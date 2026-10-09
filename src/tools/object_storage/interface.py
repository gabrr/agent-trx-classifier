import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePath
from uuid import UUID


class StorageError(RuntimeError):
    """Storage failed; the application decides whether to retry."""


class StorageConflict(StorageError):
    """An immutable object differs from the requested object."""


class StorageNotFound(StorageError):
    """The requested object generation no longer exists."""


@dataclass(frozen=True)
class StoredObject:
    bucket_name: str
    key: str
    generation: int
    size_bytes: int
    content_type: str
    sha256: str


class ObjectStorage(ABC):
    """Private document storage; callers authorize ownership before access."""

    MAX_FILE_BYTES = 25 * 1024 * 1024
    KEY_PATTERN = re.compile(
        r"documents/[0-9a-f-]{36}/[0-9a-f-]{36}/[0-9a-f]{64}\.(pdf|csv)"
    )

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        """The fixed configured bucket used by this provider."""
        raise NotImplementedError

    def upload(
        self, content: bytes, *, owner_id: UUID, upload_id: UUID, filename: str
    ) -> StoredObject:
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes.")

        if not content or len(content) > self.MAX_FILE_BYTES:
            raise ValueError("Document must contain between 1 byte and 25 MiB.")

        if not isinstance(owner_id, UUID) or not isinstance(upload_id, UUID):
            raise TypeError("owner_id and upload_id must be UUIDs.")

        if not isinstance(filename, str):
            raise TypeError("filename must be a string.")

        extension = PurePath(filename.replace("\\", "/")).suffix.lower()

        if extension not in {".pdf", ".csv"}:
            raise ValueError("Only PDF and CSV documents are supported.")

        digest = sha256(content).hexdigest()

        key = f"documents/{owner_id}/{upload_id}/{digest}{extension}"
        content_type = "application/pdf" if extension == ".pdf" else "text/csv"

        return self._upload(content, key=key, content_type=content_type, digest=digest)

    def download(self, object_key: str, *, generation: int) -> bytes:
        self._validate_reference(object_key, generation)

        content = self._download(object_key, generation=generation)

        if not isinstance(content, bytes) or not content:
            raise StorageError("Storage returned an empty or invalid document.")

        if len(content) > self.MAX_FILE_BYTES:
            raise StorageError("Stored document exceeds the size limit.")

        digest = PurePath(object_key).stem

        if sha256(content).hexdigest() != digest:
            raise StorageConflict("Stored document checksum does not match its key.")

        return content

    def delete(self, object_key: str, *, generation: int) -> None:
        self._validate_reference(object_key, generation)

        self._delete(object_key, generation=generation)

    def _validate_reference(self, object_key: str, generation: int) -> None:
        if not isinstance(object_key, str) or not self.KEY_PATTERN.fullmatch(
            object_key
        ):
            raise ValueError("Invalid application document key.")

        if type(generation) is not int or generation < 1:
            raise ValueError("generation must be a positive integer.")

    @abstractmethod
    def _upload(
        self, content: bytes, *, key: str, content_type: str, digest: str
    ) -> StoredObject:
        raise NotImplementedError

    @abstractmethod
    def _download(self, object_key: str, *, generation: int) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def _delete(self, object_key: str, *, generation: int) -> None:
        raise NotImplementedError
