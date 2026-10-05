from typing import TypedDict

from .models import ExtractedStatement, NormalizedStatement
from .parallel_choice import ClassificationBatch


class ClassifierState(TypedDict, total=False):
    file_base64: str
    filename: str
    started_at: float
    markdown: str
    extracted: ExtractedStatement
    batch: ClassificationBatch
    result: NormalizedStatement
