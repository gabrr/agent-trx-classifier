from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class JobProcessingState:
    job_id: UUID
    owner_id: UUID
    attempt_id: UUID
    deadline_at: datetime
    checkpoint: dict
    input_fingerprint: str


@dataclass(frozen=True)
class JobProcessingOutcome:
    status: Literal["completed", "terminal", "busy", "retry"]
