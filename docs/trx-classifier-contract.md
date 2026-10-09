# Classifier and API contract

The classifier accepts one PDF or UTF-8 CSV and returns a normalized statement. [Pydantic models](../src/workflows/trx_classifier/models.py) define the result schema; [API routes](../src/api/) define the HTTP interface.

## Models and execution

- Inputs are nonempty PDF or CSV files within the limit defined by `AgentConfig` in [config.py](../src/config.py). The current limit is 25 MiB. PDFs require a valid signature; CSVs require UTF-8 text, with an optional byte-order mark.
- The workflow prepares text, extracts statement fields, classifies transactions, and assembles `statement`, `transactions` and `metrics`.
- Classification sends one Choice question per transaction in one batch request. The criteria are `fixed`, `movements`, `installments` and `no_match`; `no_match` maps to `variable` locally. An empty transaction list makes no classification call.
- Transaction IDs are positional (`tx_000`, `tx_001`, ...), stable within a result. They are not global identifiers across statements.
- Money values remain strings; dates serialize as ISO dates. Nullable source fields stay nullable. Preserve original transaction order.
- Each transaction has `report_bucket`, `classification_confidence` and `classification_probabilities`. Probabilities must include all four buckets, be finite values between zero and one, and sum to one within the model's tolerance.
- Metrics include summed stage duration, classification duration, classification model-call count and transaction count. See [timing semantics](trx-classifier-architecture.md#input-and-progress).

## HTTP API

User routes require `Authorization: Bearer <Supabase access token>`. Submission/retry keys are scoped to the authenticated user.

| Route | Request and response |
| --- | --- |
| `GET /auth/me` | Returns verified user ID, email and name. |
| `POST /api/jobs` | Multipart `file`, `Idempotency-Key`; returns 202 with job ID/status. |
| `GET /api/jobs/{job_id}` | Owner-scoped status and safe failure information. |
| `GET /api/jobs/{job_id}/result` | Owner-scoped classifier result; 409 while unavailable. |
| `POST /api/jobs/{job_id}/retry` | Failed job, new `Idempotency-Key`; returns 202 with a linked replacement job. |
| `GET /api/jobs/{job_id}/events` | Owner-scoped SSE replay/live stream; optional `Last-Event-ID` sequence. |
| `POST /internal/process` | Google task identity; JSON `job_id`; processes or acknowledges a durable job. |
| `POST /internal/maintenance` | Google maintenance identity; recovers dispatch and finalizes expired jobs. |
| `GET /health` | Process liveness. |
| `GET /ready` | Bounded database connectivity check. |

Unknown or cross-owner job reads return 404. Missing/invalid/expired tokens return 401; unavailable authentication configuration returns 503. `/classify` returns 410 after token verification in the default app; direct classification uses the CLI. The current API has no job listing, multi-file submission, file-download or user cancellation route.

Processing returns 204 for terminal outcomes, 409 for an active duplicate and 503 for a retryable processing failure. Google caller verification occurs before processing. [Job recovery](trx-system-design/01-architecture-and-services.md#recovery) explains attempt/deadline limits and checkpoints.

## Events and errors

Classifier progress uses `step_started` and `step_completed`. Completion output includes stage output and type where available; the `complete` step supplies timing only. `result` carries the complete normalized result once.

Durable job streams also include lifecycle events and safe terminal errors. Their SSE IDs are per-job sequences. [Events and live updates](trx-system-design/02-events-and-live-updates.md) is the authoritative stored/wire-format guide.

Direct CLI execution propagates processing errors and exits nonzero. Durable jobs can retry nonterminal errors within their budget; exhausted, invalid or timed-out work persists a terminal failure. Low confidence and an empty transaction list are valid classifier outcomes. SDK retry behavior is adapter-specific; the job wrapper has no additional provider retry loop.

## Errors and evaluation

Evaluation maps reference labels `excluded` to `movements` and `installment` to `installments` without modifying the source dataset. Dataset inputs and expected results live in [dataset.json](../src/evaluations/dataset/dataset.json).

Measure classification accuracy, transaction count, processing duration and monetary correctness. Compare statement total and signed transaction sum separately using decimal arithmetic; they need not be equal. Missing rows must affect end-to-end accuracy rather than disappearing from the denominator. [Evaluation implementation](../src/evaluations/evaluation/)

Correction memory and external enrichment are separate [proposals](trx-correction-memory.md).
