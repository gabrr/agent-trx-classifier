from .interface import AuthenticationService, InternalAuthenticationService


def authentication_factory(
    provider: str = "supabase",
    *,
    url: str | None = None,
    publishable_key: str | None = None,
) -> AuthenticationService:
    if provider != "supabase":
        raise ValueError(f"Unsupported authentication service: {provider}")

    from .supabase import SupabaseAuthenticationService

    if url is None and publishable_key is None:
        return SupabaseAuthenticationService.from_environment()

    return SupabaseAuthenticationService(url, publishable_key)


def internal_auth_factory(provider: str = "google") -> InternalAuthenticationService:
    if provider != "google":
        raise ValueError(f"Unsupported internal authentication service: {provider}")

    from .google import GoogleInternalAuthenticationService

    return GoogleInternalAuthenticationService()
