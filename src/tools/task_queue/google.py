import hashlib
import json
import re
from threading import Lock
from urllib.parse import urlsplit
from uuid import UUID

from google.api_core.exceptions import AlreadyExists, GoogleAPICallError, NotFound
from google.auth.exceptions import GoogleAuthError
from google.cloud import tasks_v2
from google.protobuf.duration_pb2 import Duration

from .interface import (
    QueuedTask,
    TaskConflict,
    TaskQueue,
    TaskQueueError,
    TaskTombstone,
)


class GoogleTaskQueue(TaskQueue):
    """Google-authenticated HTTP deliveries to the configured backend."""

    def __init__(
        self,
        *,
        project_id: str,
        location: str,
        queue_name: str,
        backend_url: str,
        service_account_email: str,
        client=None,
    ):
        for value in (project_id, location, queue_name):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
                raise ValueError("Invalid Cloud Tasks resource identifier.")

        parsed = urlsplit(backend_url)

        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("backend_url must be an HTTPS origin.")

        if not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.iam\.gserviceaccount\.com", service_account_email
        ):
            raise ValueError("A Google service-account email is required.")

        self._queue = f"projects/{project_id}/locations/{location}/queues/{queue_name}"
        self._backend_url = backend_url.rstrip("/")

        self._service_account_email = service_account_email
        self._client = client
        self._client_lock = Lock()

    def _get_client(self):
        with self._client_lock:
            if self._client is None:
                try:
                    self._client = tasks_v2.CloudTasksClient()

                except GoogleAuthError as exc:
                    raise TaskQueueError(
                        "Cloud Tasks credentials are unavailable."
                    ) from exc

        return self._client

    def _enqueue(self, job_id: UUID, *, delivery_key: str) -> QueuedTask:
        suffix = hashlib.sha256(delivery_key.encode()).hexdigest()

        name = f"{self._queue}/tasks/{suffix}"
        body = json.dumps({"job_id": str(job_id)}, separators=(",", ":")).encode()

        request = tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=f"{self._backend_url}/internal/process",
            headers={"Content-Type": "application/json"},
            body=body,
            oidc_token=tasks_v2.OidcToken(
                service_account_email=self._service_account_email,
                audience=self._backend_url,
            ),
        )

        task = tasks_v2.Task(
            name=name, http_request=request, dispatch_deadline=Duration(seconds=1800)
        )

        client = self._get_client()

        try:
            client.create_task(
                request={"parent": self._queue, "task": task}, timeout=30, retry=None
            )

        except AlreadyExists:
            try:
                existing = client.get_task(
                    request={"name": name, "response_view": tasks_v2.Task.View.FULL},
                    timeout=30,
                    retry=None,
                )

            except NotFound as exc:
                raise TaskTombstone(
                    "Delivery name is reserved but the task cannot be confirmed."
                ) from exc

            except (GoogleAPICallError, GoogleAuthError) as exc:
                raise TaskQueueError("Cannot reconcile existing delivery.") from exc

            actual = existing.http_request

            if (
                actual.http_method != request.http_method
                or actual.url != request.url
                or actual.body != request.body
                or actual.oidc_token.audience != request.oidc_token.audience
                or actual.oidc_token.service_account_email
                != request.oidc_token.service_account_email
            ):
                raise TaskConflict(
                    "Delivery name refers to a different request."
                ) from None

        except (GoogleAPICallError, GoogleAuthError) as exc:
            raise TaskQueueError("Cloud Tasks dispatch failed.") from exc

        return QueuedTask(name=name)
