import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from openrouter import OpenRouter


def chat_model_factory(model: str) -> BaseChatModel:
    if model.startswith("openrouter:"):
        client = OpenRouter(
            api_key=os.environ["OPENROUTER_API_KEY"],
            retry_config=None,
            timeout_ms=120_000,
        )

        return init_chat_model(model, client=client, max_retries=0, timeout=120_000)

    return init_chat_model(model, max_retries=0)
