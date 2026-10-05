from .interface import LLM, ResponseFormat


def llm_factory(
    provider: str = "langchain",
    *,
    model: str,
    system_prompt: str | None = None,
    response_format: ResponseFormat = None,
) -> LLM:
    """Return the selected implementation through the LLM contract."""

    if not isinstance(provider, str):
        raise TypeError("provider must be a string.")

    if provider.strip().lower() == "langchain":
        from .langchain import LangChainProvider

        return LangChainProvider(
            model=model,
            system_prompt=system_prompt,
            response_format=response_format,
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")
