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

TRX-classifier is a standalone LangGraph workflow that receives a PDF or CSV, prepares Markdown or CSV text, extracts transactions with an LLM, and classifies each one through Jev. It follows the tools/workflows architecture from Evaluation Lab.

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
    ├── config.py
    ├── api/
    ├── cli/
    ├── evaluations/
    │   ├── dataset/
    │   │   ├── dataset.json
    │   │   └── fixtures/
    │   │       └── fixture-01.pdf
    │   └── evaluation/
    ├── tools/
    │   ├── __init__.py
    │   ├── event_stream.py
    │   ├── statement_file/
    │   │   ├── __init__.py
    │   │   └── input.py
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
            ├── criteria.py
            ├── classification.py
            ├── prompts.py
            └── workflow.py
```

## File preparation

`config.py` owns accepted formats, the upload size limit, CSV encoding, and
once-per-process environment initialization. The extraction model stays in
`build_workflow()` and prompts stay in code.

API, CLI, and evaluation construct `StatementFileInput` once. The immutable file
retains bytes and caches successful Base64 encoding and text preparation. The
`convert` stage calls `to_text()`: PDFs use the existing Docling tool; CSVs are
decoded directly and bypass Docling. Both feed `document_text` into extraction.
The existing conversion, LLM, and Jev tools remain unchanged.

LangGraph tooling can still supply `file_base64` and `filename`; the conversion
stage adapts this JSON input without re-encoding it. File objects and their locks
are for local execution, not serialized checkpoint storage.

API, CLI, and evaluations execute the compiled graph directly. The reusable
`tools/event_stream.py` function wraps node operations and emits the existing
progress events. `workflow_events()` formats an already-running graph stream,
validates progress events, emits one final result, and detects missing results;
it does not build or execute graphs.

Each processing node stores its duration in `step_durations`. The final `complete`
node sums conversion, extraction, and classification durations into
`metrics.elapsed_seconds`, including for direct graph execution. This is processing
time, excluding graph scheduling, event serialization, and final-result formatting.
The `complete` step still emits its own duration but is excluded from the sum.
Duration accumulation assumes the current sequential graph; parallel branches
would require a state reducer.
