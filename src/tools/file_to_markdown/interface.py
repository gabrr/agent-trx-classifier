import base64
import binascii
from abc import ABC, abstractmethod
from pathlib import PurePath


class FileToMarkdown(ABC):
    """Interface for converting Base64-encoded documents to Markdown."""

    ALLOWED_EXTENSIONS = frozenset({".pdf", ".csv"})

    MAX_FILE_BYTES = 25 * 1024 * 1024

    def convert(self, file_base64: str, *, filename: str) -> str:
        if not isinstance(file_base64, str) or not isinstance(filename, str):
            raise TypeError("file_base64 and filename must be strings.")

        extension = PurePath(filename).suffix.lower()

        if extension not in self.ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported extension: {extension or '(none)'}")

        max_encoded_length = 4 * ((self.MAX_FILE_BYTES + 2) // 3)

        if len(file_base64) > max_encoded_length:
            raise ValueError("File exceeds the configured size limit.")

        try:
            content = base64.b64decode(file_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid Base64 content.") from exc

        if not content:
            raise ValueError("Empty files are not allowed.")

        if len(content) > self.MAX_FILE_BYTES:
            raise ValueError("File exceeds the configured size limit.")

        markdown = self._convert(content, filename=filename)

        if not isinstance(markdown, str):
            raise TypeError("Provider must return Markdown as a string.")

        if not markdown.strip():
            raise RuntimeError("No readable content was extracted.")

        return markdown

    @abstractmethod
    def _convert(self, content: bytes, *, filename: str) -> str:
        """Convert validated document bytes into Markdown."""
        raise NotImplementedError
