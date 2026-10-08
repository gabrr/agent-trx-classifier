from datetime import timedelta

from sqlalchemy import select

from db.base import utc_now
from db.models import Job, Outbox


def pending_intents(session, owner_id, *, limit=100):
    """Lock due intents for a future dispatcher; retain the transaction until ack."""
    return list(
        session.scalars(
            select(Outbox)
            .join(Job, Job.id == Outbox.job_id)
            .where(
                Job.owner_id == owner_id,
                Outbox.dispatch_status == "pending",
                (Outbox.next_attempt_at.is_(None))
                | (Outbox.next_attempt_at <= utc_now()),
            )
            .order_by(Outbox.created_at)
            .limit(limit)
            .with_for_update(of=Outbox, skip_locked=True)
        )
    )


def record_dispatch(session, owner_id, intent_id, *, safe_error=None):
    intent = session.scalar(
        select(Outbox)
        .join(Job, Job.id == Outbox.job_id)
        .where(Job.owner_id == owner_id, Outbox.id == intent_id)
        .with_for_update(of=Outbox)
    )

    if intent is None:
        raise LookupError("Outbox intent not found")

    if intent.dispatch_status == "dispatched":
        return intent

    if safe_error:
        intent.retry_count += 1
        intent.last_error = safe_error
        intent.next_attempt_at = utc_now() + timedelta(
            seconds=min(2 ** min(intent.retry_count, 12), 3600)
        )

    else:
        intent.dispatch_status = "dispatched"
        intent.dispatched_at = utc_now()

        intent.last_error = None

    return intent
