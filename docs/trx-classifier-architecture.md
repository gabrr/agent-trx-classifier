# TRX-classifier architecture

## Tech stack

| Technology | Purpose |
| --- | --- |
| Python 3.12+ | Application language and runtime. |
| uv | Dependency management and Python command execution. |
| LangGraph | Workflow graphs, state, and execution. |
| LangGraph CLI | Local graph development and execution. |
| LangChain | General LLM tool implementation and structured responses. |
| Gemini 3.8 Flash via OpenRouter | Transaction extraction, reusing Evaluation Lab configuration. |
| FastAPI / Uvicorn | HTTP API and SSE streaming. |
| Pydantic | Domain models and data validation. |
| Docling | Document-to-Markdown conversion. |
| TypeSafe SDK | Typed Choice questions and Jev API access. |
| Jev (`jev-latest`) | Transaction classification model. |
| LangSmith | Datasets, evaluations, experiment comparisons, and tracing. |
| Ruff | Python linting and formatting. |

Status: implemented core classifier. Memory and external research are deferred.

TRX-classifier is a standalone LangGraph workflow that receives a full document, converts it to Markdown, extracts transactions with an LLM, and classifies each one through Jev. It follows the tools/workflows architecture from Evaluation Lab.

## Project structure

```text
apps/agent-trx-classifier/
├── AGENTS.md
├── pyproject.toml
├── ruff.toml
├── langgraph.json
├── .gitignore
├── .env
├── .env.example
├── README.md
├── docs/
│   ├── index.md
│   ├── trx-classifier-architecture.md
│   ├── trx-classifier-contract.md
│   ├── trx-classifier-frontend-plan.md
│   ├── trx-classifier-context-addon.md
│   └── trx-correction-memory.md
└── src/
    ├── api/
    ├── cli/
    ├── runtime/
    │   ├── events.py
    │   ├── interface.py
    │   ├── factory.py
    │   ├── settings.py
    │   └── runner.py
    ├── evaluations/
    │   ├── dataset/
    │   │   ├── dataset.json
    │   │   └── fixtures/
    │   │       └── fixture-01.pdf
    │   └── evaluation/
    ├── tools/
    │   ├── __init__.py
    │   ├── file_to_markdown/
    │   │   ├── __init__.py
    │   │   ├── interface.py
    │   │   ├── factory.py
    │   │   └── docling.py
    │   ├── llm/
    │   │   ├── __init__.py
    │   │   ├── interface.py
    │   │   ├── factory.py
    │   │   ├── model_factory.py
    │   │   └── langchain.py
    │   └── single_model/
    │       ├── __init__.py
    │       ├── interface.py
    │       ├── factory.py
    │       └── jev.py
    └── workflows/
        ├── __init__.py
        └── trx_classifier/
            ├── __init__.py
            ├── models.py
            ├── state.py
            ├── criteria.py
            ├── parallel_choice.py
            ├── prompts.py
            ├── nodes.py
            ├── steps.py
            ├── factory.py
            ├── graph.py
            └── workflow.py
```
