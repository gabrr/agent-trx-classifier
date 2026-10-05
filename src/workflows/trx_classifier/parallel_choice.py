from dataclasses import dataclass
from time import perf_counter

from pydantic import BaseModel, Field, model_validator

from tools import SingleModel

from .criteria import CRITERIA
from .models import ExtractedTransaction, NormalizedTransaction, ReportBucket


class ChoiceAnswer(BaseModel):
    choice: str
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    probabilities: dict[str, float]

    @model_validator(mode="after")
    def _known_choices(self):
        if self.choice not in CRITERIA or set(self.probabilities) != set(CRITERIA):
            raise ValueError("Jev must answer using the requested criteria.")

        return self


@dataclass(frozen=True)
class ClassificationBatch:
    transactions: list[NormalizedTransaction]
    elapsed_seconds: float
    model_calls: int


def classify_parallel_choice(
    model: SingleModel,
    transactions: list[ExtractedTransaction],
) -> ClassificationBatch:
    if not transactions:
        return ClassificationBatch([], 0, 0)

    questions = {
        f"tx_{index:03d}": {
            "type": "choice",
            "instructions": {
                "transaction": transaction.model_dump(mode="json"),
                "question": (
                    "Select the explicit category supported by this transaction. "
                    "Use no_match when none applies. If evidence overlaps, "
                    "prefer movements, then installments, then fixed."
                ),
            },
            "criteria": dict(CRITERIA),
        }
        for index, transaction in enumerate(transactions)
    }
    started = perf_counter()

    response = model.evaluate(state={}, questions=questions)

    answers = response.get("answers")

    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError("Jev must return exactly one answer per transaction.")

    classified = []

    for index, transaction in enumerate(transactions):
        item_id = f"tx_{index:03d}"
        answer = ChoiceAnswer.model_validate(answers[item_id])

        category = "variable" if answer.choice == "no_match" else answer.choice
        probabilities = {
            "variable" if key == "no_match" else key: value
            for key, value in answer.probabilities.items()
        }
        classified.append(
            NormalizedTransaction(
                **transaction.model_dump(),
                id=item_id,
                report_bucket=ReportBucket(category),
                classification_confidence=answer.confidence,
                classification_probabilities=probabilities,
            )
        )

    return ClassificationBatch(classified, perf_counter() - started, 1)
