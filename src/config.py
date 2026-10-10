import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AgentConfig:
    accepted_formats: tuple[str, ...] = ("pdf", "csv")

    max_file_bytes: int = 25 * 1024 * 1024
    csv_encoding: str = "utf-8-sig"


@cache
def load_environment() -> None:
    load_dotenv(ROOT / ".env", interpolate=False)

    os.environ.setdefault("LANGSMITH_PROJECT", "trx-classifier")


@dataclass(frozen=True)
class ApiConfig:
    enable_docs: bool = False


@dataclass(frozen=True)
class DatabaseConfig:
    runtime_url: str | None


def database_url() -> str | None:
    """Validate the database connection without logging credentials."""
    from sqlalchemy.engine import make_url

    load_environment()

    value = os.environ.get("DATABASE_URL")

    if not value:
        return None

    try:
        url = make_url(value)

    except Exception:
        raise ValueError("Invalid database URL") from None

    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg")

    if url.drivername != "postgresql+psycopg":
        raise ValueError("PostgreSQL with psycopg is required")

    return url.render_as_string(hide_password=False)


def database_config() -> DatabaseConfig:
    return DatabaseConfig(database_url())


@dataclass(frozen=True)
class JobConfig:
    bucket_name: str
    project_id: str
    location: str
    queue_name: str
    backend_url: str
    task_caller_email: str
    processing_timeout_seconds: int = 1700
    job_deadline_seconds: int = 7200
    max_attempts: int = 5

    def __post_init__(self):
        if not 0 < self.processing_timeout_seconds < 1800:
            raise ValueError("Processing timeout must be shorter than 1800 seconds")

        if self.job_deadline_seconds <= 0 or self.max_attempts <= 0:
            raise ValueError("Job deadline and attempt budget must be positive")

    @classmethod
    def from_environment(cls):
        load_environment()

        names = (
            "GCS_BUCKET",
            "GOOGLE_CLOUD_PROJECT",
            "TASKS_LOCATION",
            "TASKS_QUEUE",
            "BACKEND_URL",
            "TASK_CALLER_EMAIL",
        )

        values = [os.environ.get(name, "").strip() for name in names]

        if not all(values):
            raise ValueError("Storage and Cloud Tasks configuration is required")

        return cls(*values)
