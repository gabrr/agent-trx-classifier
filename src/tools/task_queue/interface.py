from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


class TaskQueueError(RuntimeError):
    """Dispatch failed or cannot be confirmed; keep the intent recoverable."""


class TaskTombstone(TaskQueueError):
    """A delivery name is reserved for a missing task; use a new persisted intent."""


class TaskConflict(TaskQueueError):
    """A delivery name already refers to a different request."""


@dataclass(frozen=True)
class QueuedTask:
    name: str


class TaskQueue(ABC):
    """Queue job references, using persisted identities for retry-safe dispatch."""

    def enqueue(self, job_id: UUID, *, delivery_key: str) -> QueuedTask:
        if not isinstance(job_id, UUID):
            raise TypeError("job_id must be a UUID.")

        if (
            not isinstance(delivery_key, str)
            or not delivery_key.strip()
            or len(delivery_key) > 500
        ):
            raise ValueError(
                "delivery_key must be a nonempty persisted key up to 500 characters."
            )

        return self._enqueue(job_id, delivery_key=delivery_key)

    @abstractmethod
    def _enqueue(self, job_id: UUID, *, delivery_key: str) -> QueuedTask:
        raise NotImplementedError
