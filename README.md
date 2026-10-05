# TRX Classifier

Extracts transactions from PDF and CSV statements and classifies them into `fixed`,
`movements`, `installments`, and `variable`.

## Quick start

Requires Python 3.12+ and uv. From the workspace root:

```sh
cd apps/agent-trx-classifier
uv sync
```

Create `.env` from [`.env.example`](.env.example) if it does not exist, then set
`OPENROUTER_API_KEY`, `TYPESAFE_API_KEY`, and `LANGSMITH_API_KEY`. See
[credential details](docs/trx-classifier-usage.md#credentials) for tracing options.

Classify the included sample PDF:

```sh
uv run trx-classify src/evaluations/dataset/fixtures/fixture-01.pdf
```

Returns `statement`, `transactions`, and `metrics` as final JSON. CLI commands
run directly without the API or web app. The first conversion downloads Docling
models and can take longer.

## CLI

Run commands below from `apps/agent-trx-classifier`.

```sh
uv run trx-classify /path/to/statement.pdf
uv run trx-classify /path/to/statement.pdf --stream
uv run trx-classify /path/to/statement.csv
```

Standard mode prints the final result; `--stream` emits progress and the final
result as JSON lines. See [CLI details](docs/trx-classifier-usage.md#cli) for
input limits, events, and errors.

## API and web

```sh
uv run trx-api
```

The API uses `http://127.0.0.1:8000`; `GET /health` checks readiness and
`POST /classify` accepts a PDF or CSV in multipart field `file`, returning SSE events.
[Acetate Web 0.1](../acetate-web-0.1/README.md) runs on port 3101 and proxies
uploads to this API.

## Other commands

| Command | Purpose |
| --- | --- |
| `uv run trx-dataset` | Upload or update the reference PDF and expected results in LangSmith. |
| `uv run trx-evaluate` | Synchronize the dataset, run classification, and record evaluation scores in LangSmith. |
| `uv run ruff check .` | Check Python lint issues without modifying files. |
| `uv run ruff format --check .` | Check Python formatting without modifying files. |

`trx-evaluate` makes model calls and already synchronizes the dataset; running
`trx-dataset` first is optional. See [evaluation details](docs/trx-classifier-usage.md#evaluation)
and [code checks](docs/trx-classifier-usage.md#code-checks).

## Concepts and details

| Concept | More information |
| --- | --- |
| Workflow: PDF conversion, extraction, and classification. | [Architecture](docs/trx-classifier-architecture.md) |
| Results: fields, categories, confidence, and events. | [Contract](docs/trx-classifier-contract.md) |
| Dataset: a reference PDF paired with expected results. | [Dataset synchronization](docs/trx-classifier-usage.md#dataset-synchronization) |
| Evaluation: compare model output with the reference results. | [Evaluation](docs/trx-classifier-usage.md#evaluation) |

[Documentation index](docs/index.md).

Commit messages: `type: comment`, using `feat`, `fix`, `chore`, `doc`, or
`refactor`. Example: `doc: made readme.md clearer`.
