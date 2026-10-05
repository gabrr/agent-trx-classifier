from typing import Any

from langsmith import traceable
from typesafe_sdk import Choice, Noul, RetryPolicy, Score, TypeSafeClient

from .interface import (
    ModelState,
    SingleModel,
    SingleModelQuestion,
    SingleModelQuestions,
    SingleModelResult,
)


class JevProvider(SingleModel):
    """Evaluate typed questions with TypeSafe's Jev model."""

    def __init__(self, client: TypeSafeClient | None = None) -> None:
        self._client = client or TypeSafeClient(
            model="jev-latest",
            retry=RetryPolicy(max_retries=0),
            timeout=120,
        )

    @traceable(name="jev_parallel_choice", run_type="tool")
    def _evaluate(
        self,
        state: ModelState,
        questions: SingleModelQuestions,
    ) -> SingleModelResult:
        response = self._client.system_one(
            state=state,
            questions={
                name: self._build_question(question)
                for name, question in questions.items()
            },
        )

        return response.model_dump(mode="json")

    @staticmethod
    def _build_question(question: SingleModelQuestion) -> Noul | Choice | Score:
        question_type = question["type"]
        instructions = question.get("instructions")

        criteria: Any = question.get("criteria")

        if question_type == "noul":
            return Noul(instructions=instructions, criteria=criteria)

        if question_type == "choice":
            if not isinstance(criteria, dict) or not criteria:
                raise ValueError("Choice questions require mapping criteria.")

            return Choice(instructions=instructions, criteria=criteria)

        if question_type == "score":
            if not isinstance(criteria, list) or not criteria:
                raise ValueError("Score questions require list criteria.")

            return Score(instructions=instructions, criteria=criteria)

        raise ValueError(f"Unsupported question type: {question_type}")
