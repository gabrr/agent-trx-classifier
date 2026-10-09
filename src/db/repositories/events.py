from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import Event

from .jobs import get_job, guard_attempt

TRX_EVENTS = {"step_started", "step_completed", "result", "error"}


def append_locked(session, job, event_type, data, attempt_id=None):
    """Internal helper: caller holds the job row lock through commit."""
    session.flush()

    sequence = (
        session.scalar(
            select(func.coalesce(func.max(Event.sequence), 0)).where(
                Event.job_id == job.id
            )
        )
        + 1
    )

    event = Event(
        job_id=job.id,
        sequence=sequence,
        attempt_id=attempt_id,
        event_type=event_type,
        data=data,
    )

    session.add(event)

    session.flush()

    session.execute(select(func.pg_notify("job_updates", str(job.id))))

    return event


def append_progress(session, owner_id, job_id, attempt_id, event_type, data):
    if event_type not in {"step_started", "step_completed"}:
        raise ValueError("Terminal events must use result/failure persistence")

    job = guard_attempt(session, owner_id, job_id, attempt_id)

    job.current_stage = data.get("step_id") or data.get("step")

    return append_locked(session, job, event_type, data, attempt_id)


def replay(session: Session, owner_id: UUID, job_id: UUID, *, after_sequence=0):
    get_job(session, owner_id, job_id)

    return list(
        session.scalars(
            select(Event)
            .where(Event.job_id == job_id, Event.sequence > after_sequence)
            .order_by(Event.sequence)
        )
    )
