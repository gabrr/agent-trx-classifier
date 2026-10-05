from collections.abc import AsyncIterator
from time import perf_counter

from langgraph.graph.state import CompiledStateGraph

from tools.statement_file import StatementFileInput
from workflows.trx_classifier.models import NormalizedStatement

from .events import WorkflowEvent
from .interface import DocumentClassifier


class LangGraphRunner(DocumentClassifier):
    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph

    def classify(self, file: StatementFileInput) -> NormalizedStatement:
        inputs = {"file": file}

        started = perf_counter()

        inputs["started_at"] = started
        state = self._graph.invoke(inputs, config={"run_name": "trx_classifier"})

        result = NormalizedStatement.model_validate(state["result"])

        result.metrics.elapsed_seconds = perf_counter() - started

        return result

    async def events(self, file: StatementFileInput) -> AsyncIterator[WorkflowEvent]:
        inputs = {"file": file}

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
