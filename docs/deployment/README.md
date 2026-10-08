# Deployment plan

Status: agreed design; services have not been provisioned by these documents.
Use CLI for setup and deployment; use provider consoles for account creation,
billing, and credentials when needed. Run commands from `apps/agent-trx-classifier`.

## Services

| Guide | Purpose | Setup method |
| --- | --- | --- |
| [Cloud Run](cloud-run.md) | FastAPI, processing, and SSE. | gcloud CLI |
| [Cloud Tasks](cloud-tasks.md) | Queue; up to two concurrent processing requests. | gcloud CLI |
| [Cloud Storage](cloud-storage.md) | Private PDF files. | gcloud CLI |
| [Supabase](supabase.md) | PostgreSQL jobs, results, and events; Free plan initially. | CLI; dashboard for connection details |
| [OpenRouter](openrouter.md) | Gemini 3.8 Flash extraction. | Existing key; CLI secret upload |
| [TypeSafe](typesafe.md) | Jev classification, called directly. | Existing key; CLI secret upload |

See [authentication](authentication.md) for the proposed login/session design
and its [interactive walkthrough](../../../../docs/trx-classifier-authentication.html).

## Order of work

1. Bootstrap Google Cloud below when deployment is authorized; reuse the existing `acetate-agentic` Supabase project.
2. Create the private bucket and queue; upload database/AI secrets and the session encryption key.
   Configure Supabase Auth/Google login and same-origin browser routing.
3. Integrate the implemented repositories/listener/migration with the job API and provider adapters.
4. Add a container build and verify two simultaneous Docling workflows.
5. Deploy Cloud Run; configure its URL as the task audience and target.
6. Verify upload → queue → result, ownership, retries, and SSE recovery.

Current code has `/health` and synchronous `/classify`, a 25 MiB per-file limit,
and a process-local single-run lock. The asynchronous jobs design is still work
to implement. Local database repositories, migration `0001`, Docker packaging, and `/ready` are now implemented; see [database and Docker](../database-and-docker/README.md). Google/Supabase authentication adapters and durable job API/worker wiring remain to implement. Refactor
`classify` into the internal task processing handler, reusing its TRX workflow.

## Google Cloud bootstrap

Install [gcloud](https://cloud.google.com/sdk/docs/install), uv, and the
[Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started).
Create accounts/billing through the provider console if not already available.
Choose the region before creating resources; `us-central1` is an example, not a
final region decision. Keep Run, Tasks, and Storage together.

```sh
export TRX_PROJECT_ID="your-globally-unique-project-id"
export TRX_REGION="us-central1"
export TRX_SERVICE="trx-classifier"
export TRX_QUEUE="trx-processing"
export TRX_BUCKET="${TRX_PROJECT_ID}-pdfs"
export TRX_RUNTIME_SA="trx-runtime@${TRX_PROJECT_ID}.iam.gserviceaccount.com"
export TRX_TASK_SA="trx-task-caller@${TRX_PROJECT_ID}.iam.gserviceaccount.com"

gcloud auth login
gcloud projects create "$TRX_PROJECT_ID"
gcloud config set project "$TRX_PROJECT_ID"
gcloud billing accounts list
gcloud billing projects link "$TRX_PROJECT_ID" --billing-account=YOUR_BILLING_ACCOUNT_ID
gcloud services enable run.googleapis.com cloudtasks.googleapis.com storage.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com iam.googleapis.com
gcloud iam service-accounts create trx-runtime
gcloud iam service-accounts create trx-task-caller
```

The deploying identity needs permission to build/deploy, manage these resources,
and act as the runtime service account. Use an administrator for initial bootstrap;
application permissions are scoped in the service guides.

## Secrets and configuration

Runtime keys already used: `OPENROUTER_API_KEY`, `TYPESAFE_API_KEY`.
Proposed additions: `DATABASE_URL`, `DATABASE_LISTENER_URL`, `GCP_PROJECT_ID`,
`GCP_REGION`, `PDF_BUCKET`, `TASK_QUEUE`, `TASK_AUDIENCE`, `TASK_CALLER_EMAIL`.
Database URLs are secrets; the remaining additions are ordinary configuration.
[Authentication](authentication.md) adds Supabase/app-origin/session settings and
secret `TOKEN_ENCRYPTION_KEY`; the Cloud Run command includes those mappings.
Recommended user authentication: Supabase Auth with a custom server-managed
browser session. This is a proposal; see [authentication](authentication.md)
for configuration, trade-offs, and required controls.

Define this helper once. It reads one value from the environment or local `.env`
and pipes it directly into Secret Manager. Never upload the complete `.env`.
Run in Bash/Zsh with pipeline failure propagation enabled.

```sh
set -o pipefail
publish_trx_secret() {
  uv run python -c 'import os, sys; from dotenv import load_dotenv; load_dotenv(".env"); value = os.environ[sys.argv[1]]; assert value, "Empty secret"; sys.stdout.write(value)' "$1" |
    gcloud secrets create "$2" --replication-policy=automatic --data-file=-
}
```

For an existing secret, use `gcloud secrets versions add NAME --data-file=-`
in the helper instead of `create`. Pin a numeric version in Cloud Run and redeploy
when rotating. Do not bake `.env` or credentials into the container image.

## Launch checks

- Any number of PDFs per batch, total ≤ **30,000,000 bytes**, checked by client and
  backend; bound the complete multipart request below Cloud Run's 32 MiB limit.
- One job per accepted PDF; valid files accepted even when others are rejected.
- One shared queue dispatches at most two requests; processing stays within its
  30-minute dispatch deadline; acknowledge only after durable success/failure.
- Authenticate users and enforce ownership; verify task OIDC separately.
- Durable events, transactional `NOTIFY job_updates`, no periodic progress polling.
- Register the subscriber/listener before replay, deduplicate, and recover after
  reconnect. Heartbeats do not query PostgreSQL. Close SSE after terminal success or failure.
- Recover failed enqueue operations automatically through a transactional outbox.
- Resume compatible saved stages; use bounded in-handler retries before queue retries.
- Persist safe failure reasons and diagnostics; terminal failures require explicit
  user retry. Timeout continuation/global worker slots are deferred.

Keep accepted source PDFs after extraction; exact duplicate detection is deferred.
Final retention/deletion rules and CPU/memory sizing remain implementation decisions.
[Cloud Tasks](cloud-tasks.md) records the confirmed recovery choices and terminal
outcome rules. Cross-service logs/monitoring are part two; job diagnostics are part one.
The browser application deployment is outside these six backend service guides.
