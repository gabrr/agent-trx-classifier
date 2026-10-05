from .interface import SingleModel


def single_model_factory(provider: str = "jev") -> SingleModel:
    """Return the selected implementation as a SingleModel interface."""

    if not isinstance(provider, str):
        raise TypeError("provider must be a string.")

    if provider.strip().lower() == "jev":
        from .jev import JevProvider

        return JevProvider()

    raise ValueError(f"Unsupported single-model provider: {provider}")
