"""Provider-independent authentication contracts; HTTP and persistence stay outside."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


class AuthenticationRejected(Exception):
    """Invalid credentials or provider session."""


class AuthenticationUnavailable(Exception):
    """Authentication provider temporarily unavailable."""


@dataclass(frozen=True)
class VerifiedUser:
    id: UUID
    email: str | None = None
    name: str | None = None
    expires_at: int = 0


@dataclass(frozen=True)
class ServiceIdentity:
    email: str


class AuthenticationService(ABC):
    def authenticate_token(self, token: str) -> VerifiedUser:
        if not token:
            raise AuthenticationRejected("Missing token")

        user = self._authenticate_token(token)

        if not self.is_token_active(user):
            raise AuthenticationRejected("Access token expired")

        return user

    @staticmethod
    def is_token_active(user: VerifiedUser) -> bool:
        return user.expires_at > time.time()

    def close(self) -> None:
        return None

    @abstractmethod
    def _authenticate_token(self, token: str) -> VerifiedUser: ...


class InternalAuthenticationService(ABC):
    def verify_identity(self, token: str, audience: str) -> ServiceIdentity:
        if not token or not audience:
            raise AuthenticationRejected("Missing service credentials")

        return self._verify_identity(token, audience)

    def close(self) -> None:
        return None

    @abstractmethod
    def _verify_identity(self, token: str, audience: str) -> ServiceIdentity: ...
