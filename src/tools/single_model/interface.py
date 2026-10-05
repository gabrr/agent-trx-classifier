from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, Literal, Required, TypedDict

type ModelState = str | dict[str, Any] | list[Any]


class SingleModelQuestion(TypedDict, total=False):
    type: Required[Literal["noul", "choice", "score"]]
    instructions: str | dict[str, Any] | list[Any] | None
    criteria: dict[str, Any] | list[Any] | None


type SingleModelQuestions = Mapping[str, SingleModelQuestion]
type SingleModelResult = dict[str, Any]


class SingleModel(ABC):
    """Interface for typed model decisions."""

    def evaluate(
        self,
        state: ModelState,
        questions: SingleModelQuestions,
    ) -> SingleModelResult:
        if not isinstance(state, (str, dict, list)):
            raise TypeError("state must be a string, dictionary, or list.")

        if not questions:
            raise ValueError("At least one question is required.")

        for name, question in questions.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Question names must be non-empty strings.")

            if question.get("type") not in {"noul", "choice", "score"}:
                raise ValueError(f"Unsupported question type for {name}.")

        result = self._evaluate(state, questions)

        if not isinstance(result, dict):
            raise TypeError("Provider must return a dictionary.")

        return result

    @abstractmethod
    def _evaluate(
        self,
        state: ModelState,
        questions: SingleModelQuestions,
    ) -> SingleModelResult:
        """Evaluate validated questions with the concrete model."""
        raise NotImplementedError
