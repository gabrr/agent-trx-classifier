# Classifier documentation

Start with [system design](trx-system-design/README.md) to understand the backend, [usage](trx-classifier-usage.md) to run the classifier, or [deployment](deployment/README.md) to configure managed services.

| Guide | Purpose |
| --- | --- |
| [System design](trx-system-design/README.md) | Visual explanations of jobs, events, identity and capacity. |
| [Classifier architecture](trx-classifier-architecture.md) | Workflow stages and code responsibilities. |
| [Contract](trx-classifier-contract.md) | Inputs, results, API routes, errors and evaluation rules. |
| [Usage](trx-classifier-usage.md) | CLI/API entry points, credentials, dataset and evaluation commands. |
| [Database and Docker](database-and-docker/README.md) | Local setup, migrations, tests and persistence guarantees. |
| [Authentication and job integration](authentication-and-jobs.md) | Provider abstractions, services and their composition. |
| [Deployment](deployment/README.md) | Cloud setup, verification and recovery procedures. |
| [Agent instructions](../AGENTS.md) | Code style and documentation maintenance. |

## Proposals

These documents describe extensions, not current capabilities:

- [Authentication provider switching review](authentication-and-jobs.md#planned-authentication-review)
- [Context enrichment](trx-classifier-context-addon.md)
- [TRX Correction Memory](trx-correction-memory.md)

## Historical records

- [Database implementation handoff](database-and-docker/HANDOFF.md)
- [Database verification report](database-and-docker/IMPLEMENTATION.md)
- [Disposable frontend plan](trx-classifier-frontend-plan.md)

Use the current guides above for operating commands and system behavior.
