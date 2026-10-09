"""Bearer authentication and Google service caller dependencies."""

import hmac
import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from db.repositories.users import synchronize_verified_profile
from services.authentication import (
    AuthenticationRejected,
    AuthenticationService,
    AuthenticationUnavailable,
    authentication_factory,
    internal_auth_factory,
)
from services.authentication.interface import VerifiedUser


def get_auth_service(request: Request) -> AuthenticationService:
    service = getattr(request.app.state, "auth_service", None)

    if service is not None:
        return service

    try:
        service = authentication_factory()

    except AuthenticationUnavailable:
        raise HTTPException(503, "Authentication unavailable") from None

    request.app.state.auth_service = service
    return service


def current_user(
    request: Request,
    service: Annotated[AuthenticationService, Depends(get_auth_service)],
) -> VerifiedUser:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")

    if scheme.lower() != "bearer" or not token or any(char.isspace() for char in token):
        raise HTTPException(
            401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        user = service.authenticate_token(token)

    except AuthenticationRejected:
        raise HTTPException(
            401, "Sign in required", headers={"WWW-Authenticate": "Bearer"}
        ) from None

    except AuthenticationUnavailable:
        raise HTTPException(503, "Authentication unavailable") from None

    sessions = getattr(request.app.state, "db_sessions", None)

    if sessions is not None:
        with sessions.begin() as session:
            synchronize_verified_profile(session, user.id, email=user.email)

    return user


def _internal_caller(request: Request, caller_state: str, caller_env: str):
    audience = os.environ.get("BACKEND_URL")

    expected = getattr(request.app.state, caller_state, None) or os.environ.get(
        caller_env
    )

    if not audience or not expected:
        raise HTTPException(503, "Internal authentication unavailable")

    scheme, _, token = request.headers.get("authorization", "").partition(" ")

    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Service identity required")

    provider = getattr(request.app.state, "internal_auth_provider", None)

    if provider is None:
        provider = internal_auth_factory()

        request.app.state.internal_auth_provider = provider

    try:
        identity = provider.verify_identity(token, audience)

    except AuthenticationRejected:
        raise HTTPException(401, "Invalid service identity") from None

    except AuthenticationUnavailable:
        raise HTTPException(503, "Internal authentication unavailable") from None

    if not hmac.compare_digest(identity.email, expected):
        raise HTTPException(403, "Service caller not authorized")

    return identity


def require_task_caller(request: Request):
    return _internal_caller(request, "task_caller_email", "TASK_CALLER_EMAIL")


def require_maintenance_caller(request: Request):
    return _internal_caller(
        request, "maintenance_caller_email", "MAINTENANCE_CALLER_EMAIL"
    )
