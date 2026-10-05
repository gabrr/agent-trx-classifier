from workflows.trx_classifier.factory import workflow_factory

from .interface import DocumentClassifier
from .runner import LangGraphRunner


def classifier_factory() -> DocumentClassifier:
    return LangGraphRunner(workflow_factory())
