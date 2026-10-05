from dataclasses import dataclass
from time import perf_counter

from tools import LLM, FileToMarkdown, SingleModel

from .models import ExtractedStatement, NormalizedStatement, RunMetrics
from .parallel_choice import classify_parallel_choice
from .state import ClassifierState


@dataclass(frozen=True)
class ClassifierNodes:
    converter: FileToMarkdown
    extractor: LLM
    classifier: SingleModel

    def convert_document(self, state: ClassifierState) -> dict:
        markdown = self.converter.convert(
            state["file_base64"],
            filename=state["filename"],
        )

        return {"markdown": markdown}

    def extract_transactions(self, state: ClassifierState) -> dict:
        response = self.extractor.prompt(state["markdown"])

        extracted = ExtractedStatement.model_validate(response.structured_output)

        return {"extracted": extracted}

    def classify_transactions(self, state: ClassifierState) -> dict:
        batch = classify_parallel_choice(
            self.classifier, state["extracted"].transactions
        )

        return {"batch": batch}

    def consolidate(self, state: ClassifierState) -> dict:
        batch = state["batch"]
        result = NormalizedStatement(
            statement=state["extracted"].statement,
            transactions=batch.transactions,
            metrics=RunMetrics(
                elapsed_seconds=(
                    perf_counter() - state["started_at"] if "started_at" in state else 0
                ),
                classification_seconds=batch.elapsed_seconds,
                classification_model_calls=batch.model_calls,
                transaction_count=len(batch.transactions),
            ),
        )

        return {"result": result}
