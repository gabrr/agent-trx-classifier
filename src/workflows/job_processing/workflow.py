import asyncio
import hashlib
import logging
from datetime import timedelta
from pathlib import Path

from pydantic import TypeAdapter
from sqlalchemy import func, select

from config import JobConfig
from db.base import utc_now
from db.models import JobAttempt
from db.repositories import checkpoints, events, files, jobs, results
from tools.event_stream import json_output
from tools.statement_file import StatementFileInput
from workflows.trx_classifier.classification import ClassificationBatch
from workflows.trx_classifier.models import ExtractedStatement, NormalizedStatement

from .models import JobProcessingOutcome, JobProcessingState

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1"
MODEL_VERSION = "openrouter:google/gemini-3.8-flash|typesafe:jev-latest"


def workflow_fingerprint():
    """Invalidate snapshots when workflow, prompts, criteria or contracts change."""
    digest = hashlib.sha256(MODEL_VERSION.encode())

    directory = Path(__file__).parents[1] / "trx_classifier"
    for name in (
        "workflow.py",
        "prompts.py",
        "criteria.py",
        "classification.py",
        "models.py",
    ):
        digest.update((directory / name).read_bytes())

    source = Path(__file__).parents[2]
    digest.update((source / "config.py").read_bytes())

    digest.update((source / "tools" / "event_stream.py").read_bytes())

    for package in ("llm", "single_model", "file_to_markdown", "statement_file"):
        for path in sorted((source / "tools" / package).glob("*.py")):
            digest.update(path.read_bytes())

    return digest.hexdigest()


def restore_checkpoint(snapshot):
    restored = dict(snapshot or {})

    if "extracted" in restored:
        restored["extracted"] = ExtractedStatement.model_validate(restored["extracted"])

    if "batch" in restored:
        restored["batch"] = TypeAdapter(ClassificationBatch).validate_python(
            restored["batch"]
        )

    return restored


class JobProcessor:
    """Durable wrapper around the existing classifier graph; no HTTP concerns."""

    def __init__(
        self, sessions, storage, settings: JobConfig, *, classifier_factory=None
    ):
        self.sessions = sessions
        self.storage = storage
        self.settings = settings
        if classifier_factory is None:
            from workflows.trx_classifier.workflow import (
                build_workflow as classifier_factory,
            )

        self.classifier_factory = classifier_factory
        self.version = workflow_fingerprint()

    def claim_job(self, job_id):
        with self.sessions.begin() as session:
            owner_id = jobs.internal_job_owner(session, job_id)

            job = jobs.get_job(session, owner_id, job_id, lock=True)

            if job.status in ("succeeded", "failed"):
                return JobProcessingOutcome("terminal")

            now = session.scalar(select(func.clock_timestamp()))

            if (
                job.status == "running"
                and job.claim_expires_at
                and job.claim_expires_at > now
            ):
                return JobProcessingOutcome("busy")

            if jobs.finalize_expired(
                session, job_id, max_attempts=self.settings.max_attempts
            ):
                return JobProcessingOutcome("terminal")

            # A processing timeout permanently fences this run; no automatic continuation.
            processing_deadline = now + timedelta(
                seconds=self.settings.processing_timeout_seconds
            )

            job.deadline_at = (
                min(job.deadline_at, processing_deadline)
                if job.deadline_at
                else processing_deadline
            )

            attempt = jobs.claim_job(session, owner_id, job_id, lease_seconds=1800)

            if attempt is None:
                return JobProcessingOutcome("terminal")

            uploaded = files.get_file(session, owner_id, job.uploaded_file_id)

            if uploaded.storage_bucket != self.storage.bucket_name:
                raise ValueError("Stored file belongs to another configured bucket")

            fingerprint = f"{uploaded.checksum}:{uploaded.storage_object}:{uploaded.storage_generation}"
            snapshot = {}
            for stage in ("classify", "extract", "convert"):
                checkpoint = checkpoints.compatible_checkpoint(
                    session,
                    owner_id,
                    job_id,
                    stage=stage,
                    input_fingerprint=fingerprint,
                    workflow_version=self.version,
                    model_version=MODEL_VERSION,
                    schema_version=SCHEMA_VERSION,
                )

                if checkpoint is None and job.retry_of_job_id:
                    checkpoint = checkpoints.compatible_checkpoint(
                        session,
                        owner_id,
                        job_id,
                        stage=stage,
                        input_fingerprint=fingerprint,
                        workflow_version=self.version,
                        model_version=MODEL_VERSION,
                        schema_version=SCHEMA_VERSION,
                        source_job_id=job.retry_of_job_id,
                    )

                if checkpoint is not None:
                    snapshot = checkpoint.output
                    break

            state = JobProcessingState(
                job_id, owner_id, attempt.id, job.deadline_at, snapshot, fingerprint
            )

            return (
                state,
                uploaded.storage_object,
                int(uploaded.storage_generation),
                uploaded.filename,
            )

    def load_document(self, key, generation, filename):
        content = self.storage.download(key, generation=generation)

        return StatementFileInput.from_bytes(content, filename=filename)

    def save_progress(self, state, event_type, data):
        with self.sessions.begin() as session:
            events.append_progress(
                session,
                state.owner_id,
                state.job_id,
                state.attempt_id,
                event_type,
                data,
            )

    def save_checkpoint(self, state, stage, snapshot):
        with self.sessions.begin() as session:
            checkpoints.save_checkpoint(
                session,
                state.owner_id,
                state.job_id,
                state.attempt_id,
                stage=stage,
                input_fingerprint=state.input_fingerprint,
                workflow_version=self.version,
                model_version=MODEL_VERSION,
                schema_version=SCHEMA_VERSION,
                output=json_output(snapshot),
            )

    async def run_classifier(self, state, document):
        graph = await asyncio.to_thread(self.classifier_factory)

        snapshot = restore_checkpoint(state.checkpoint)

        snapshot["file"] = document
        parts = graph.astream(
            snapshot,
            config={"run_name": "trx_classifier"},
            stream_mode=["custom", "updates"],
            version="v2",
        )

        result = None
        try:
            async for part in parts:
                if part["type"] == "custom":
                    event = part["data"]
                    await asyncio.to_thread(
                        self.save_progress, state, event["event"], event["data"]
                    )

                elif part["type"] == "updates":
                    for stage, update in part["data"].items():
                        if not update:
                            continue

                        snapshot.update(update)

                        if stage == "complete":
                            result = NormalizedStatement.model_validate(
                                update["result"]
                            )

                        elif stage in ("convert", "extract", "classify"):
                            serializable = {
                                key: value
                                for key, value in snapshot.items()
                                if key not in {"file", "file_base64", "result"}
                            }
                            await asyncio.to_thread(
                                self.save_checkpoint, state, stage, serializable
                            )

        finally:
            await parts.aclose()

        if result is None:
            raise RuntimeError("Classifier completed without a result")

        return result

    def complete_job(self, state, result):
        with self.sessions.begin() as session:
            results.complete_job(
                session, state.owner_id, state.job_id, state.attempt_id, result
            )

    def record_failure(self, state, *, terminal, code):
        with self.sessions.begin() as session:
            # Timeout cleanup must work even after the lease/deadline expired.
            job = jobs.get_job(session, state.owner_id, state.job_id, lock=True)

            if job.status != "running" or job.active_attempt_id != state.attempt_id:
                return JobProcessingOutcome(
                    "terminal" if job.status in ("failed", "succeeded") else "retry"
                )

            count = session.scalar(
                select(func.count())
                .select_from(JobAttempt)
                .where(JobAttempt.job_id == state.job_id)
            )

            if (
                terminal
                or count >= self.settings.max_attempts
                or job.deadline_at <= utc_now()
            ):
                reason = (
                    "Processing timed out. Please try again."
                    if code == "processing_timeout"
                    else "Processing could not complete. Please try again."
                )

                jobs._fail_locked(session, job, code, reason)

                return JobProcessingOutcome("terminal")

            jobs.release_attempt(
                session, state.owner_id, state.job_id, state.attempt_id, error_code=code
            )

            return JobProcessingOutcome("retry")

    async def process_job(self, job_id):
        claimed = await asyncio.to_thread(self.claim_job, job_id)

        if isinstance(claimed, JobProcessingOutcome):
            return claimed

        state, key, generation, filename = claimed
        try:
            remaining = max(0.01, (state.deadline_at - utc_now()).total_seconds() - 2)

            async with asyncio.timeout(remaining):
                document = await asyncio.to_thread(
                    self.load_document, key, generation, filename
                )

                result = await self.run_classifier(state, document)

                await asyncio.to_thread(self.complete_job, state, result)

            return JobProcessingOutcome("completed")

        except asyncio.CancelledError:
            # Sync provider calls may survive cancellation; only this coroutine writes DB state.
            await asyncio.shield(
                asyncio.to_thread(
                    self.record_failure,
                    state,
                    terminal=True,
                    code="processing_cancelled",
                )
            )

            raise

        except TimeoutError:
            return await asyncio.to_thread(
                self.record_failure, state, terminal=True, code="processing_timeout"
            )

        except jobs.StaleAttemptError:
            return JobProcessingOutcome("retry")

        except Exception as error:
            logger.warning(
                "Job processing failed",
                extra={"job_id": str(job_id), "error_type": type(error).__name__},
            )

            return await asyncio.to_thread(
                self.record_failure,
                state,
                terminal=isinstance(error, ValueError),
                code="processing_failed",
            )


def build_workflow(sessions, storage, settings, *, classifier_factory=None):
    return JobProcessor(
        sessions, storage, settings, classifier_factory=classifier_factory
    )
