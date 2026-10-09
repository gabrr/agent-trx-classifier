# OpenRouter extraction

The classifier sends prepared statement text to OpenRouter for structured transaction extraction. The model is selected in [the classifier workflow](../../src/workflows/trx_classifier/workflow.py).

## Configure

Set `OPENROUTER_API_KEY` through your local secret-management process, then use the [secret helper](README.md#secrets-and-configuration):

```sh
publish_trx_secret OPENROUTER_API_KEY trx-openrouter-key
```

[Cloud Run](cloud-run.md) grants secret access and maps it to the application. The model is configured in code rather than through an environment variable.

## Verify and measure

Run a representative statement through the deployed workflow. Validate the extraction schema and measure actual billed usage, including failed or repeated attempts. Keep credentials and financial document contents out of logs. Ensure account credits and quotas support the intended workload.

Optional LangSmith tracing requires its own credentials and a policy for financial document data. See [usage credentials](../trx-classifier-usage.md#credentials).

[OpenRouter models](https://openrouter.ai/models), [account support](https://openrouter.ai/support/).
