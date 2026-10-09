import json
import time
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from api.authentication import router
from api.dependencies import (
    get_auth_service,
    require_maintenance_caller,
    require_task_caller,
)
from services.authentication import AuthenticationService, authentication_factory
from services.authentication.interface import (
    AuthenticationRejected,
    AuthenticationUnavailable,
    ServiceIdentity,
    VerifiedUser,
)
from services.authentication.supabase import SupabaseAuthenticationService


@pytest.fixture
def browser():
    class Provider(AuthenticationService):
        tokens = []
        failure = None

        def _authenticate_token(self, token):
            self.tokens.append(token)

            if self.failure:
                raise self.failure()

            if token != "valid":
                raise AuthenticationRejected()

            return VerifiedUser(
                owner, "user@example.com", "User", int(time.time()) + 3600
            )

    owner = uuid4()

    provider = Provider()

    app = FastAPI()

    app.include_router(router)

    app.dependency_overrides[get_auth_service] = lambda: provider

    return TestClient(app), provider, owner


def test_each_request_verifies_bearer_token_without_backend_session(browser):
    client, provider, owner = browser
    for _ in range(2):
        response = client.get("/auth/me", headers={"Authorization": "Bearer valid"})

        assert response.status_code == 200
        assert response.json() == {
            "id": str(owner),
            "email": "user@example.com",
            "name": "User",
        }
        assert "set-cookie" not in response.headers

    assert provider.tokens == ["valid", "valid"]


@pytest.mark.parametrize(
    "authorization",
    ["", "Basic valid", "Bearer", "Bearer invalid", "Bearer valid extra"],
)
def test_missing_or_invalid_bearer_returns_401(browser, authorization):
    client, _, _ = browser
    response = client.get("/auth/me", headers={"Authorization": authorization})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_cookie_and_query_token_are_not_credentials(browser):
    client, provider, _ = browser
    client.cookies.set("trx_session", "valid")

    assert client.get("/auth/me?access_token=valid").status_code == 401
    assert not provider.tokens


def test_provider_outage_returns_503(browser):
    client, provider, _ = browser
    provider.failure = AuthenticationUnavailable
    assert (
        client.get("/auth/me", headers={"Authorization": "Bearer valid"}).status_code
        == 503
    )


def test_backend_login_and_logout_routes_removed(browser):
    client, _, _ = browser
    assert client.post("/auth/login").status_code == 404
    assert client.get("/auth/callback").status_code == 404
    assert client.post("/auth/logout").status_code == 404


@pytest.fixture
def signed_provider():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))

    jwk.update(kid="test-key", alg="RS256", use="sig")

    provider = SupabaseAuthenticationService(
        "https://example.supabase.co", "public-key"
    )

    calls = []

    def respond(request):
        calls.append(str(request.url))

        return httpx.Response(200, json={"keys": [jwk]})

    provider.verifier_client._http_client.close()

    provider.verifier_client._http_client = httpx.Client(
        transport=httpx.MockTransport(respond)
    )

    owner = uuid4()

    claims = {
        "iss": "https://example.supabase.co/auth/v1",
        "aud": "authenticated",
        "role": "authenticated",
        "sub": str(owner),
        "exp": int(time.time()) + 3600,
    }
    yield provider, key, claims, calls
    provider.close()


def sign(key, claims):
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})


def test_actual_sdk_verifies_signature_and_caches_project_keys(signed_provider):
    provider, key, claims, calls = signed_provider
    token = sign(key, claims)

    for _ in range(2):
        user = provider.authenticate_token(token)

        assert str(user.id) == claims["sub"]
        assert user.expires_at == claims["exp"]

    assert len(calls) == 1
    assert calls[0].endswith("/auth/v1/.well-known/jwks.json")


@pytest.mark.parametrize(
    "change",
    [
        {"exp": 1},
        {"iss": "https://other.supabase.co/auth/v1"},
        {"aud": "other"},
        {"role": "service_role"},
        {"sub": "invalid"},
    ],
)
def test_expired_wrong_project_audience_role_and_identity_rejected(
    signed_provider, change
):
    provider, key, claims, _ = signed_provider
    with pytest.raises(AuthenticationRejected):
        provider.authenticate_token(sign(key, {**claims, **change}))


def test_forged_signature_rejected(signed_provider):
    provider, _, claims, _ = signed_provider
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with pytest.raises(AuthenticationRejected):
        provider.authenticate_token(sign(attacker_key, claims))


@pytest.mark.parametrize("token", ["not-a-jwt", "a.b.c"])
def test_malformed_token_rejected(signed_provider, token):
    provider, _, _, _ = signed_provider
    with pytest.raises(AuthenticationRejected):
        provider.authenticate_token(token)


def test_open_stream_identity_expires():
    service = AuthenticationService

    assert not service.is_token_active(VerifiedUser(uuid4(), expires_at=1))

    assert service.is_token_active(
        VerifiedUser(uuid4(), expires_at=int(time.time()) + 3600)
    )


@pytest.mark.parametrize(
    "url,key",
    [
        ("", "key"),
        ("https://example.supabase.co", ""),
        ("http://remote.example", "key"),
        ("https://user:password@example.supabase.co", "key"),
        ("https://example.supabase.co/auth/v1", "key"),
    ],
)
def test_invalid_provider_configuration_rejected(url, key):
    with pytest.raises(ValueError):
        SupabaseAuthenticationService(url, key)


def test_auth_environment_requires_only_provider_configuration(monkeypatch):
    monkeypatch.setenv("AUTH_SUPABASE_URL", "https://example.supabase.co")

    monkeypatch.setenv("AUTH_SUPABASE_PUBLISHABLE_KEY", "public-key")

    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)

    service = authentication_factory()

    assert service.url == "https://example.supabase.co"
    assert service.key == "public-key"

    service.close()


def test_service_caller_audience_and_allowlist(monkeypatch):
    seen = []

    class Provider:
        def verify_identity(self, token, audience):
            seen.append((token, audience))

            return ServiceIdentity("tasks@example.iam.gserviceaccount.com")

    app = FastAPI()

    app.state.internal_auth_provider = Provider()

    monkeypatch.setenv("BACKEND_URL", "https://worker.example")
    app.state.task_caller_email = "tasks@example.iam.gserviceaccount.com"
    app.state.maintenance_caller_email = "scheduler@example.iam.gserviceaccount.com"

    @app.post("/task", dependencies=[Depends(require_task_caller)])
    def task():
        return {}

    @app.post("/maintenance", dependencies=[Depends(require_maintenance_caller)])
    def maintenance():
        return {}

    client = TestClient(app)

    assert client.post("/task").status_code == 401
    assert (
        client.post("/task", headers={"authorization": "Bearer token"}).status_code
        == 200
    )

    assert seen == [("token", "https://worker.example")]
    assert (
        client.post(
            "/maintenance", headers={"authorization": "Bearer token"}
        ).status_code
        == 403
    )


def test_google_verifier_rejects_unverified_email_and_wrong_audience(monkeypatch):
    from services.authentication import google
    from services.authentication.google import GoogleInternalAuthenticationService

    claims = {
        "iss": "https://accounts.google.com",
        "aud": "expected",
        "email_verified": False,
        "email": "caller@example.com",
    }
    monkeypatch.setattr(
        google.id_token, "verify_oauth2_token", lambda *args, **kwargs: claims
    )

    provider = GoogleInternalAuthenticationService()

    with pytest.raises(AuthenticationRejected):
        provider.verify_identity("token", "expected")

    claims["email_verified"] = True
    claims["aud"] = "different"
    with pytest.raises(AuthenticationRejected):
        provider.verify_identity("token", "expected")


def test_verified_identity_controls_job_access_and_submission(signed_provider):
    from api.jobs import get_job_service
    from api.jobs import router as jobs_router

    provider, key, claims, _ = signed_provider
    owner = claims["sub"]
    job_id = uuid4()

    class Jobs:
        def get_job(self, user_id, requested_id):
            if str(user_id) != owner:
                raise LookupError()

            return {"id": str(requested_id), "status": "queued"}

        def get_result(self, user_id, requested_id):
            self.get_job(user_id, requested_id)

            return {"transactions": []}

        def retry_job(self, user_id, requested_id, submission_key):
            return self.get_job(user_id, requested_id)

        def submit_job(self, user_id, content, filename, submission_key):
            assert str(user_id) == owner
            return {"id": str(job_id), "status": "queued"}

    app = FastAPI()

    app.include_router(jobs_router)

    app.dependency_overrides[get_auth_service] = lambda: provider

    app.dependency_overrides[get_job_service] = Jobs
    client = TestClient(app)

    headers = {
        "Authorization": f"Bearer {sign(key, claims)}",
        "Idempotency-Key": "submission",
    }
    assert client.get(f"/api/jobs/{job_id}").status_code == 401
    assert client.get(f"/api/jobs/{job_id}", headers=headers).status_code == 200
    assert (
        client.post(
            "/api/jobs", headers=headers, files={"file": ("test.pdf", b"%PDF-test")}
        ).status_code
        == 202
    )

    headers["Authorization"] = f"Bearer {sign(key, {**claims, 'sub': str(uuid4())})}"
    for path in (
        f"/api/jobs/{job_id}",
        f"/api/jobs/{job_id}/result",
        f"/api/jobs/{job_id}/events",
    ):
        assert client.get(path, headers=headers).status_code == 404

    assert client.post(f"/api/jobs/{job_id}/retry", headers=headers).status_code == 404


def test_event_stream_closes_when_verified_token_expires(signed_provider, monkeypatch):
    from types import SimpleNamespace

    from api.jobs import get_job_service
    from api.jobs import router as jobs_router
    from services.authentication import interface as authentication

    provider, key, claims, _ = signed_provider
    times = iter([claims["exp"] - 1, claims["exp"] + 1])

    monkeypatch.setattr(
        authentication, "time", SimpleNamespace(time=lambda: next(times))
    )

    removed = []

    class Listener:
        def subscribe(self, *args, **kwargs):
            return "subscription"

        def unsubscribe(self, token):
            removed.append(token)

    app = FastAPI()

    app.include_router(jobs_router)

    app.state.job_listener = Listener()

    app.dependency_overrides[get_auth_service] = lambda: provider

    app.dependency_overrides[get_job_service] = lambda: SimpleNamespace(
        get_job=lambda *args: {"status": "running"}
    )

    response = TestClient(app).get(
        f"/api/jobs/{uuid4()}/events",
        headers={"Authorization": f"Bearer {sign(key, claims)}"},
    )

    assert response.status_code == 200
    assert "event: session_expired" in response.text
    assert removed == ["subscription"]


def test_missing_provider_configuration_returns_503(monkeypatch):
    from services.authentication import supabase as authentication

    monkeypatch.setattr(authentication, "load_environment", lambda: None)

    monkeypatch.setenv("AUTH_SUPABASE_URL", "")

    monkeypatch.setenv("AUTH_SUPABASE_PUBLISHABLE_KEY", "key")

    app = FastAPI()

    app.include_router(router)

    response = TestClient(app).get(
        "/auth/me", headers={"Authorization": "Bearer token"}
    )

    assert response.status_code == 503


def test_verification_key_network_failure_is_unavailable(signed_provider):
    provider, key, claims, _ = signed_provider

    def fail(request):
        raise httpx.ConnectError("Unavailable", request=request)

    provider.verifier_client._http_client.close()

    provider.verifier_client._http_client = httpx.Client(
        transport=httpx.MockTransport(fail)
    )

    with pytest.raises(AuthenticationUnavailable):
        provider.authenticate_token(sign(key, claims))
