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
class DatabaseConfig:
    runtime_url: str | None
    listener_url: str | None


def database_url(*, admin: bool = False) -> str | None:
    """Resolve legacy password placeholders without logging credentials."""
    from sqlalchemy.engine import make_url

    load_environment()

    value = os.environ.get("DATABASE_ADMIN_URL" if admin else "DATABASE_URL")

    if not value and not admin:
        value = os.environ.get("DB_URL")

    if not value:
        if admin:
            raise ValueError("DATABASE_ADMIN_URL is required for migrations")

        return None

    password = os.environ.get("DB_PASSWORD")

    for placeholder in ("${DB_PASSWORD}", "$DB_PASSWORD", "${PASSWORD}", "$PASSWORD"):
        if placeholder in value:
            if not password:
                raise ValueError("DB_PASSWORD is required for the legacy URL")

            from urllib.parse import quote

            value = value.replace(placeholder, quote(password, safe=""))

    try:
        url = make_url(value)

    except Exception:
        raise ValueError("Invalid database URL") from None

    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg")

    if url.drivername != "postgresql+psycopg":
        raise ValueError("PostgreSQL with psycopg is required")

    if not url.password and password:
        url = url.set(password=password)

    if not admin and (url.username or "").split(".")[0] != "trx_app":
        raise ValueError("Runtime requires the restricted trx_app role")

    return url.render_as_string(hide_password=False)


def database_config() -> DatabaseConfig:
    runtime_url = database_url()

    listener_url = os.environ.get("DATABASE_LISTENER_URL") or runtime_url
    if listener_url:
        from sqlalchemy.engine import make_url

        try:
            listener = make_url(listener_url)

        except Exception:
            raise ValueError("Invalid listener URL") from None

        if (listener.username or "").split(".")[0] != "trx_app":
            raise ValueError("Listener requires the restricted trx_app role")

    return DatabaseConfig(runtime_url, listener_url)
