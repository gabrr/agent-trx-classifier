import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def load_environment() -> None:
    load_dotenv(ROOT / ".env")

    os.environ.setdefault("LANGSMITH_PROJECT", "trx-classifier")


@dataclass(frozen=True)
class Settings:
    extraction_model: str = "openrouter:google/gemini-3.8-flash"
    max_upload_bytes: int = 25 * 1024 * 1024
