from collections.abc import AsyncIterator, Callable
from time import perf_counter
from typing import Any, Literal

from langgraph.config import get_stream_writer
from pydantic import BaseModel, TypeAdapter

JSON = TypeAdapter(Any)


class WorkflowEvent(BaseModel):
    event: Literal["step_started", "step_completed", "result", "error"]
    data: dict[str, Any]


def json_output(value: Any) -> Any:
    return JSON.dump_python(value, mode="json")


def event_stream(
    operation: Callable[[dict], dict],
    *,
    step_id: str,
    name: str,
    output_key: str | None = None,
    output_type: str | Callable[[dict], str] = "json",
    record_duration: bool = True,
) -> Callable[[dict], dict]:
    """Emit progress and accumulate processing durations for a sequential graph."""

    def execute(state: dict) -> dict:
        writer = get_stream_writer()

        details = {"step_id": step_id, "name": name}
        writer({"event": "step_started", "data": details})

        started = perf_counter()

        update = operation(state)

        elapsed = perf_counter() - started
        resumed = output_key is not None and state.get(output_key) is not None
        if resumed:
            elapsed = state.get("step_durations", {}).get(step_id, 0.0)

        completed = {**details, "elapsed_seconds": elapsed}
        if resumed:
            completed["resumed"] = True

        if output_key is not None:
            completed["output_type"] = (
                output_type(state | update) if callable(output_type) else output_type
            )
            completed["output"] = json_output(update[output_key])

        writer({"event": "step_completed", "data": completed})

        if record_duration:
            return {
                **update,
                "step_durations": {
                    **state.get("step_durations", {}),
                    step_id: elapsed,
                },
            }

        return update

    return execute


async def workflow_events(parts: AsyncIterator[dict]) -> AsyncIterator[WorkflowEvent]:
    """Present an already-running graph stream as progress and one final result."""
    completed = False

    try:
        async for part in parts:
            if part["type"] == "custom":
                yield WorkflowEvent.model_validate(part["data"])

            elif part["type"] == "updates":
                update = part["data"].get("complete")

                if update and not completed:
                    completed = True

                    yield WorkflowEvent(
                        event="result", data=json_output(update["result"])
                    )

        if not completed:
            raise RuntimeError("Workflow ended without a result.")

    finally:
        await parts.aclose()
