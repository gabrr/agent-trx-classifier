from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from workflows.trx_classifier.models import NormalizedStatement

from .events import WorkflowEvent


class DocumentClassifier(ABC):
    @abstractmethod
    def classify(self, document: bytes, *, filename: str) -> NormalizedStatement:
        """Classify a document, raising on processing failures."""
        raise NotImplementedError

    @abstractmethod
    def events(self, document: bytes, *, filename: str) -> AsyncIterator[WorkflowEvent]:
        """Stream progress and one final result from the same workflow."""
        raise NotImplementedError
