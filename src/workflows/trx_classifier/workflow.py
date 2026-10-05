from collections.abc import Callable
from time import perf_counter
from typing import TypedDict

from langchain.agents.structured_output import ProviderStrategy
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from runtime.events import json_output
from runtime.settings import Settings, load_environment
from tools import file_to_markdown_factory, llm_factory, single_model_factory

from .classification import ClassificationBatch, classify_transactions
from .models import ExtractedStatement, NormalizedStatement, RunMetrics
from .prompts import EXTRACTION_PROMPT


class ClassifierState(TypedDict, total=False):
    file_base64: str
    filename: str
    started_at: float
    markdown: str
    extracted: ExtractedStatement
    batch: ClassificationBatch
    result: NormalizedStatement


def _with_progress(
    step_id: str,
    name: str,
    operation: Callable[[ClassifierState], dict],
    output_key: str,
    output_type: str = "json",
):
    """Wrap a focused node with the shared progress event contract."""

    def execute(state: ClassifierState) -> dict:
        writer = get_stream_writer()

        writer({"event": "step_started", "data": {"step_id": step_id, "name": name}})

        started = perf_counter()

        update = operation(state)

        writer(
            {
                "event": "step_completed",
                "data": {
                    "step_id": step_id,
                    "name": name,
                    "output_type": output_type,
                    "output": json_output(update[output_key]),
                    "elapsed_seconds": perf_counter() - started,
                },
            }
        )

        return update

    return execute


def build_workflow() -> CompiledStateGraph:
    """Build the classifier for local execution and LangGraph tooling."""
    load_environment()

    settings = Settings()

    converter = file_to_markdown_factory("docling")
    extractor = llm_factory(
        "langchain",
        model=settings.extraction_model,
        system_prompt=EXTRACTION_PROMPT,
        response_format=ProviderStrategy(ExtractedStatement),
    )
    classifier = single_model_factory("jev")

    def convert(state: ClassifierState) -> dict:
        markdown = converter.convert(state["file_base64"], filename=state["filename"])

        return {"markdown": markdown}

    def extract(state: ClassifierState) -> dict:
        response = extractor.prompt(state["markdown"])

        extracted = ExtractedStatement.model_validate(response.structured_output)

        return {"extracted": extracted}

    def classify(state: ClassifierState) -> dict:
        batch = classify_transactions(classifier, state["extracted"].transactions)

        return {"batch": batch}

    def complete(state: ClassifierState) -> dict:
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

    graph = StateGraph(ClassifierState)

    graph.add_node(
        "convert",
        _with_progress(
            "convert", "Convert PDF to Markdown", convert, "markdown", "markdown"
        ),
    )

    graph.add_node(
        "extract",
        _with_progress("extract", "Extract transactions", extract, "extracted"),
    )

    graph.add_node(
        "classify",
        _with_progress("classify", "Classify transactions", classify, "batch"),
    )

    graph.add_node(
        "complete",
        _with_progress("complete", "Prepare result", complete, "result"),
    )

    graph.add_edge(START, "convert")

    graph.add_edge("convert", "extract")

    graph.add_edge("extract", "classify")

    graph.add_edge("classify", "complete")

    graph.add_edge("complete", END)

    return graph.compile()
