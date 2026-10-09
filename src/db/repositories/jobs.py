from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import Batch, Job, JobAttempt, Outbox, UploadedFile


class StaleAttemptError(ValueError):
    pass


def get_job(session: Session, owner_id: UUID, job_id: UUID, *, lock=False) -> Job:
    query = select(Job).where(Job.id == job_id, Job.owner_id == owner_id)

    if lock:
        query = query.with_for_update()

    job = session.scalar(query)

    if job is None:
        raise LookupError("Job not found")

    return job


def guard_attempt(session: Session, owner_id: UUID, job_id: UUID, attempt_id: UUID):
    job = get_job(session, owner_id, job_id, lock=True)

    now = session.scalar(select(func.clock_timestamp()))

    if (
        job.status != "running"
        or job.active_attempt_id != attempt_id
        or job.claim_expires_at is None
        or job.claim_expires_at <= now
        or (job.deadline_at is not None and job.deadline_at <= now)
    ):
        raise StaleAttemptError("Attempt is no longer active")

    return job


def create_batch(session: Session, owner_id: UUID) -> Batch:
    batch = Batch(owner_id=owner_id)

    session.add(batch)

    session.flush()

    return batch


def create_job(
    session: Session,
    owner_id: UUID,
    uploaded_file_id: UUID,
    submission_key: str,
    *,
    batch_id: UUID | None = None,
    retry_of_job_id: UUID | None = None,
    deadline_at=None,
) -> Job:
    # Serialize submissions by owner; the unique constraint remains the backstop.
    from db.models import User

    if (
        session.scalar(select(User.id).where(User.id == owner_id).with_for_update())
        is None
    ):
        raise LookupError("User not found")

    file = session.scalar(
        select(UploadedFile).where(
            UploadedFile.id == uploaded_file_id, UploadedFile.owner_id == owner_id
        )
    )

    if file is None:
        raise LookupError("File not found")

    if (
        batch_id
        and session.scalar(
            select(Batch.id).where(Batch.id == batch_id, Batch.owner_id == owner_id)
        )
        is None
    ):
        raise LookupError("Batch not found")

    if retry_of_job_id:
        previous = get_job(session, owner_id, retry_of_job_id)

        if previous.status not in ("failed", "succeeded"):
            raise ValueError("Retry requires a terminal job")

    existing = session.scalar(
        select(Job).where(
            Job.owner_id == owner_id, Job.submission_key == submission_key
        )
    )

    if existing:
        if (existing.uploaded_file_id, existing.batch_id, existing.retry_of_job_id) != (
            uploaded_file_id,
            batch_id,
            retry_of_job_id,
        ):
            raise ValueError("Submission key already used for another submission")

        return existing

    job = Job(
        owner_id=owner_id,
        uploaded_file_id=uploaded_file_id,
        submission_key=submission_key,
        batch_id=batch_id,
        retry_of_job_id=retry_of_job_id,
        status="queued",
        deadline_at=deadline_at,
    )

    session.add(job)

    session.flush()

    session.add(
        Outbox(
            job_id=job.id,
            action="enqueue",
            task_name=f"trx-{job.id}",
            payload={"job_id": str(job.id)},
            dispatch_status="pending",
            retry_count=0,
        )
    )

    from .events import append_locked

    append_locked(session, job, "job_queued", {})

    return job


def claim_job(session: Session, owner_id: UUID, job_id: UUID, *, lease_seconds=300):
    if not 0 < lease_seconds <= 1800:
        raise ValueError("Lease must be between 1 and 1800 seconds")

    job = get_job(session, owner_id, job_id, lock=True)

    now = session.scalar(select(func.clock_timestamp()))

    if job.status in ("succeeded", "failed"):
        return None

    if job.deadline_at and job.deadline_at <= now:
        _fail_locked(session, job, "deadline_exceeded", "Processing deadline exceeded")

        return None

    if job.status == "running" and job.claim_expires_at and job.claim_expires_at > now:
        return None

    if job.active_attempt_id:
        old = session.get(JobAttempt, job.active_attempt_id)

        old.status = "failed"
        old.finished_at = now
        old.error_code = "claim_expired"

    number = (
        session.scalar(
            select(func.coalesce(func.max(JobAttempt.attempt_number), 0)).where(
                JobAttempt.job_id == job_id
            )
        )
        + 1
    )

    expiry = now + timedelta(seconds=lease_seconds)

    if job.deadline_at:
        expiry = min(expiry, job.deadline_at)

    attempt = JobAttempt(
        job_id=job_id,
        attempt_number=number,
        status="running",
        started_at=now,
        claim_expires_at=expiry,
    )

    session.add(attempt)

    session.flush()

    job.status = "running"
    job.active_attempt_id = attempt.id
    job.claim_expires_at = expiry
    job.started_at = job.started_at or now
    from .events import append_locked

    append_locked(session, job, "job_started", {}, attempt.id)

    return attempt


def renew_claim(
    session: Session,
    owner_id: UUID,
    job_id: UUID,
    attempt_id: UUID,
    *,
    lease_seconds=300,
):
    if not 0 < lease_seconds <= 1800:
        raise ValueError("Invalid lease")

    job = guard_attempt(session, owner_id, job_id, attempt_id)

    now = session.scalar(select(func.clock_timestamp()))

    expiry = now + timedelta(seconds=lease_seconds)

    if job.deadline_at:
        expiry = min(expiry, job.deadline_at)

    job.claim_expires_at = expiry
    session.get(JobAttempt, attempt_id).claim_expires_at = expiry


def _fail_locked(session, job, code, safe_reason, diagnostic_reference=None):
    now = session.scalar(select(func.clock_timestamp()))

    job.status = "failed"
    job.error_code = code
    job.error_reason = safe_reason
    job.diagnostic_reference = diagnostic_reference
    job.finished_at = now
    job.claim_expires_at = None
    if job.active_attempt_id:
        attempt = session.get(JobAttempt, job.active_attempt_id)

        attempt.status = "failed"
        attempt.error_code = code
        attempt.finished_at = now
        attempt.claim_expires_at = None

    from .events import append_locked

    append_locked(
        session,
        job,
        "error",
        {"code": code, "reason": safe_reason},
        job.active_attempt_id,
    )


def fail_job(
    session,
    owner_id,
    job_id,
    attempt_id,
    *,
    error_code,
    safe_reason,
    diagnostic_reference=None,
):
    job = guard_attempt(session, owner_id, job_id, attempt_id)

    _fail_locked(session, job, error_code, safe_reason, diagnostic_reference)


def recover_enqueue(session: Session, owner_id: UUID, job_id: UUID, *, max_attempts=3):
    """Durable intent for a later dispatcher; no provider or queue calls here."""
    job = get_job(session, owner_id, job_id, lock=True)

    now = session.scalar(select(func.clock_timestamp()))

    if job.status in ("succeeded", "failed"):
        return None

    if job.status == "running" and job.claim_expires_at and job.claim_expires_at > now:
        return None

    count = session.scalar(
        select(func.count()).select_from(JobAttempt).where(JobAttempt.job_id == job_id)
    )

    if count >= max_attempts or (job.deadline_at and job.deadline_at <= now):
        _fail_locked(
            session, job, "recovery_exhausted", "Processing could not complete"
        )

        return None

    intent = session.scalar(
        select(Outbox).where(Outbox.task_name == f"trx-{job.id}-recover-{count}")
    )

    if intent is None:
        intent = Outbox(
            job_id=job_id,
            action="enqueue",
            task_name=f"trx-{job.id}-recover-{count}",
            payload={"job_id": str(job_id)},
            dispatch_status="pending",
            retry_count=0,
        )

        session.add(intent)

    return intent


def internal_job_owner(session: Session, job_id: UUID) -> UUID:
    """Trusted service operation: never expose this lookup on user routes."""
    owner_id = session.scalar(select(Job.owner_id).where(Job.id == job_id))

    if owner_id is None:
        raise LookupError("Job not found")

    return owner_id


def release_attempt(session, owner_id, job_id, attempt_id, *, error_code):
    """Fence a transiently failed attempt while allowing a later delivery."""
    job = guard_attempt(session, owner_id, job_id, attempt_id)

    now = session.scalar(select(func.clock_timestamp()))

    attempt = session.get(JobAttempt, attempt_id)

    attempt.status = "failed"
    attempt.error_code = error_code
    attempt.finished_at = now
    attempt.claim_expires_at = None
    job.status = "queued"
    job.active_attempt_id = None
    job.claim_expires_at = None


def finalize_expired(session, job_id, *, max_attempts=5):
    owner_id = internal_job_owner(session, job_id)

    job = get_job(session, owner_id, job_id, lock=True)

    now = session.scalar(select(func.clock_timestamp()))

    if job.status in ("succeeded", "failed"):
        return False

    if job.deadline_at and job.deadline_at <= now:
        _fail_locked(
            session, job, "deadline_exceeded", "Processing timed out. Please try again."
        )

        return True

    if job.status == "running" and job.claim_expires_at and job.claim_expires_at > now:
        return False

    count = session.scalar(
        select(func.count()).select_from(JobAttempt).where(JobAttempt.job_id == job_id)
    )

    if count >= max_attempts:
        _fail_locked(
            session,
            job,
            "attempts_exhausted",
            "Processing could not complete. Please try again.",
        )

        return True

    return False
