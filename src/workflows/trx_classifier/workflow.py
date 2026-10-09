from typing import Any, TypedDict

from langchain.agents.structured_output import ProviderStrategy
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from config import AgentConfig, load_environment
from tools import file_to_markdown_factory, llm_factory, single_model_factory
from tools.event_stream import event_stream
from tools.statement_file import StatementFileInput

from .classification import ClassificationBatch, classify_transactions
from .models import ExtractedStatement, NormalizedStatement, RunMetrics
from .prompts import EXTRACTION_PROMPT


class ClassifierState(TypedDict, total=False):
    # Local runs share the file object; tooling supplies file_base64 and filename.
    file: Any
    file_base64: str
    filename: str
    step_durations: dict[str, float]
    document_text: str
    document_format: str
    extracted: ExtractedStatement
    batch: ClassificationBatch
    result: NormalizedStatement


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
        if state.get("document_text") is not None:
            return {
                "document_text": state["document_text"],
                "document_format": state["document_format"],
            }

        file = state.get("file")

        if file is None:
            file = StatementFileInput.from_base64(
                state["file_base64"], filename=state["filename"], config=config
            )

        text = file.to_text(pdf_converter=converter)

        return {"document_text": text, "document_format": file.format}

    def extract(state: ClassifierState) -> dict:
        if state.get("extracted") is not None:
            return {"extracted": ExtractedStatement.model_validate(state["extracted"])}

        response = extractor.prompt(state["document_text"])

        extracted = ExtractedStatement.model_validate(response.structured_output)

        return {"extracted": extracted}

    def classify(state: ClassifierState) -> dict:
        if state.get("batch") is not None:
            from pydantic import TypeAdapter

            return {
                "batch": TypeAdapter(ClassificationBatch).validate_python(
                    state["batch"]
                )
            }

        batch = classify_transactions(classifier, state["extracted"].transactions)

        return {"batch": batch}

    def complete(state: ClassifierState) -> dict:
        batch = state["batch"]
        result = NormalizedStatement(
            statement=state["extracted"].statement,
            transactions=batch.transactions,
            metrics=RunMetrics(
                elapsed_seconds=sum(state.get("step_durations", {}).values()),
                classification_seconds=batch.elapsed_seconds,
                classification_model_calls=batch.model_calls,
                transaction_count=len(batch.transactions),
            ),
        )

        return {"result": result}

    def conversion_output_type(state: ClassifierState) -> str:
        if state["document_format"] == "pdf":
            return "markdown"

        return "text"

    graph = StateGraph(ClassifierState)

    graph.add_node(
        "convert",
        event_stream(
            convert,
            step_id="convert",
            name="Prepare statement text",
            output_key="document_text",
            output_type=conversion_output_type,
        ),
    )

    graph.add_node(
        "extract",
        event_stream(
            extract,
            step_id="extract",
            name="Extract transactions",
            output_key="extracted",
        ),
    )

    graph.add_node(
        "classify",
        event_stream(
            classify,
            step_id="classify",
            name="Classify transactions",
            output_key="batch",
        ),
    )

    graph.add_node(
        "complete",
        event_stream(
            complete,
            step_id="complete",
            name="Prepare result",
            record_duration=False,
        ),
    )

    graph.add_edge(START, "convert")

    graph.add_edge("convert", "extract")

    graph.add_edge("extract", "classify")

    graph.add_edge("classify", "complete")

    graph.add_edge("complete", END)

    return graph.compile()
