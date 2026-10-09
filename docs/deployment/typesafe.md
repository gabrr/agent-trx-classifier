# TypeSafe classification

The classifier uses the TypeSafe SDK to classify extracted transactions through Jev. The model and request implementation live in [the Jev adapter](../../src/tools/single_model/jev.py).

## Configure

Set `TYPESAFE_API_KEY` through your local secret-management process, then use the [secret helper](README.md#secrets-and-configuration):

```sh
publish_trx_secret TYPESAFE_API_KEY trx-typesafe-key
```

[Cloud Run](cloud-run.md) grants secret access and maps it to the application. Jev receives extracted fields/text rather than raw PDFs.

## Verify and measure

Classify representative statements and compare outputs against the [contract](../trx-classifier-contract.md). Record provider usage, errors and repeated calls. Completed job deliveries read persisted results instead of calling the model again.

Checkpoint compatibility uses a fingerprint of the classifier code and configured model identifiers. Changes behind the mutable `jev-latest` alias are not detected automatically. See [checkpoint recovery](../trx-system-design/01-architecture-and-services.md#recovery).

[TypeSafe models](https://docs.typesafe.ai/models), [account](https://typesafe.ai/).
