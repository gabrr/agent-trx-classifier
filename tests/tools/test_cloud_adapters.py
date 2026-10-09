from uuid import uuid4

import pytest
from google.api_core.exceptions import AlreadyExists, NotFound, PreconditionFailed
from google.cloud import tasks_v2

from tools.object_storage import StorageConflict, object_storage_factory
from tools.task_queue import (
    TaskConflict,
    TaskQueueError,
    TaskTombstone,
    task_queue_factory,
)


class FakeBlob:
    def __init__(self):
        self.metadata = {}
        self.content_type = None
        self.size = None
        self.generation = None
        self.content = None
        self.upload_options = None
        self.delete_options = None

    def upload_from_string(self, content, **kwargs):
        self.upload_options = kwargs

        if self.generation is not None:
            raise PreconditionFailed("exists")

        self.content = content
        self.size = len(content)
        self.content_type = kwargs["content_type"]
        self.generation = 7

    def reload(self, **kwargs):
        if self.generation is None:
            raise NotFound("missing")

    def download_as_bytes(self, **kwargs):
        assert kwargs["if_generation_match"] == self.generation

        return self.content

    def delete(self, **kwargs):
        self.delete_options = kwargs
        raise NotFound("already deleted")


class FakeStorageClient:
    def __init__(self):
        self.objects = {}

    def bucket(self, name):
        assert name == "private-documents"

        return self

    def blob(self, name, generation=None):
        return self.objects.setdefault(name, FakeBlob())


class FakeTasksClient:
    def __init__(self):
        self.tasks = {}
        self.tombstone = False

    def create_task(self, request, **kwargs):
        assert kwargs == {"timeout": 30, "retry": None}

        task = request["task"]

        if task.name in self.tasks or self.tombstone:
            raise AlreadyExists("duplicate")

        self.tasks[task.name] = task

    def get_task(self, request, **kwargs):
        assert request["response_view"] == tasks_v2.Task.View.FULL

        if self.tombstone:
            raise NotFound("deleted")

        return self.tasks[request["name"]]


def make_queue(client):
    return task_queue_factory(
        project_id="project-123",
        location="us-central1",
        queue_name="processing",
        backend_url="https://backend.example",
        service_account_email="tasks@project-123.iam.gserviceaccount.com",
        client=client,
    )


def test_storage_immutable_upload_pinned_read_and_delete():
    client = FakeStorageClient()
    storage = object_storage_factory(bucket_name="private-documents", client=client)
    arguments = {
        "owner_id": uuid4(),
        "upload_id": uuid4(),
        "filename": "../../statement.pdf",
    }
    stored = storage.upload(b"document", **arguments)
    repeated = storage.upload(b"document", **arguments)

    assert stored == repeated
    assert stored.bucket_name == "private-documents"
    assert "statement" not in stored.key
    assert storage.download(stored.key, generation=stored.generation) == b"document"
    assert client.objects[stored.key].upload_options["if_generation_match"] == 0

    storage.delete(stored.key, generation=stored.generation)

    assert client.objects[stored.key].delete_options["if_generation_match"] == 7


def test_storage_rejects_corrupt_existing_object():
    client = FakeStorageClient()
    storage = object_storage_factory(bucket_name="private-documents", client=client)
    arguments = {"owner_id": uuid4(), "upload_id": uuid4(), "filename": "statement.csv"}
    stored = storage.upload(b"document", **arguments)
    client.objects[stored.key].content_type = "application/octet-stream"

    with pytest.raises(StorageConflict):
        storage.upload(b"document", **arguments)

    client.objects[stored.key].content = b"tampered"

    with pytest.raises(StorageConflict):
        storage.download(stored.key, generation=7)


def test_storage_rejects_untrusted_references():
    storage = object_storage_factory(
        bucket_name="private-documents", client=FakeStorageClient()
    )

    with pytest.raises(ValueError):
        storage.download("../../secret", generation=1)

    with pytest.raises(ValueError):
        storage.upload(
            b"", owner_id=uuid4(), upload_id=uuid4(), filename="statement.pdf"
        )


def test_tasks_duplicate_reconciles_and_distinct_recovery_delivers():
    client = FakeTasksClient()
    queue = make_queue(client)
    job_id = uuid4()
    first = queue.enqueue(job_id, delivery_key="initial-intent")

    assert queue.enqueue(job_id, delivery_key="initial-intent") == first
    assert queue.enqueue(job_id, delivery_key="recovery-intent") != first
    task = client.tasks[first.name]

    assert task.dispatch_deadline.seconds == 1800
    assert task.http_request.oidc_token.audience == "https://backend.example"
    assert task.http_request.body == f'{{"job_id":"{job_id}"}}'.encode()


def test_tasks_duplicate_conflicting_payload_rejected():
    client = FakeTasksClient()
    queue = make_queue(client)
    queue.enqueue(uuid4(), delivery_key="intent")

    with pytest.raises(TaskConflict):
        queue.enqueue(uuid4(), delivery_key="intent")


def test_tasks_tombstone_remains_recoverable():
    client = FakeTasksClient()
    client.tombstone = True

    with pytest.raises(TaskTombstone, match="reserved"):
        make_queue(client).enqueue(uuid4(), delivery_key="intent")


def test_factories_do_not_resolve_credentials(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("must not initialize SDK client")

    monkeypatch.setattr(tasks_v2, "CloudTasksClient", fail)
    queue = make_queue(None)
    storage = object_storage_factory(bucket_name="private-documents")

    assert queue._client is None
    assert storage._client is None


def test_queue_requires_fixed_https_origin():
    with pytest.raises(ValueError, match="HTTPS origin"):
        task_queue_factory(
            project_id="project",
            location="region",
            queue_name="queue",
            backend_url="https://backend.example/another-path",
            service_account_email="tasks@project.iam.gserviceaccount.com",
        )


def test_provider_authentication_failures_remain_recoverable(monkeypatch):
    from google.auth.exceptions import DefaultCredentialsError, RefreshError
    from google.cloud import storage as storage_sdk

    from tools.object_storage import StorageError

    def no_credentials(*args, **kwargs):
        raise DefaultCredentialsError("missing")

    monkeypatch.setattr(storage_sdk, "Client", no_credentials)
    storage = object_storage_factory(bucket_name="private-documents")

    with pytest.raises(StorageError, match="credentials"):
        storage.upload(
            b"document", owner_id=uuid4(), upload_id=uuid4(), filename="statement.pdf"
        )

    def cannot_refresh(*args, **kwargs):
        raise RefreshError("expired")

    client = FakeTasksClient()
    monkeypatch.setattr(client, "create_task", cannot_refresh)

    with pytest.raises(TaskQueueError, match="dispatch failed"):
        make_queue(client).enqueue(uuid4(), delivery_key="intent")
