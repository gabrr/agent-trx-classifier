from collections.abc import Iterator

from langchain.agents import create_agent

from .interface import LLM, LLMResponse, LLMStreamEvent, ResponseFormat
from .model_factory import chat_model_factory


class LangChainProvider(LLM):
    """LLM implementation powered by a LangChain agent graph."""

    def __init__(
        self,
        model: str,
        *,
        system_prompt: str | None = None,
        response_format: ResponseFormat = None,
    ) -> None:
        if not isinstance(model, str):
            raise TypeError("model must be a string.")

        if not model.strip():
            raise ValueError("model must not be empty.")

        chat_model = chat_model_factory(model)

        self._agent = create_agent(
            model=chat_model,
            tools=[],
            system_prompt=system_prompt,
            response_format=response_format,
        )

    def _prompt(self, prompt: str) -> LLMResponse:
        result = self._agent.invoke({"messages": [{"role": "user", "content": prompt}]})

        final_message = result["messages"][-1]
        message = str(final_message.text) or None

        return LLMResponse(
            message=message,
            structured_output=result.get("structured_response"),
        )

    def _stream(self, prompt: str) -> Iterator[LLMStreamEvent]:
        for message, metadata in self._agent.stream(
            {"messages": [{"role": "user", "content": prompt}]},
            stream_mode="messages",
        ):
            content = str(message.text)

            if content:
                yield LLMStreamEvent(content=content, metadata=metadata)
