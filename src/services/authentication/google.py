from google.auth import exceptions
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from .interface import (
    AuthenticationRejected,
    AuthenticationUnavailable,
    InternalAuthenticationService,
    ServiceIdentity,
)


class BoundedRequest(Request):
    """Bound Google certificate retrieval without implementing token verification."""

    def __call__(self, *args, **kwargs):
        kwargs["timeout"] = 10
        return super().__call__(*args, **kwargs)


class GoogleInternalAuthenticationService(InternalAuthenticationService):
    def __init__(self):
        self.request = BoundedRequest()

    def close(self):
        self.request.session.close()

    def _verify_identity(self, token, audience):
        try:
            claims = id_token.verify_oauth2_token(
                token, self.request, audience=audience
            )

        except exceptions.TransportError:
            raise AuthenticationUnavailable("Google identity unavailable") from None

        except (ValueError, exceptions.GoogleAuthError):
            raise AuthenticationRejected("Invalid Google identity") from None

        if (
            claims.get("iss")
            not in {"accounts.google.com", "https://accounts.google.com"}
            or claims.get("aud") != audience
            or claims.get("email_verified") is not True
            or not isinstance(claims.get("email"), str)
        ):
            raise AuthenticationRejected("Unexpected Google identity")

        return ServiceIdentity(claims["email"])
