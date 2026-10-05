from collections.abc import Callable
from time import perf_counter
from typing import Any, TypedDict

from langchain.agents.structured_output import ProviderStrategy
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from config import AgentConfig, load_environment
from runtime.events import json_output
from tools import file_to_markdown_factory, llm_factory, single_model_factory
from tools.statement_file import StatementFileInput

from .classification import ClassificationBatch, classify_transactions
from .models import ExtractedStatement, NormalizedStatement, RunMetrics
from .prompts import EXTRACTION_PROMPT


class ClassifierState(TypedDict, total=False):
    # Local runs share the file object; tooling supplies file_base64 and filename.
    file: Any
    file_base64: str
    filename: str
    started_at: float
    document_text: str
    document_format: str
    extracted: ExtractedStatement
    batch: ClassificationBatch
    result: NormalizedStatement


def _with_progress(
    step_id: str,
    name: str,
    operation: Callable[[ClassifierState], dict],
    output_key: str | None,
    output_type: str | Callable[[ClassifierState], str] = "json",
):
    """Wrap a focused node with the shared progress event contract."""

    def execute(state: ClassifierState) -> dict:
        writer = get_stream_writer()

        writer({"event": "step_started", "data": {"step_id": step_id, "name": name}})

        started = perf_counter()

        update = operation(state)

        data = {
            "step_id": step_id,
            "name": name,
            "elapsed_seconds": perf_counter() - started,
        }

        if output_key is not None:
            data["output_type"] = (
                output_type(state | update) if callable(output_type) else output_type
            )
            data["output"] = json_output(update[output_key])

        writer({"event": "step_completed", "data": data})

        return update

    return execute


def build_workflow() -> CompiledStateGraph:
    """Build the classifier for local execution and LangGraph tooling."""
    load_environment()

    config = AgentConfig()

    converter = file_to_markdown_factory("docling")
    extractor = llm_factory(
        "langchain",
        model="openrouter:google/gemini-3.8-flash",
        system_prompt=EXTRACTION_PROMPT,
        response_format=ProviderStrategy(ExtractedStatement),
    )
    classifier = single_model_factory("jev")

    def convert(state: ClassifierState) -> dict:
        file = state.get("file")

        if file is None:
            file = StatementFileInput.from_base64(
                state["file_base64"], filename=state["filename"], config=config
            )

        text = file.to_text(pdf_converter=converter)

        return {"document_text": text, "document_format": file.format}

    def extract(state: ClassifierState) -> dict:
        response = extractor.prompt(state["document_text"])

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
            "convert",
            "Prepare statement text",
            convert,
            "document_text",
            lambda state: "markdown" if state["document_format"] == "pdf" else "text",
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
        _with_progress("complete", "Prepare result", complete, None),
    )

    graph.add_edge(START, "convert")

    graph.add_edge("convert", "extract")

    graph.add_edge("extract", "classify")

    graph.add_edge("classify", "complete")

    graph.add_edge("complete", END)

    return graph.compile()
