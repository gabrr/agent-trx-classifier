# TRX-classifier contract

## Models and execution

- Borrow models, validators, and extraction instructions from Evaluation Lab's `src/workflows/normalizer/`. Session preferences agreed here take priority.
- Extraction: Gemini 3.8 Flash through the existing LangChain/OpenRouter configuration, `openrouter:google/gemini-3.8-flash`.
- Classification: Jev Parallel Choice; one question per transaction, one request for the whole batch. Evaluate `fixed`, `movements`, and `installments`; `no_match` becomes `variable` locally with no additional call.
- Input: full PDF or UTF-8 CSV. API accepts multipart `file`; CLI accepts a file path. Both use the same workflow and event contract.
- Output: `statement` and `transactions`, using the source models. Keep decimal amounts as strings, ISO dates, and original row order.
- Transaction classification fields: `report_bucket`, `classification_confidence` (0–1), and `classification_probabilities`. Add stable transaction IDs for context attachment and reassessment.
- Categories: `fixed`, `movements`, `installments`, `variable`. Map dataset reference labels `excluded → movements` and `installment → installments` during evaluation; preserve the source dataset.
- SSE events: `step_started`, `step_completed`, `result`, `error`. Step events identify the step; completed events expose its actual output and type, except `complete`, which reports timing only. The full final output appears once in `result`.

[TRX Correction Memory](trx-correction-memory.md) and external research remain deferred add-ons. Memory corrections identify their classification dimension: `report_bucket` now; separate spending categories such as food, car and entertainment later.

## Errors and evaluation

- Fail on processing/provider/validation errors. No silent fallback or automatic retries. The API emits `error` if streaming has begun; the CLI fails with a nonzero exit.
- An empty transaction list or low confidence is a valid outcome, not a processing error.
- Use LangSmith dataset `trx-classifier`, with the supplied PDF attached and the adapted reference labels; expected transaction count is 99.
- Measure classification accuracy, summed processing duration, exact transaction count, and monetary correctness. `metrics.elapsed_seconds` sums conversion, extraction, and classification durations; it excludes graph overhead and the `complete` step.
- Compare statement total and the sum of signed transaction amounts separately against their dataset references, using decimal arithmetic. Do not assume the invoice total equals the transaction sum.
- Reuse source transaction matching and amount evaluators; include end-to-end classification accuracy so missing rows cannot inflate accuracy.
