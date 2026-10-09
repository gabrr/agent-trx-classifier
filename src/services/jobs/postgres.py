import hashlib
import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from config import JobConfig
from db.base import utc_now
from db.models import Job, JobAttempt, Outbox, User
from db.repositories import files, jobs, outbox, results
from tools.statement_file import StatementFileInput
from tools.task_queue import TaskTombstone
from workflows.job_processing import build_workflow

from .interface import JobService

logger = logging.getLogger(__name__)


def job_response(job):
    return {
        "id": str(job.id),
        "status": job.status,
        "current_stage": job.current_stage,
        "created_at": job.created_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_code": job.error_code,
        "error_reason": job.error_reason,
        "retry_of_job_id": str(job.retry_of_job_id) if job.retry_of_job_id else None,
    }


class PostgresJobService(JobService):
    def __init__(
        self, sessions, storage, queue, settings: JobConfig, *, classifier_factory=None
    ):
        self.sessions = sessions
        self.storage = storage
        self.queue = queue
        self.settings = settings
        self.processor = build_workflow(
            sessions, storage, settings, classifier_factory=classifier_factory
        )

    def _existing_submission(self, session, owner_id, submission_key):
        return session.scalar(
            select(Job).where(
                Job.owner_id == owner_id, Job.submission_key == submission_key
            )
        )

    def _validate_same_submission(
        self, session, owner_id, job, document, *, retry_of=None
    ):
        uploaded = files.get_file(session, owner_id, job.uploaded_file_id)

        if (
            uploaded.checksum != hashlib.sha256(document.content).hexdigest()
            or uploaded.filename != document.filename
            or job.retry_of_job_id != retry_of
        ):
            raise ValueError("Submission key already used for a different submission")

    def submit_job(self, owner_id, content, filename, submission_key):
        if not isinstance(submission_key, str) or not 1 <= len(submission_key) <= 128:
            raise ValueError("A submission key of at most 128 characters is required")

        document = StatementFileInput.from_bytes(content, filename=filename)

        with self.sessions() as session:
            existing = self._existing_submission(session, owner_id, submission_key)

            if existing:
                self._validate_same_submission(session, owner_id, existing, document)

                return job_response(existing)

        stored = self.storage.upload(
            document.content,
            owner_id=owner_id,
            upload_id=uuid4(),
            filename=document.filename,
        )

        unused = False
        # A failed/uncertain DB commit leaves a private object for retention cleanup;
        # deleting here could destroy an object referenced by a committed transaction.
        with self.sessions.begin() as session:
            session.scalar(select(User.id).where(User.id == owner_id).with_for_update())

            existing = self._existing_submission(session, owner_id, submission_key)

            if existing:
                self._validate_same_submission(session, owner_id, existing, document)

                response = job_response(existing)

                unused = True
            else:
                uploaded = files.create_file(
                    session,
                    owner_id,
                    filename=document.filename,
                    content_type=stored.content_type,
                    size_bytes=stored.size_bytes,
                    storage_bucket=stored.bucket_name,
                    storage_object=stored.key,
                    storage_generation=str(stored.generation),
                    checksum=stored.sha256,
                )

                job = jobs.create_job(
                    session,
                    owner_id,
                    uploaded.id,
                    submission_key,
                    deadline_at=utc_now()
                    + timedelta(seconds=self.settings.job_deadline_seconds),
                )

                response = job_response(job)

        if unused:
            try:
                self.storage.delete(stored.key, generation=stored.generation)

            except Exception:
                logger.warning("Unused private upload requires retention cleanup")

        self.dispatch_pending_jobs(
            owner_id=owner_id, job_id=job.id if not unused else existing.id, limit=1
        )

        return response

    def get_job(self, owner_id, job_id):
        with self.sessions() as session:
            return job_response(jobs.get_job(session, owner_id, job_id))

    def get_result(self, owner_id, job_id):
        with self.sessions() as session:
            result = results.get_result(session, owner_id, job_id)

            return result.model_dump(mode="json") if result else None

    def retry_job(self, owner_id, job_id, submission_key):
        if not isinstance(submission_key, str) or not 1 <= len(submission_key) <= 128:
            raise ValueError("A submission key of at most 128 characters is required")

        with self.sessions.begin() as session:
            previous = jobs.get_job(session, owner_id, job_id)

            if previous.status != "failed":
                raise ValueError("Only failed jobs can be retried")

            session.scalar(select(User.id).where(User.id == owner_id).with_for_update())

            existing = self._existing_submission(session, owner_id, submission_key)

            if existing and (
                existing.retry_of_job_id != job_id
                or existing.uploaded_file_id != previous.uploaded_file_id
            ):
                raise ValueError(
                    "Submission key already used for a different submission"
                )

            job = existing or jobs.create_job(
                session,
                owner_id,
                previous.uploaded_file_id,
                submission_key,
                retry_of_job_id=job_id,
                deadline_at=utc_now()
                + timedelta(seconds=self.settings.job_deadline_seconds),
            )

            response = job_response(job)

        self.dispatch_pending_jobs(owner_id=owner_id, job_id=job.id, limit=1)

        return response

    def dispatch_pending_jobs(self, *, owner_id=None, job_id=None, limit=20):
        limit = min(max(limit, 1), 20)

        query = (
            select(Outbox.id)
            .join(Job, Job.id == Outbox.job_id)
            .where(
                Outbox.dispatch_status == "pending",
                (Outbox.next_attempt_at.is_(None))
                | (Outbox.next_attempt_at <= utc_now()),
            )
        )

        if owner_id is not None:
            query = query.where(Job.owner_id == owner_id)

        if job_id is not None:
            query = query.where(Job.id == job_id)

        with self.sessions() as session:
            intent_ids = list(
                session.scalars(query.order_by(Outbox.created_at).limit(limit))
            )

        dispatched = 0
        for intent_id in intent_ids:
            with self.sessions.begin() as session:
                intent = session.scalar(
                    select(Outbox)
                    .where(Outbox.id == intent_id, Outbox.dispatch_status == "pending")
                    .with_for_update(skip_locked=True)
                )

                if intent is None:
                    continue

                job = session.get(Job, intent.job_id)

                if job.status in ("succeeded", "failed"):
                    intent.dispatch_status = "cancelled"
                    continue

                delivery_job_id = job.id
                delivery_owner_id = job.owner_id
                delivery_key = intent.task_name

            # The persisted delivery key makes concurrent sends retry-safe.
            # No database connection or row lock is held during the queue call.
            dispatch_error = None
            try:
                self.queue.enqueue(delivery_job_id, delivery_key=delivery_key)

            except TaskTombstone:
                dispatch_error = "delivery_tombstone"

            except Exception:
                # SDK errors can contain credentials; persist only a safe code.
                dispatch_error = "dispatch_unavailable"

            with self.sessions.begin() as session:
                job = jobs.get_job(
                    session, delivery_owner_id, delivery_job_id, lock=True
                )

                intent = session.scalar(
                    select(Outbox).where(Outbox.id == intent_id).with_for_update()
                )

                # Another dispatcher may already have finalized this intent.
                if intent is None or intent.dispatch_status != "pending":
                    continue

                if job.status in ("succeeded", "failed"):
                    intent.dispatch_status = "cancelled"
                    continue

                if dispatch_error == "delivery_tombstone":
                    intent.dispatch_status = "cancelled"
                    intent.last_error = dispatch_error
                    if (
                        intent.retry_count >= self.settings.max_attempts
                        and job.status == "queued"
                    ):
                        jobs._fail_locked(
                            session,
                            job,
                            "delivery_exhausted",
                            "Processing could not start. Please try again.",
                        )

                    else:
                        session.add(
                            Outbox(
                                job_id=job.id,
                                action="enqueue",
                                task_name=f"trx-{job.id}-transport-{uuid4()}",
                                payload={"job_id": str(job.id)},
                                dispatch_status="pending",
                                retry_count=intent.retry_count + 1,
                            )
                        )

                elif dispatch_error:
                    outbox.record_dispatch(
                        session,
                        delivery_owner_id,
                        intent.id,
                        safe_error=dispatch_error,
                    )

                else:
                    outbox.record_dispatch(session, delivery_owner_id, intent.id)

                    dispatched += 1

        return dispatched

    def finalize_expired_jobs(self, *, limit=20):
        now = utc_now()

        pending = (
            select(Outbox.id)
            .where(Outbox.job_id == Job.id, Outbox.dispatch_status == "pending")
            .exists()
        )

        latest_delivery = (
            select(func.max(func.coalesce(Outbox.dispatched_at, Outbox.created_at)))
            .where(
                Outbox.job_id == Job.id,
                Outbox.dispatch_status.in_(["dispatched", "cancelled"]),
            )
            .scalar_subquery()
        )

        stale_delivery = latest_delivery < now - timedelta(minutes=5)

        with self.sessions() as session:
            ids = list(
                session.scalars(
                    select(Job.id)
                    .where(
                        Job.status.in_(["queued", "running"]),
                        (Job.deadline_at <= now)
                        | ((Job.status == "running") & (Job.claim_expires_at <= now))
                        | ((Job.status == "queued") & ~pending & stale_delivery),
                    )
                    .order_by(Job.deadline_at)
                    .limit(min(limit, 20))
                )
            )

        finalized = 0
        for job_id in ids:
            with self.sessions.begin() as session:
                if jobs.finalize_expired(
                    session, job_id, max_attempts=self.settings.max_attempts
                ):
                    finalized += 1
                    continue

                owner_id = jobs.internal_job_owner(session, job_id)

                job = jobs.get_job(session, owner_id, job_id, lock=True)

                if (
                    job.status == "running"
                    and job.claim_expires_at
                    and job.claim_expires_at <= utc_now()
                ):
                    jobs.recover_enqueue(
                        session,
                        owner_id,
                        job_id,
                        max_attempts=self.settings.max_attempts,
                    )

                elif job.status == "queued":
                    attempts = session.scalar(
                        select(func.count())
                        .select_from(JobAttempt)
                        .where(JobAttempt.job_id == job_id)
                    )

                    pending = session.scalar(
                        select(Outbox.id)
                        .where(
                            Outbox.job_id == job_id, Outbox.dispatch_status == "pending"
                        )
                        .limit(1)
                    )

                    latest = session.scalar(
                        select(func.coalesce(Outbox.dispatched_at, Outbox.created_at))
                        .where(
                            Outbox.job_id == job_id,
                            Outbox.dispatch_status.in_(["dispatched", "cancelled"]),
                        )
                        .order_by(
                            func.coalesce(
                                Outbox.dispatched_at, Outbox.created_at
                            ).desc()
                        )
                        .limit(1)
                    )

                    # Recover a dispatched delivery lost before the first claim too.
                    if (
                        pending is None
                        and latest
                        and latest < utc_now() - timedelta(minutes=5)
                    ):
                        intent = jobs.recover_enqueue(
                            session,
                            owner_id,
                            job_id,
                            max_attempts=self.settings.max_attempts,
                        )

                        if intent and intent.dispatch_status == "dispatched":
                            # Same attempt count but another transport retry exhaustion:
                            # new delivery key preserves deterministic enqueue reconciliation.
                            session.add(
                                Outbox(
                                    job_id=job_id,
                                    action="enqueue",
                                    task_name=f"trx-{job_id}-recover-{attempts}-{uuid4()}",
                                    payload={"job_id": str(job_id)},
                                    dispatch_status="pending",
                                    retry_count=0,
                                )
                            )

        return finalized

    def run_maintenance(self):
        finalized = self.finalize_expired_jobs()

        dispatched = self.dispatch_pending_jobs()

        return {"finalized": finalized, "dispatched": dispatched}

    async def process_job(self, job_id):
        return await self.processor.process_job(job_id)
