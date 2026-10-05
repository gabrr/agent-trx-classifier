from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from langchain.agents.structured_output import ProviderStrategy, ToolStrategy

type ResponseFormat = (
    type[Any] | dict[str, Any] | ProviderStrategy[Any] | ToolStrategy[Any] | None
)


@dataclass(frozen=True)
class LLMResponse:
    """Complete response returned by an LLM."""

    message: str | None
    structured_output: Any | None = None


@dataclass(frozen=True)
class LLMStreamEvent:
    """A piece of an LLM response emitted while it is generated."""

    content: str
    metadata: dict[str, Any]


class LLM(ABC):
    """Interface for prompting an LLM synchronously or as a stream."""

    def prompt(self, prompt: str) -> LLMResponse:
        self._validate_prompt(prompt)

        response = self._prompt(prompt)

        if not isinstance(response, LLMResponse):
            raise TypeError("Provider must return an LLMResponse.")

        return response

    def stream(self, prompt: str) -> Iterator[LLMStreamEvent]:
        self._validate_prompt(prompt)

        return self._stream(prompt)

    @staticmethod
    def _validate_prompt(prompt: str) -> None:
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string.")

        if not prompt.strip():
            raise ValueError("prompt must not be empty.")

    @abstractmethod
    def _prompt(self, prompt: str) -> LLMResponse:
        """Send a validated prompt and return the complete response."""
        raise NotImplementedError

    @abstractmethod
    def _stream(self, prompt: str) -> Iterator[LLMStreamEvent]:
        """Send a validated prompt and stream the response."""
        raise NotImplementedError
