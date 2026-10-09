"""Verify Supabase access tokens using the provider SDK."""

import os
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from supabase_auth import SyncGoTrueClient
from supabase_auth.errors import AuthApiError, AuthError, AuthRetryableError

from config import load_environment

from .interface import (
    AuthenticationRejected,
    AuthenticationService,
    AuthenticationUnavailable,
    VerifiedUser,
)


def validate_provider_config(url: str, publishable_key: str) -> str:
    """Accept only a project origin, including explicit local Supabase origins."""
    if (
        not isinstance(url, str)
        or not isinstance(publishable_key, str)
        or not publishable_key.strip()
    ):
        raise ValueError("Supabase URL and publishable key required")

    parsed = urlsplit(url)

    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or url != url.strip()
    ):
        raise ValueError("AUTH_SUPABASE_URL must be an origin")

    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("HTTPS AUTH_SUPABASE_URL required outside localhost")

    # Validate ports before allowing the SDK to construct its endpoint.
    _ = parsed.port
    return url.rstrip("/")


class SupabaseAuthenticationService(AuthenticationService):
    def __init__(self, url: str, publishable_key: str):
        self.url = validate_provider_config(url, publishable_key)

        self.key = publishable_key
        self.verifier_client = self._client()

    @classmethod
    def from_environment(cls):
        load_environment()

        try:
            return cls(
                os.environ["AUTH_SUPABASE_URL"],
                os.environ["AUTH_SUPABASE_PUBLISHABLE_KEY"],
            )

        except (KeyError, ValueError):
            raise AuthenticationUnavailable(
                "Authentication configuration unavailable"
            ) from None

    def close(self):
        self.verifier_client._http_client.close()

    def _client(self):
        return SyncGoTrueClient(
            url=f"{self.url}/auth/v1",
            headers={"apikey": self.key, "Authorization": f"Bearer {self.key}"},
            auto_refresh_token=False,
            persist_session=False,
            http_client=httpx.Client(timeout=10),
        )

    def _call(self, operation):
        try:
            return operation()

        except (httpx.HTTPError, AuthRetryableError):
            raise AuthenticationUnavailable("Auth provider unavailable") from None

        except AuthApiError as error:
            if int(error.status or 0) >= 500:
                raise AuthenticationUnavailable("Auth provider unavailable") from None

            raise AuthenticationRejected("Auth provider rejected credentials") from None

        except (AuthError, ValueError, KeyError, TypeError):
            raise AuthenticationRejected("Invalid provider response") from None

    def _authenticate_token(self, access_token):
        result = self._call(lambda: self.verifier_client.get_claims(jwt=access_token))

        if not result:
            raise AuthenticationRejected("Missing claims")

        claims = result["claims"]
        audience = claims.get("aud")

        if (
            claims.get("iss") != f"{self.url}/auth/v1"
            or claims.get("role") != "authenticated"
            or not (
                audience == "authenticated"
                or isinstance(audience, list)
                and "authenticated" in audience
            )
        ):
            raise AuthenticationRejected("Unexpected token claims")

        try:
            owner_id = UUID(claims["sub"])

        except (ValueError, KeyError, TypeError):
            raise AuthenticationRejected("Invalid user identity") from None

        expires_at = claims.get("exp")

        if not isinstance(expires_at, int):
            raise AuthenticationRejected("Access token expired")

        profile = claims.get("user_metadata") or {}
        return VerifiedUser(
            owner_id, claims.get("email"), profile.get("full_name"), expires_at
        )
