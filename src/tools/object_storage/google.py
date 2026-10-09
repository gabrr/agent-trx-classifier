from threading import Lock

from google.api_core.exceptions import GoogleAPICallError, NotFound, PreconditionFailed
from google.auth.exceptions import GoogleAuthError
from requests.exceptions import RequestException

from .interface import (
    ObjectStorage,
    StorageConflict,
    StorageError,
    StorageNotFound,
    StoredObject,
)


class GoogleObjectStorage(ObjectStorage):
    """Create-only objects in one bucket, with generation-fenced reads and deletes."""

    def __init__(self, *, bucket_name: str, client=None):
        if (
            not isinstance(bucket_name, str)
            or not bucket_name.strip()
            or "/" in bucket_name
        ):
            raise ValueError("bucket_name must be a configured bucket name.")

        self._bucket_name = bucket_name
        self._client = client
        self._client_lock = Lock()

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def _bucket(self):
        with self._client_lock:
            if self._client is None:
                from google.cloud import storage

                try:
                    self._client = storage.Client()

                except GoogleAuthError as exc:
                    raise StorageError("Storage credentials are unavailable.") from exc

        return self._client.bucket(self._bucket_name)

    def _upload(
        self, content: bytes, *, key: str, content_type: str, digest: str
    ) -> StoredObject:
        blob = self._bucket().blob(key)

        blob.metadata = {"sha256": digest}

        try:
            blob.upload_from_string(
                content,
                content_type=content_type,
                if_generation_match=0,
                timeout=60,
                retry=None,
                checksum="auto",
            )

        except PreconditionFailed:
            try:
                blob.reload(timeout=30, retry=None)

            except (GoogleAPICallError, GoogleAuthError, RequestException) as exc:
                raise StorageError("Cannot reconcile existing document.") from exc

            if (
                blob.size != len(content)
                or blob.content_type != content_type
                or (blob.metadata or {}).get("sha256") != digest
            ):
                raise StorageConflict(
                    "Existing document differs from upload."
                ) from None

        except (GoogleAPICallError, GoogleAuthError, RequestException) as exc:
            raise StorageError("Document upload failed.") from exc

        if blob.generation is None:
            raise StorageError("Upload did not return a generation.")

        return StoredObject(
            self._bucket_name,
            key,
            int(blob.generation),
            len(content),
            content_type,
            digest,
        )

    def _download(self, object_key: str, *, generation: int) -> bytes:
        blob = self._bucket().blob(object_key, generation=generation)

        try:
            blob.reload(if_generation_match=generation, timeout=30, retry=None)

            if blob.size is None or blob.size > self.MAX_FILE_BYTES:
                raise StorageError("Stored document exceeds the size limit.")

            return blob.download_as_bytes(
                if_generation_match=generation, timeout=60, retry=None, checksum="auto"
            )

        except NotFound as exc:
            raise StorageNotFound("Document generation was not found.") from exc

        except PreconditionFailed as exc:
            raise StorageConflict("Document generation changed.") from exc

        except (GoogleAPICallError, GoogleAuthError, RequestException) as exc:
            raise StorageError("Document download failed.") from exc

    def _delete(self, object_key: str, *, generation: int) -> None:
        blob = self._bucket().blob(object_key, generation=generation)

        try:
            blob.delete(if_generation_match=generation, timeout=30, retry=None)

        except NotFound:
            return

        except PreconditionFailed as exc:
            raise StorageConflict("Document generation changed.") from exc

        except (GoogleAPICallError, GoogleAuthError, RequestException) as exc:
            raise StorageError("Document deletion failed.") from exc
