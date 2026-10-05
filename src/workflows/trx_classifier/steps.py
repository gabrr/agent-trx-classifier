from collections.abc import Callable
from time import perf_counter

from langgraph.config import get_stream_writer

from runtime.events import json_output

from .state import ClassifierState


def workflow_step(
    step_id: str,
    name: str,
    output_key: str,
    operation: Callable[[ClassifierState], dict],
    *,
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
