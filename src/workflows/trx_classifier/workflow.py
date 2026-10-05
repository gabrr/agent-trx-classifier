from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .nodes import ClassifierNodes
from .state import ClassifierState
from .steps import workflow_step


def build_graph(nodes: ClassifierNodes) -> CompiledStateGraph:
    graph = StateGraph(ClassifierState)

    steps = [
        (
            "convert",
            "Convert PDF to Markdown",
            "markdown",
            nodes.convert_document,
            "markdown",
        ),
        (
            "extract",
            "Extract transactions",
            "extracted",
            nodes.extract_transactions,
            "json",
        ),
        (
            "classify",
            "Classify transactions",
            "batch",
            nodes.classify_transactions,
            "json",
        ),
        ("complete", "Prepare result", "result", nodes.consolidate, "json"),
    ]
    previous = START

    for step_id, name, output_key, operation, output_type in steps:
        graph.add_node(
            step_id,
            workflow_step(
                step_id, name, output_key, operation, output_type=output_type
            ),
        )

        graph.add_edge(previous, step_id)

        previous = step_id

    graph.add_edge(previous, END)

    return graph.compile()
