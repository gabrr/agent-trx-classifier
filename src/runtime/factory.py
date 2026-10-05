from workflows.trx_classifier.workflow import build_workflow

from .interface import DocumentClassifier
from .runner import LangGraphRunner


def classifier_factory() -> DocumentClassifier:
    return LangGraphRunner(build_workflow())
