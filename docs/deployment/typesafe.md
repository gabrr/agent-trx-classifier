# TypeSafe → Jev

Classifies extracted transactions using typed decisions. Called directly through
the existing TypeSafe SDK; OpenRouter is used for Gemini only.
Setup: **existing API key + CLI**; console only for account, credits, or key replacement.

## Configure

Keep the existing `TYPESAFE_API_KEY` in local environment/`.env`. Use the
[secret helper](README.md):

```sh
publish_trx_secret TYPESAFE_API_KEY trx-typesafe-key
```

The Cloud Run guide grants access and maps it to `TYPESAFE_API_KEY`. Current
provider uses `jev-latest`. Consider pinning a tested version before launch for
repeatable classification; this requires an application change.

## Verify and budget

Classify one extracted statement and confirm typed decisions match the expected
categories. Measure total Jev input tokens across all classification calls per
PDF; the initial estimate is 1,600 tokens/PDF.

Handle authentication errors as configuration failures and rate limits as
retryable failures. Include provider deadlines within the task's total deadline.
Jev receives text/structured fields, not raw PDFs. Store final classification in
PostgreSQL so completed task retries do not call the provider again.

[TypeSafe models and pricing](https://docs.typesafe.ai/models)
· [TypeSafe account](https://typesafe.ai/)
