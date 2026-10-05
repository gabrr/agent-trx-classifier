from typing import Any, Literal

from pydantic import BaseModel, TypeAdapter

JSON = TypeAdapter(Any)


class WorkflowEvent(BaseModel):
    event: Literal["step_started", "step_completed", "result", "error"]
    data: dict[str, Any]


def json_output(value: Any) -> Any:
    return JSON.dump_python(value, mode="json")
