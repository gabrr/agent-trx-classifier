from langchain.agents.structured_output import ProviderStrategy

from runtime.settings import Settings, load_environment
from tools import file_to_markdown_factory, llm_factory, single_model_factory

from .models import ExtractedStatement
from .nodes import ClassifierNodes
from .prompts import EXTRACTION_PROMPT
from .workflow import build_graph


def workflow_factory(settings: Settings | None = None):
    load_environment()

    settings = settings or Settings()

    nodes = ClassifierNodes(
        converter=file_to_markdown_factory("docling"),
        extractor=llm_factory(
            "langchain",
            model=settings.extraction_model,
            system_prompt=EXTRACTION_PROMPT,
            response_format=ProviderStrategy(ExtractedStatement),
        ),
        classifier=single_model_factory("jev"),
    )

    return build_graph(nodes)
