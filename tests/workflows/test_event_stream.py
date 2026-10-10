import asyncio
import importlib
from itertools import count
from types import SimpleNamespace

import pytest

from tools.statement_file import StatementFileInput
from workflows.trx_classifier.event_stream import workflow_events
from workflows.trx_classifier.models import NormalizedStatement
from workflows.trx_classifier.workflow import build_workflow


@pytest.fixture
def workflow(monkeypatch):
    module = importlib.import_module("workflows.trx_classifier.workflow")
    events = importlib.import_module("workflows.trx_classifier.event_stream")
    clock = count()
    monkeypatch.setattr(events, "perf_counter", lambda: float(next(clock)))
    monkeypatch.setattr(module, "load_environment", lambda: None)
    monkeypatch.setattr(
        module,
        "file_to_markdown_factory",
        lambda _: SimpleNamespace(convert=lambda *args, **kwargs: "# Statement"),
    )

    extracted = {
        "statement": {"kind": "unknown"},
        "transactions": [
            {"date": "2026-10-08", "description": "Coffee", "amount": "12.00"}
        ],
    }
    monkeypatch.setattr(
        module,
        "llm_factory",
        lambda *args, **kwargs: SimpleNamespace(
            prompt=lambda _: SimpleNamespace(structured_output=extracted)
        ),
    )

    def evaluate(*, state, questions):
        return {
            "answers": {
                key: {
                    "choice": "no_match",
                    "confidence": 0.8,
                    "probabilities": {
                        "fixed": 0.05,
                        "installments": 0.05,
                        "movements": 0.1,
                        "no_match": 0.8,
                    },
                }
                for key in questions
            }
        }

    monkeypatch.setattr(
        module,
        "single_model_factory",
        lambda _: SimpleNamespace(evaluate=evaluate),
    )

    return build_workflow()


async def collect(graph, inputs):
    parts = graph.astream(
        inputs,
        config={"run_name": "trx_classifier"},
        stream_mode=["custom", "updates"],
        version="v2",
    )

    return [event async for event in workflow_events(parts)]


@pytest.mark.parametrize(
    "filename,content,output_type",
    [
        ("statement.pdf", b"%PDF-synthetic", "markdown"),
        ("statement.csv", b"description,amount\nCoffee,12.00", "text"),
    ],
)
def test_direct_and_streamed_results(workflow, filename, content, output_type):
    file = StatementFileInput.from_bytes(content, filename=filename)
    state = workflow.invoke({"file": file}, config={"run_name": "trx_classifier"})

    result = NormalizedStatement.model_validate(state["result"])

    assert state["step_durations"] == {"convert": 1, "extract": 1, "classify": 1}
    assert result.metrics.elapsed_seconds == 3
    assert result.transactions[0].report_bucket == "variable"

    events = asyncio.run(collect(workflow, {"file": file}))

    assert [event.event for event in events] == [
        "step_started",
        "step_completed",
    ] * 4 + ["result"]
    assert [event.data["step_id"] for event in events[:-1:2]] == [
        "convert",
        "extract",
        "classify",
        "complete",
    ]
    assert all(event.data["elapsed_seconds"] == 1 for event in events[1:-1:2])
    assert events[1].data["output_type"] == output_type
    assert events[3].data["output"]["transactions"][0]["date"] == "2026-10-08"
    assert events[5].data["output"]["model_calls"] == 1
    assert "output" not in events[7].data
    streamed = NormalizedStatement.model_validate(events[-1].data)

    assert streamed.statement == result.statement
    assert streamed.transactions == result.transactions
    assert streamed.metrics.elapsed_seconds == result.metrics.elapsed_seconds
    assert streamed.metrics.classification_model_calls == 1


def test_base64_input_retains_processing_duration(workflow):
    file = StatementFileInput.from_bytes(b"%PDF-synthetic", filename="statement.pdf")
    state = workflow.invoke(
        {"file_base64": file.to_base64(), "filename": file.filename}
    )

    assert state["result"].metrics.elapsed_seconds == 3
    assert state["step_durations"]["convert"] == 1


def test_missing_result_and_stream_cleanup():
    closed = []

    async def parts():
        try:
            yield {"type": "updates", "data": {"extract": {}}}
        finally:
            closed.append(True)

    async def consume():
        return [event async for event in workflow_events(parts())]

    with pytest.raises(RuntimeError, match="without a result"):
        asyncio.run(consume())

    assert closed == [True]


def test_closing_event_stream_closes_graph_stream():
    closed = []

    async def parts():
        try:
            yield {"type": "custom", "data": {"event": "step_started", "data": {}}}
            await asyncio.sleep(3600)
        finally:
            closed.append(True)

    async def consume():
        events = workflow_events(parts())

        await anext(events)

        await events.aclose()

    asyncio.run(consume())

    assert closed == [True]


@pytest.mark.parametrize("streaming", [False, True])
def test_cli_executes_graph_directly(
    workflow, monkeypatch, tmp_path, capsys, streaming
):
    import json

    import cli.main as cli

    file = tmp_path / "statement.csv"
    file.write_text("Coffee,12.00")
    arguments = ["trx-classify", str(file)]
    if streaming:
        arguments.append("--stream")

    monkeypatch.setattr(cli.sys, "argv", arguments)
    monkeypatch.setattr(cli, "build_workflow", lambda: workflow)

    cli.main()

    output = capsys.readouterr().out
    if streaming:
        events = [json.loads(line) for line in output.splitlines()]
        assert len(events) == 9
        assert events[-1]["event"] == "result"
        result = events[-1]["data"]
    else:
        result = json.loads(output)

    assert result["metrics"]["elapsed_seconds"] == 3
    assert result["transactions"][0]["amount"] == "12.00"
