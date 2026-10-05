# TRX Classifier usage

All commands below run from `apps/agent-trx-classifier` after `uv sync`.
For first-time setup, start with the [README](../README.md#quick-start).

## Credentials

The classifier loads this app's `.env` once per process; existing process
environment variables take precedence. Restart the process after changing `.env`.

| Variable | Used for |
| --- | --- |
| `OPENROUTER_API_KEY` | Gemini transaction extraction. |
| `TYPESAFE_API_KEY` | Jev transaction classification. |
| `LANGSMITH_API_KEY` | Tracing, dataset synchronization, and evaluation. |
| `LANGSMITH_TRACING` | Enables tracing when set to `true` in the example configuration. Set to `false` to disable tracing for CLI/API runs. |
| `LANGSMITH_PROJECT` | Trace project; defaults to `trx-classifier`. |
| `LANGSMITH_ENDPOINT` | LangSmith service endpoint; supplied in `.env.example`. |

CLI/API classification requires OpenRouter and TypeSafe credentials. LangSmith
credentials are needed when tracing is enabled and for dataset/evaluation
commands, even if tracing is disabled.

## CLI

```sh
uv run trx-classify src/evaluations/dataset/fixtures/fixture-01.pdf
```

Accepts a nonempty PDF (`.pdf`) or UTF-8 CSV (`.csv`), up to 25 MiB. UTF-8
byte-order marks are supported. PDF uses Docling; CSV goes directly to LLM
extraction as text. Both use the same downstream workflow as the API.

```sh
uv run trx-classify /path/to/statement.csv
```

Standard output contains the final result:

| Field | Contents |
| --- | --- |
| `statement` | Statement metadata, such as institution, currency, dates, and total. |
| `transactions` | Extracted rows with category, confidence, and category probabilities. |
| `metrics` | Workflow and classification durations, classification model calls, and transaction count. |

See the [contract](trx-classifier-contract.md#models-and-execution) for category
mapping and output conventions.

```sh
uv run trx-classify src/evaluations/dataset/fixtures/fixture-01.pdf --stream
```

Each line contains an event with `event` and `data` fields. Step events report
progress and completed step outputs; the `complete` step reports timing only.
The `result` event contains the complete result once. Event details are in the [contract](trx-classifier-contract.md#models-and-execution).

CLI failures are printed to stderr as `ExceptionType: message`, including in
streaming mode. Invalid files, provider failures, or output validation errors
stop processing. Low confidence or an empty transaction list can still be a
valid result.

## API

```sh
uv run trx-api
```

Binds to `127.0.0.1:8000`. `GET /health` reports readiness; `POST /classify` accepts
multipart field `file` and streams SSE events. Only one classification runs at a
time: overlapping requests receive HTTP 409. Invalid PDF/CSV files receive HTTP 422;
failures after streaming starts are sent as `error` events.

For the browser client and its proxy configuration, see
[Acetate Web 0.1](../../acetate-web-0.1/README.md).

## Dataset synchronization

```sh
uv run trx-dataset
```

Reads `src/evaluations/dataset/dataset.json` and the PDF named by its
`input.fixture` field under `src/evaluations/dataset/fixtures/`.

Creates the LangSmith dataset `trx-classifier` if missing, then creates or updates
the reference example identified by its `dataset_id` metadata. Uploads the PDF
as an attachment, inputs, and expected results. Prints
`Synchronized LangSmith dataset: trx-classifier` on completion.

Synchronization adapts reference labels `excluded` to `movements` and
`installment` to `installments`. Local dataset files and PDFs remain unchanged.
This command does not run classification.

## Evaluation

```sh
uv run trx-evaluate
```

Synchronizes the reference dataset, then runs the full classifier against its
examples using LangSmith. Each example makes extraction and classification
model calls. Examples run sequentially with `max_concurrency=1`.

Records an experiment with prefix `parallel-choice` and prints one JSON object
of scores per evaluated example. Measures transaction count, matching, amounts,
category accuracy, statement total, signed transaction total, and workflow
duration. See [evaluation rules](trx-classifier-contract.md#errors-and-evaluation)
for how those results are interpreted.

Run this after workflow changes to compare quality and timing in LangSmith.
`trx-dataset` is useful separately when you only want to update the reference
example; evaluation already performs that synchronization.

## Code checks

```sh
uv run ruff check .
uv run ruff format --check .
```

Both commands report issues without editing files. To apply formatting:

```sh
uv run ruff format .
```

Project readability conventions are in [AGENTS.md](../AGENTS.md).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing credentials or provider authentication failure | App `.env` and process environment overrides; see the credential table above. |
| Slow first conversion | Docling downloads models on first use. |
| File rejected | Nonempty content, PDF/CSV extension, valid PDF signature or UTF-8 CSV text, and the 25 MiB limit. |
| API cannot bind port 8000 | Another service, such as the backend API, may already use that port. |
| Web upload cannot reach the classifier | API availability and the web app's `CLASSIFIER_API_URL`; see its README. |
| Dataset/evaluation authentication failure | LangSmith key and endpoint, even if tracing is disabled. |

## SDK references

- [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [LangChain OpenRouter](https://docs.langchain.com/oss/python/integrations/chat/openrouter)
- [TypeSafe SDK](https://github.com/typesafe-ai/typesafe-sdk-python)
- [LangSmith attachments](https://docs.langchain.com/langsmith/evaluate-with-attachments)
- [FastAPI streaming responses](https://fastapi.tiangolo.com/advanced/custom-response/)
