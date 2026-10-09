# Deployment

Deploy the FastAPI backend on Cloud Run with Supabase Auth/PostgreSQL, private Cloud Storage, Cloud Tasks processing, and scheduled maintenance. The frontend routes browser requests to FastAPI on the same origin.

[System design](../trx-system-design/README.md) explains the architecture. These guides describe setup and verification, not the current state of any cloud account. Run commands from `apps/agent-trx-classifier`.

## Setup order

1. Complete the Google Cloud bootstrap below.
2. Configure the [database connection and apply migrations](supabase.md).
3. Configure [authentication](authentication.md), [Storage](cloud-storage.md), and [Tasks](cloud-tasks.md#create-and-authorize).
4. Publish [OpenRouter](openrouter.md), [TypeSafe](typesafe.md), database secrets.
5. Build and deploy [Cloud Run](cloud-run.md), then configure its direct URL.
6. Create the [maintenance schedule](cloud-tasks.md#scheduled-maintenance) and configure frontend routing.
7. Run the launch checks below.

| Guide | Service responsibility |
| --- | --- |
| [Authentication](authentication.md) | Supabase sign-in, token verification and frontend routing. |
| [Supabase](supabase.md) | Private application tables, SQL connections and listener connection. |
| [Cloud Storage](cloud-storage.md) | Private PDF and CSV inputs. |
| [Cloud Tasks and maintenance](cloud-tasks.md) | Processing delivery, retry controls and Cloud Scheduler invocation. |
| [Cloud Run](cloud-run.md) | Backend image, secrets, resources, deployment and rollback. |
| [OpenRouter](openrouter.md) | Statement extraction provider. |
| [TypeSafe](typesafe.md) | Transaction classification provider. |

## Google Cloud bootstrap

Install [gcloud](https://cloud.google.com/sdk/docs/install) and uv. Use provider consoles for account creation, billing and credential setup. Reuse an existing project where appropriate; run project/service-account creation commands only for resources that do not already exist.

Fill in the Google Cloud settings in your selected env file before deployment. Use `TASKS_LOCATION` as the region for Run, Tasks and Storage. The service name `trx-classifier` below is an example. `RUNTIME_EMAIL` selects the backend service account for deployment and resource permissions; it is not a secret or an application credential.

Open a shell with the existing production settings loaded:

```sh
uv run --env-file .env.prod bash
```

Run the remaining deployment commands in that shell. Use `.env` instead if that file contains the intended settings. Neither command modifies the file.

```sh
gcloud auth login
gcloud projects create "$GOOGLE_CLOUD_PROJECT"
gcloud config set project "$GOOGLE_CLOUD_PROJECT"
gcloud billing accounts list
gcloud billing projects link "$GOOGLE_CLOUD_PROJECT" --billing-account=YOUR_BILLING_ACCOUNT_ID
gcloud services enable run.googleapis.com cloudtasks.googleapis.com cloudscheduler.googleapis.com storage.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com iam.googleapis.com
gcloud iam service-accounts create "${RUNTIME_EMAIL%%@*}"
gcloud iam service-accounts create "${TASK_CALLER_EMAIL%%@*}"
gcloud iam service-accounts create "${MAINTENANCE_CALLER_EMAIL%%@*}"
```

The deploying identity needs permissions to build/deploy, manage resources and act as the relevant service accounts. Runtime permissions are scoped in each guide.

## Secrets and configuration

[`.env.example`](../../.env.example) is the configuration reference. Deployment commands reuse those same application variable names. The container image and resource names are supplied in the commands.

Store the database URL and AI keys in Secret Manager. Resource identifiers, origins, caller emails and the Supabase publishable key are configuration. The backend and migrations use the same `DATABASE_URL`.

Define this helper in Bash or Zsh. It reads one value from the environment or local `.env` and sends it directly to Secret Manager:

```sh
set -o pipefail
publish_trx_secret() {
  uv run python -c 'import os, sys; from dotenv import load_dotenv; load_dotenv(".env", interpolate=False); value = os.environ[sys.argv[1]]; assert value, "Empty secret"; sys.stdout.write(value)' "$1" |
    gcloud secrets create "$2" --replication-policy=automatic --data-file=-
}
```

For an existing secret, replace `create` with `gcloud secrets versions add NAME --data-file=-`. Mount numeric secret versions and redeploy when rotating. Never upload the entire `.env` or bake credentials into the image.

## Launch checks

- Complete Supabase login and logout in the frontend; verify token rejection and job ownership through the deployed proxy.
- Reject unauthenticated requests, invalid or expired tokens, cross-owner reads, and wrong internal caller identities.
- Submit a PDF and CSV; verify persisted status, stage events and results. Check file-size rejection.
- Submit more jobs than queue concurrency; measure processing and event responsiveness together.
- Verify repeated submission keys, duplicate delivery, unknown enqueue outcome, checkpoint recovery and exhausted attempts.
- Verify maintenance runs when the backend has scaled to zero and records terminal outcomes after handler crashes.
- Disconnect/reconnect the browser and database listener; replay events without losing or duplicating applied updates.
- Confirm private bucket access, database access, backups and restore procedures.
- Set measured resource limits, a retention policy and operational monitoring before launch.

The API accepts one file per request. Multi-file submissions, active-job listing, file downloads and user cancellation require additional interfaces. Retained files and event history have no automatic deletion policy. Frontend hosting is configured separately.
