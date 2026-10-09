# System design

These guides explain the backend implemented in this repository. Cloud deployment requires the setup and verification in [deployment](../deployment/README.md).

| Guide | Question |
| --- | --- |
| [Architecture and jobs](01-architecture-and-services.md) | Where does work run, and how is a job recovered? |
| [Events and live updates](02-events-and-live-updates.md) | How does the browser receive and replay progress? |
| [Security and identity](03-security-and-identity.md) | Who can submit, process, or read a job? |
| [Capacity and cost](04-capacity-and-cost.md) | What must be measured before choosing limits? |

The backend accepts one PDF or CSV per job. It does not expose multi-file submission, active-job listing, user cancellation, or file-download routes. [API source](../../src/api/jobs.py) defines the available job endpoints.

For local execution, see [usage](../trx-classifier-usage.md) and [Database and Docker](../database-and-docker/README.md). For provider abstractions and their composition, see [authentication and jobs](../authentication-and-jobs.md).
