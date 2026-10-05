import base64
from collections.abc import AsyncIterator
from time import perf_counter

from langgraph.graph.state import CompiledStateGraph

from workflows.trx_classifier.models import NormalizedStatement

from .events import WorkflowEvent
from .interface import DocumentClassifier
from .settings import Settings


def document_input(document: bytes, filename: str) -> dict:
    if not document or not document.startswith(b"%PDF-"):
        raise ValueError("Upload a nonempty PDF document.")

    if not filename.lower().endswith(".pdf"):
        raise ValueError("The document filename must end in .pdf.")

    if len(document) > Settings().max_upload_bytes:
        raise ValueError("PDF exceeds the 25 MiB upload limit.")

    return {
        "file_base64": base64.b64encode(document).decode("ascii"),
        "filename": filename,
    }


class LangGraphRunner(DocumentClassifier):
    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph

    def classify(self, document: bytes, *, filename: str) -> NormalizedStatement:
        inputs = document_input(document, filename)

        started = perf_counter()

        inputs["started_at"] = started
        state = self._graph.invoke(inputs, config={"run_name": "trx_classifier"})

        result = NormalizedStatement.model_validate(state["result"])

        result.metrics.elapsed_seconds = perf_counter() - started

        return result

    async def events(
        self, document: bytes, *, filename: str
    ) -> AsyncIterator[WorkflowEvent]:
        inputs = document_input(document, filename)

        started = perf_counter()

        inputs["started_at"] = started
        completed = False

        async for part in self._graph.astream(
            inputs,
            config={"run_name": "trx_classifier"},
            stream_mode=["custom", "updates"],
            version="v2",
        ):
            if part["type"] == "custom":
                yield WorkflowEvent.model_validate(part["data"])

            elif part["type"] == "updates":
                update = part["data"].get("complete")

                if update:
                    result = NormalizedStatement.model_validate(update["result"])

                    result.metrics.elapsed_seconds = perf_counter() - started
                    completed = True

                    yield WorkflowEvent(
                        event="result", data=result.model_dump(mode="json")
                    )

        if not completed:
            raise RuntimeError("Workflow ended without a result.")
