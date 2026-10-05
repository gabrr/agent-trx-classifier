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
    load_dotenv(ROOT / ".env")

    os.environ.setdefault("LANGSMITH_PROJECT", "trx-classifier")
