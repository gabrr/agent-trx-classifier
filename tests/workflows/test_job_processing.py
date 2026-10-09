import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event, current_thread
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from api.app import create_app
from api.dependencies import (
    current_user,
    get_auth_service,
    require_task_caller,
)
from config import JobConfig
from db import models
from db.base import utc_now
from db.engine import create_database_engine
from db.repositories.users import synchronize_verified_profile
from db.session import session_factory
from services.jobs import job_service_factory
from tools.object_storage import ObjectStorage, StoredObject
from tools.task_queue import QueuedTask, TaskQueue, TaskQueueError, TaskTombstone
from workflows.job_processing.workflow import restore_checkpoint


class MemoryStorage(ObjectStorage):
    bucket_name = "private-test"

    def __init__(self):
        self.objects = {}

    def _upload(self, content, *, key, content_type, digest):
        self.objects[key] = content
        return StoredObject(
            self.bucket_name, key, 1, len(content), content_type, digest
        )

    def _download(self, key, *, generation):
        return self.objects[key]

    def _delete(self, key, *, generation):
        self.objects.pop(key, None)


class MemoryQueue(TaskQueue):
    def __init__(self):
        self.deliveries = {}
        self.failure = None

    def _enqueue(self, job_id, *, delivery_key):
        if self.failure:
            raise self.failure

        self.deliveries[delivery_key] = job_id
        return QueuedTask(delivery_key)


@pytest.fixture
def database():
    import os

    runtime = os.environ.get("DATABASE_URL")

    if not runtime:
        pytest.skip("Set DATABASE_URL for local trx_test")

    url = make_url(runtime)

    if url.database != "trx_test" or url.host not in {
        "localhost",
        "127.0.0.1",
        "db",
    }:
        pytest.fail("Job tests only allow isolated local trx_test")

    engine = create_database_engine(runtime)
    sessions = session_factory(engine)
    owners = [uuid4(), uuid4()]

    with sessions.begin() as session:
        for owner in owners:
            synchronize_verified_profile(session, owner)

    try:
        yield sessions, owners
    finally:
        with engine.begin() as session:
            job_ids = select(models.Job.id).where(models.Job.owner_id.in_(owners))
            statement_ids = select(models.Statement.id).where(
                models.Statement.owner_id.in_(owners)
            )
            session.execute(
                delete(models.Transaction).where(
                    models.Transaction.statement_id.in_(statement_ids)
                )
            )
            session.execute(
                delete(models.Statement).where(models.Statement.owner_id.in_(owners))
            )

            for model in (
                models.RunMetrics,
                models.Event,
                models.Checkpoint,
                models.Outbox,
            ):
                session.execute(delete(model).where(model.job_id.in_(job_ids)))

            session.execute(
                models.Job.__table__.update()
                .where(models.Job.owner_id.in_(owners))
                .values(active_attempt_id=None)
            )
            session.execute(
                delete(models.JobAttempt).where(models.JobAttempt.job_id.in_(job_ids))
            )
            session.execute(delete(models.Job).where(models.Job.owner_id.in_(owners)))
            session.execute(
                delete(models.UploadedFile).where(
                    models.UploadedFile.owner_id.in_(owners)
                )
            )
            session.execute(delete(models.User).where(models.User.id.in_(owners)))

        engine.dispose()


@pytest.fixture
def service(database, monkeypatch):
    import workflows.trx_classifier.workflow as module

    calls = {"convert": 0, "extract": 0, "classify": 0}
    failure = {"classify": False}

    def convert(*args, **kwargs):
        calls["convert"] += 1
        return "# Synthetic statement"

    def extract(*args):
        calls["extract"] += 1
        return SimpleNamespace(
            structured_output={
                "statement": {"kind": "unknown"},
                "transactions": [{"description": "Coffee", "amount": "12.00"}],
            }
        )

    def classify(*, state, questions):
        calls["classify"] += 1
        if failure["classify"]:
            raise RuntimeError("Synthetic temporary provider failure")

        return {
            "answers": {
                key: {
                    "choice": "no_match",
                    "confidence": 0.8,
                    "probabilities": {
                        "fixed": 0.05,
                        "installments": 0.05,
                        "movements": 0.1,
                        "no_match": 0.8,
                    },
                }
                for key in questions
            }
        }

    monkeypatch.setattr(module, "load_environment", lambda: None)
    monkeypatch.setattr(
        module, "file_to_markdown_factory", lambda _: SimpleNamespace(convert=convert)
    )
    monkeypatch.setattr(
        module, "llm_factory", lambda *args, **kwargs: SimpleNamespace(prompt=extract)
    )
    monkeypatch.setattr(
        module, "single_model_factory", lambda _: SimpleNamespace(evaluate=classify)
    )

    sessions, owners = database
    storage, queue = MemoryStorage(), MemoryQueue()
    settings = JobConfig(
        "private-test",
        "project",
        "region",
        "queue",
        "https://backend.example.com",
        "tasks@project.iam.gserviceaccount.com",
    )
    service = job_service_factory(
        sessions, storage, queue, settings, classifier_factory=module.build_workflow
    )

    return service, owners, calls, failure


def submit(service, owner, key="synthetic-submission"):
    return UUID(
        service.submit_job(owner, b"%PDF-synthetic", "synthetic.pdf", key)["id"]
    )


def test_checkpoint_types_restored():
    restored = restore_checkpoint(
        {
            "extracted": {"statement": {"kind": "unknown"}, "transactions": []},
            "batch": {"transactions": [], "elapsed_seconds": 1.0, "model_calls": 0},
        }
    )

    assert restored["extracted"].transactions == []
    assert restored["batch"].elapsed_seconds == 1


def test_duplicate_delivery_is_idempotent(service):
    jobs, owners, calls, _ = service
    job_id = submit(jobs, owners[0])

    assert asyncio.run(jobs.process_job(job_id)).status == "completed"
    assert asyncio.run(jobs.process_job(job_id)).status == "terminal"
    assert calls == {"convert": 1, "extract": 1, "classify": 1}
    assert jobs.get_result(owners[0], job_id)["transactions"][0]["amount"] == "12.00"

    with jobs.sessions() as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(models.Statement).where(
                            models.Statement.job_id == job_id
                        )
                    )
                )
            )
            == 1
        )


def test_compatible_checkpoint_resumed(service):
    jobs, owners, calls, failure = service
    job_id = submit(jobs, owners[0])
    failure["classify"] = True

    assert asyncio.run(jobs.process_job(job_id)).status == "retry"
    failure["classify"] = False
    assert asyncio.run(jobs.process_job(job_id)).status == "completed"
    assert calls == {"convert": 1, "extract": 1, "classify": 2}


def test_active_claim_is_not_acknowledged(service):
    jobs, owners, _, _ = service
    job_id = submit(jobs, owners[0])
    state, *_ = jobs.processor.claim_job(job_id)

    assert asyncio.run(jobs.process_job(job_id)).status == "busy"
    jobs.processor.record_failure(state, terminal=True, code="synthetic_cleanup")


def test_stale_attempt_cannot_commit(service):
    from db.repositories.jobs import StaleAttemptError

    jobs, owners, _, _ = service
    job_id = submit(jobs, owners[0])
    state, *_ = jobs.processor.claim_job(job_id)
    jobs.processor.save_progress(state, "step_started", {"step_id": "convert"})

    assert jobs.get_job(owners[0], job_id)["current_stage"] == "convert"
    jobs.processor.record_failure(state, terminal=True, code="processing_timeout")

    with pytest.raises(StaleAttemptError):
        jobs.processor.save_progress(state, "step_started", {"step_id": "convert"})

    assert jobs.get_job(owners[0], job_id)["status"] == "failed"


def test_failed_dispatch_remains_recoverable(service):
    jobs, owners, _, _ = service
    jobs.queue.failure = TaskQueueError("synthetic outage")
    job_id = submit(jobs, owners[0])

    with jobs.sessions.begin() as session:
        intent = session.scalar(
            select(models.Outbox).where(models.Outbox.job_id == job_id)
        )

        assert intent.dispatch_status == "pending"
        intent.next_attempt_at = utc_now() - timedelta(seconds=1)

    jobs.queue.failure = None
    assert jobs.dispatch_pending_jobs() == 1


def test_slow_dispatches_leave_connections_available(service, monkeypatch):
    jobs, owners, _, _ = service
    jobs.queue.failure = TaskQueueError("synthetic outage")
    job_ids = [submit(jobs, owners[0], key=f"slow-{index}") for index in range(2)]

    with jobs.sessions.begin() as session:
        for intent in session.scalars(
            select(models.Outbox).where(models.Outbox.job_id.in_(job_ids))
        ):
            intent.next_attempt_at = utc_now() - timedelta(seconds=1)

    entered = Barrier(3)
    release = Event()

    def slow_enqueue(job_id, *, delivery_key):
        entered.wait(timeout=10)

        if not release.wait(timeout=10):
            raise TimeoutError("Synthetic delivery was not released")

        return QueuedTask(delivery_key)

    monkeypatch.setattr(jobs.queue, "enqueue", slow_enqueue)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(jobs.dispatch_pending_jobs, job_id=job_id, limit=1)
            for job_id in job_ids
        ]
        try:
            entered.wait(timeout=10)

            assert jobs.get_job(owners[0], job_ids[0])["status"] == "queued"
        finally:
            release.set()

        assert [future.result(timeout=10) for future in futures] == [1, 1]


@pytest.mark.parametrize("failure_type", [TaskQueueError, TaskTombstone])
def test_late_dispatch_failure_preserves_success(service, monkeypatch, failure_type):
    jobs, owners, _, _ = service
    jobs.queue.failure = TaskQueueError("synthetic outage")
    job_id = submit(jobs, owners[0])

    with jobs.sessions.begin() as session:
        intent = session.scalar(
            select(models.Outbox).where(models.Outbox.job_id == job_id)
        )

        intent.next_attempt_at = utc_now() - timedelta(seconds=1)

    entered = Barrier(3)
    release_failure = Event()
    delivery_keys = []

    def concurrent_enqueue(job_id, *, delivery_key):
        delivery_keys.append(delivery_key)
        entered.wait(timeout=10)

        if current_thread().name.startswith("failure"):
            release_failure.wait(timeout=10)

            raise failure_type("Synthetic late failure")

        return QueuedTask(delivery_key)

    monkeypatch.setattr(jobs.queue, "enqueue", concurrent_enqueue)

    with (
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="success") as successful,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="failure") as failing,
    ):
        success = successful.submit(jobs.dispatch_pending_jobs, job_id=job_id)
        failure = failing.submit(jobs.dispatch_pending_jobs, job_id=job_id)
        try:
            entered.wait(timeout=10)

            assert success.result(timeout=10) == 1
        finally:
            release_failure.set()

        assert failure.result(timeout=10) == 0

    assert len(set(delivery_keys)) == 1
    with jobs.sessions() as session:
        intent = session.scalar(
            select(models.Outbox).where(models.Outbox.job_id == job_id)
        )

        assert intent.dispatch_status == "dispatched"
        assert intent.last_error is None


def test_tombstone_creates_new_durable_delivery(service):
    jobs, owners, _, _ = service
    jobs.queue.failure = TaskTombstone("synthetic already delivered unknown outcome")
    job_id = submit(jobs, owners[0])
    jobs.queue.failure = None

    assert jobs.dispatch_pending_jobs() == 1

    with jobs.sessions() as session:
        intents = list(
            session.scalars(select(models.Outbox).where(models.Outbox.job_id == job_id))
        )

        assert len(intents) == 2
        assert {intent.dispatch_status for intent in intents} == {
            "cancelled",
            "dispatched",
        }
        assert len({intent.task_name for intent in intents}) == 2


def test_idempotent_submission_and_owner_isolation(service):
    jobs, owners, _, _ = service
    job_id = submit(jobs, owners[0])

    assert submit(jobs, owners[0]) == job_id
    assert len(jobs.storage.objects) == 1

    with pytest.raises(ValueError):
        jobs.submit_job(
            owners[0], b"%PDF-different", "synthetic.pdf", "synthetic-submission"
        )

    with pytest.raises(LookupError):
        jobs.get_job(owners[1], job_id)


def test_due_finalization_not_starved_by_live_jobs(service):
    jobs, owners, _, _ = service
    for index in range(21):
        job_id = submit(jobs, owners[0], key=f"running-{index}")
        jobs.processor.claim_job(job_id)

    expired_id = submit(jobs, owners[0], key="expired")
    with jobs.sessions.begin() as session:
        expired = session.get(models.Job, expired_id)
        expired.deadline_at = utc_now() - timedelta(seconds=1)

    assert jobs.finalize_expired_jobs() == 1
    assert jobs.get_job(owners[0], expired_id)["status"] == "failed"


def test_api_ownership_and_internal_active_delivery(service):
    jobs, owners, _, _ = service
    principal = SimpleNamespace(id=owners[0])
    app = create_app(job_service=jobs, db_sessions=jobs.sessions)
    app.dependency_overrides[current_user] = lambda: principal
    app.dependency_overrides[require_task_caller] = lambda: None

    with TestClient(app) as client:
        response = client.post(
            "/api/jobs",
            files={"file": ("synthetic.pdf", b"%PDF-synthetic")},
            headers={"Idempotency-Key": "api-submission"},
        )

        assert response.status_code == 202
        job_id = UUID(response.json()["id"])

        assert client.get(f"/api/jobs/{job_id}").status_code == 200
        principal.id = owners[1]
        assert client.get(f"/api/jobs/{job_id}").status_code == 404
        assert (
            client.post(
                f"/api/jobs/{job_id}/retry", headers={"Idempotency-Key": "retry"}
            ).status_code
            == 404
        )
        state, *_ = jobs.processor.claim_job(job_id)

        assert (
            client.post("/internal/process", json={"job_id": str(job_id)}).status_code
            == 409
        )
        jobs.processor.record_failure(state, terminal=True, code="cleanup")


def test_terminal_sse_replays_ids_and_unsubscribes(service):
    from db.repositories.events import replay

    jobs, owners, _, _ = service
    job_id = submit(jobs, owners[0])
    asyncio.run(jobs.process_job(job_id))
    removed = []

    class ReplayListener:
        def subscribe(self, owner_id, job_id, callback, *, after_sequence):
            with jobs.sessions() as session:
                for event in replay(
                    session, owner_id, job_id, after_sequence=after_sequence
                ):
                    callback(event)

            return "subscription"

        def unsubscribe(self, token):
            removed.append(token)

    principal = SimpleNamespace(id=owners[0])
    app = create_app(
        job_service=jobs, db_sessions=jobs.sessions, job_listener=ReplayListener()
    )
    app.dependency_overrides[current_user] = lambda: principal
    app.dependency_overrides[get_auth_service] = lambda: SimpleNamespace(
        is_token_active=lambda _: True
    )

    with TestClient(app) as client:
        response = client.get(
            f"/api/jobs/{job_id}/events", headers={"Last-Event-ID": "1"}
        )

        assert response.status_code == 200
        assert "id: 1\n" not in response.text
        assert response.text.count("event: result\n") == 1
        assert removed == ["subscription"]


def test_explicit_retry_resumes_failed_job_and_preserves_history(service):
    jobs, owners, calls, failure = service
    original_id = submit(jobs, owners[0])
    failure["classify"] = True

    assert asyncio.run(jobs.process_job(original_id)).status == "retry"
    with jobs.sessions.begin() as session:
        original = session.get(models.Job, original_id)
        original.deadline_at = utc_now() - timedelta(seconds=1)

    assert jobs.finalize_expired_jobs() == 1
    failure["classify"] = False
    replacement_id = UUID(
        jobs.retry_job(owners[0], original_id, "retry-submission")["id"]
    )

    assert replacement_id != original_id
    assert (
        UUID(jobs.retry_job(owners[0], original_id, "retry-submission")["id"])
        == replacement_id
    )
    assert asyncio.run(jobs.process_job(replacement_id)).status == "completed"
    assert jobs.get_job(owners[0], original_id)["status"] == "failed"
    assert calls == {"convert": 1, "extract": 1, "classify": 2}
    assert len(jobs.storage.objects) == 1


def test_latest_delivery_controls_maintenance_eligibility(service):
    jobs, owners, _, _ = service
    for index in range(21):
        job_id = submit(jobs, owners[0], key=f"recent-recovery-{index}")
        with jobs.sessions.begin() as session:
            initial = session.scalar(
                select(models.Outbox).where(models.Outbox.job_id == job_id)
            )
            initial.dispatched_at = utc_now() - timedelta(minutes=10)
            session.add(
                models.Outbox(
                    job_id=job_id,
                    action="enqueue",
                    task_name=f"recent-{job_id}",
                    payload={"job_id": str(job_id)},
                    dispatch_status="dispatched",
                    retry_count=0,
                    dispatched_at=utc_now(),
                )
            )

    due_id = submit(jobs, owners[0], key="actually-due")
    with jobs.sessions.begin() as session:
        initial = session.scalar(
            select(models.Outbox).where(models.Outbox.job_id == due_id)
        )
        initial.dispatched_at = utc_now() - timedelta(minutes=10)

    jobs.finalize_expired_jobs()
    with jobs.sessions() as session:
        pending = list(
            session.scalars(
                select(models.Outbox).where(
                    models.Outbox.dispatch_status == "pending",
                    models.Outbox.job_id == due_id,
                )
            )
        )

        assert len(pending) == 1


def test_timeout_fences_late_synchronous_provider(service, monkeypatch):
    import time
    from dataclasses import replace

    import workflows.trx_classifier.workflow as module

    jobs, owners, _, _ = service
    original_factory = module.file_to_markdown_factory
    original_converter = original_factory("docling")

    def slow_convert(*args, **kwargs):
        time.sleep(0.35)
        return original_converter.convert(*args, **kwargs)

    monkeypatch.setattr(
        module,
        "file_to_markdown_factory",
        lambda _: SimpleNamespace(convert=slow_convert),
    )
    jobs.processor.settings = replace(jobs.settings, processing_timeout_seconds=2.15)
    job_id = submit(jobs, owners[0])

    assert asyncio.run(jobs.process_job(job_id)).status == "terminal"
    assert jobs.get_job(owners[0], job_id)["status"] == "failed"
    assert jobs.get_result(owners[0], job_id) is None
    with jobs.sessions() as session:
        recorded = list(
            session.scalars(
                select(models.Event)
                .where(models.Event.job_id == job_id)
                .order_by(models.Event.sequence)
            )
        )

        assert recorded[-1].event_type == "error"
        assert recorded[-1].data["code"] == "processing_timeout"
        assert all(event.event_type != "result" for event in recorded)


def test_default_classify_cannot_bypass_queue():
    app = create_app(db_sessions=object())
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(user_id=uuid4())

    with TestClient(app) as client:
        response = client.post(
            "/classify", files={"file": ("synthetic.pdf", b"%PDF-synthetic")}
        )

        assert response.status_code == 410


@pytest.mark.parametrize(
    "timeout,attempts,deadline",
    [(1800, 5, 7200), (0, 5, 7200), (1700, 0, 7200), (1700, 5, 0)],
)
def test_job_configuration_keeps_processing_bounded(timeout, attempts, deadline):
    with pytest.raises(ValueError):
        JobConfig(
            "private-test",
            "project",
            "region",
            "queue",
            "https://backend.example.com",
            "tasks@project.iam.gserviceaccount.com",
            processing_timeout_seconds=timeout,
            max_attempts=attempts,
            job_deadline_seconds=deadline,
        )
