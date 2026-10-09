# Classifier architecture

The classifier prepares a PDF or CSV as text, extracts a structured statement, and classifies its transactions. CLI and evaluation run the graph directly. The HTTP API runs it through a durable job wrapper.

## Workflow

```mermaid
flowchart LR
    F[PDF or UTF-8 CSV] --> P[Prepare text]
    P --> E[Extract statement and transactions]
    E --> C[Classify transaction batch]
    C --> R[Validate and assemble result]
```

PDF preparation uses Docling; CSV preparation decodes text directly. Both feed the same extraction and classification stages. The extraction provider/model is selected in [workflow.py](../src/workflows/trx_classifier/workflow.py); the classification adapter is [jev.py](../src/tools/single_model/jev.py).

## Code responsibilities

| Location | Responsibility |
| --- | --- |
| [Configuration](../src/config.py) | Environment loading, accepted file formats, limits, database URLs and job settings. |
| [API](../src/api/) | Authentication, job requests, internal handlers, event responses and health. |
| [Services](../src/services/) | Session lifecycle, uploads, outbox dispatch and maintenance. |
| [Database](../src/db/) | Models, owner-scoped repositories, transactions and notification listener. |
| [Tools](../src/tools/) | Provider interfaces, factories, SDK adapters and input preparation. |
| [Classifier workflow](../src/workflows/trx_classifier/) | Sequential graph, extraction prompt, classification criteria and output models. |
| [Job processing](../src/workflows/job_processing/) | Attempt claims, compatible checkpoint resume and durable outcomes. |
| [CLI](../src/cli/) | Direct classification entry points. |
| [Evaluations](../src/evaluations/) | Dataset synchronization and quality measurements. |

[pyproject.toml](../pyproject.toml) defines runtime/development dependencies; [uv.lock](../uv.lock) pins them. Provider implementations follow the tools/workflows abstraction pattern: interfaces define operations, factories select implementations, and services receive dependencies.

## Input and progress

`StatementFileInput` validates input once and caches successful text preparation. Local execution shares the input object; LangGraph tooling can supply `file_base64` and `filename`. Checkpoints serialize stage state without the input object or raw Base64 payload.

[The event wrapper](../src/tools/event_stream.py) emits step-start and step-completion data around graph nodes. It records each stage's duration and supports resumed stages. The direct stream formatter presents an already-running graph; the durable wrapper stores progress through repositories.

`metrics.elapsed_seconds` sums conversion, extraction and classification durations. It excludes graph scheduling, event persistence, formatting and the `complete` step. Resumed stages retain their saved durations, so this metric is not the wall-clock latency of a retry.

[System design](trx-system-design/README.md) covers service boundaries, job recovery and browser streaming. [Contract](trx-classifier-contract.md) defines inputs, outputs and routes. Correction memory and external research are [proposals](trx-classifier-context-addon.md), not processing stages in the current graph.
