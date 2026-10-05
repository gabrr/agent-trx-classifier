from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from tools.statement_file import StatementFileInput
from workflows.trx_classifier.models import NormalizedStatement

from .events import WorkflowEvent


class DocumentClassifier(ABC):
    @abstractmethod
    def classify(self, file: StatementFileInput) -> NormalizedStatement:
        """Classify a document, raising on processing failures."""
        raise NotImplementedError

    @abstractmethod
    def events(self, file: StatementFileInput) -> AsyncIterator[WorkflowEvent]:
        """Stream progress and one final result from the same workflow."""
        raise NotImplementedError
