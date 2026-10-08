# OpenRouter → Gemini 3.8 Flash

Extracts structured statement data after Docling converts the PDF.
Existing workflow model: `openrouter:google/gemini-3.8-flash`.
Setup: **existing API key + CLI**; console only for account, credits, or key replacement.

## Configure

Keep the existing `OPENROUTER_API_KEY` in local environment/`.env`. Use the
[secret helper](README.md) to copy only this value to Google Secret Manager:

```sh
publish_trx_secret OPENROUTER_API_KEY trx-openrouter-key
```

The Cloud Run guide grants access and maps the secret back to
`OPENROUTER_API_KEY`. The model currently lives in `workflow.py`, not an environment
variable. No separate Gemini key or Google AI deployment is needed.

## Verify and budget

Run one authorized end-to-end sample after deployment. Confirm extraction returns
the expected schema; record billable input, output/thinking tokens, and cost.
Keep keys and financial document contents out of logs.

Budget assumption: 20,000 total tokens/PDF; input/output split still needs
measurement. Retry and fallback calls add usage. Ensure the OpenRouter account
has credits. Optional LangSmith tracing is disabled in the initial Run command;
enabling it requires its own secret and a deliberate document-data policy.

[Model and pricing](https://openrouter.ai/google/gemini-3.8-flash)
· [Account/billing support](https://openrouter.ai/support/)
