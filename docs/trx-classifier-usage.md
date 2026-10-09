# TRX Classifier usage

All commands below run from `apps/agent-trx-classifier` after `uv sync`.
For first-time setup, start with the [README](../README.md#quick-start).

## Credentials

The classifier loads this app's `.env` once per process; existing process
environment variables take precedence. Restart the process after changing `.env`.
Use `uv run --env-file .env.prod trx-api` to load production settings explicitly.
Both `.env` and `.env.prod` are private files excluded from Git and Docker build contexts;
[`.env.example`](../.env.example) is the shared template.

| Variable | Used for |
| --- | --- |
| `OPENROUTER_API_KEY` | Gemini transaction extraction. |
| `TYPESAFE_API_KEY` | Jev transaction classification. |
| `LANGSMITH_API_KEY` | Tracing, dataset synchronization, and evaluation. |
| `LANGSMITH_TRACING` | Enables tracing when set to `true`. Set to `false` to disable tracing for CLI/API runs. |
| `LANGSMITH_PROJECT` | Trace project; defaults to `trx-classifier`. |
| `LANGSMITH_ENDPOINT` | Optional LangSmith service endpoint override. |

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
| `metrics` | Summed processing duration (`elapsed_seconds`: conversion + extraction + classification), classification duration, classification model calls, and transaction count. Graph overhead and final-result preparation are excluded. |

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

Binds to `0.0.0.0:$PORT`, default port 8080. `/health` is liveness and `/ready` checks PostgreSQL. Verified Supabase Bearer tokens protect user routes. POST `/api/jobs` accepts multipart `file` plus `Idempotency-Key` and Authorization headers, returning 202. Owner-checked status/result/event routes expose persisted outcomes; Cloud Tasks invokes the independently authenticated internal processing route.

The default HTTP `/classify` path is disabled (410 after token verification). Direct CLI classification remains available. Acetate Web 0.1 uses the older direct classification interface. For the authenticated job API, use the [API contract](trx-classifier-contract.md#http-api) and [deployment guide](deployment/README.md).

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
| API cannot bind its configured port | Another service, such as the backend API, may already use that port. |
| Job submission fails | Bearer token, idempotency key, database, bucket and task configuration; see the deployment guides. |
| Dataset/evaluation authentication failure | LangSmith key and endpoint, even if tracing is disabled. |

## SDK references

- [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [LangChain OpenRouter](https://docs.langchain.com/oss/python/integrations/chat/openrouter)
- [TypeSafe SDK](https://github.com/typesafe-ai/typesafe-sdk-python)
- [LangSmith attachments](https://docs.langchain.com/langsmith/evaluate-with-attachments)
- [FastAPI streaming responses](https://fastapi.tiangolo.com/advanced/custom-response/)
