import base64
import binascii
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import PurePath
from threading import RLock

from config import AgentConfig
from tools.file_to_markdown import FileToMarkdown


@dataclass(frozen=True)
class StatementFileInput:
    """An accepted statement file with reusable in-memory representations."""

    content: bytes = field(repr=False)
    filename: str
    config: AgentConfig = field(default_factory=AgentConfig, repr=False)
    format: str = field(init=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False, compare=False)
    _text: str | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes) or not self.content:
            raise ValueError("Upload a nonempty statement file.")

        if len(self.content) > self.config.max_file_bytes:
            raise ValueError(
                f"Statement exceeds the {self.config.max_file_bytes}-byte upload limit."
            )

        if not isinstance(self.filename, str) or not self.filename.strip():
            raise ValueError("A statement filename is required.")

        filename = PurePath(self.filename.replace("\\", "/")).name
        file_format = PurePath(filename).suffix.lower().lstrip(".")

        if file_format not in self.config.accepted_formats:
            raise ValueError(
                f"Unsupported statement format: {file_format or '(none)'}."
            )

        if file_format == "pdf":
            if not self.content.startswith(b"%PDF-"):
                raise ValueError("Upload a valid PDF document.")

        elif file_format == "csv":
            try:
                text = self.content.decode(self.config.csv_encoding)
            except (UnicodeError, LookupError) as error:
                raise ValueError(
                    f"CSV must use {self.config.csv_encoding} encoding."
                ) from error

            if not text.strip() or "\x00" in text:
                raise ValueError("Upload a nonempty CSV text document.")

            object.__setattr__(self, "_text", text)

        else:
            raise ValueError(f"Statement format is not implemented: {file_format}.")

        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "format", file_format)

    @classmethod
    def from_bytes(
        cls, content: bytes, *, filename: str, config: AgentConfig | None = None
    ) -> "StatementFileInput":
        return cls(content, filename, config or AgentConfig())

    @classmethod
    def from_base64(
        cls, encoded: str, *, filename: str, config: AgentConfig | None = None
    ) -> "StatementFileInput":
        """Adapt JSON input from LangGraph tooling without re-encoding it."""
        config = config or AgentConfig()

        if not isinstance(encoded, str):
            raise ValueError("Statement Base64 must be a string.")

        if len(encoded) > 4 * ((config.max_file_bytes + 2) // 3):
            raise ValueError("Statement exceeds the upload limit.")

        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Invalid statement Base64 content.") from error

        statement = cls.from_bytes(content, filename=filename, config=config)
        statement.__dict__["_base64"] = encoded

        return statement

    @property
    def size_bytes(self) -> int:
        return len(self.content)

    @cached_property
    def _base64(self) -> str:
        return base64.b64encode(self.content).decode("ascii")

    def to_base64(self) -> str:
        with self._lock:
            return self._base64

    def to_text(self, *, pdf_converter: FileToMarkdown) -> str:
        """Reuse CSV text or convert PDF once with the existing converter."""
        with self._lock:
            if self._text is None:
                text = pdf_converter.convert(self.to_base64(), filename=self.filename)

                object.__setattr__(self, "_text", text)

            return self._text
