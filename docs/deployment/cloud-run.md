# Google Cloud Run

Hosts one FastAPI service: user endpoints, task handler, TRX workflow, and SSE.
Setup: **CLI**. Follow the [bootstrap](README.md) first.

## Before deployment

The Dockerfile and `.dockerignore` are implemented; see
[local build and checks](../database-and-docker/README.md). `trx-api` now runs one
non-root Uvicorn worker on `0.0.0.0:$PORT` (default 8080) with locked dependencies
and CPU PyTorch on Linux. Docling's required Linux libraries are installed.
Model artifacts currently download/cache on first conversion; decide whether to
pre-cache them in a production build and verify sizing before deployment.

Implement job routes, user authentication, and task OIDC verification before
exposing the service. Refactor the existing `classify` entry point into the internal
Cloud Tasks processing handler; browser submission goes through the job API.
Do not retain a public synchronous processing path that bypasses the queue.
Isolate CPU-heavy conversion from the async event loop so
SSE and other API requests remain responsive.

## Build and deploy

After the Dockerfile, application changes, and all five secrets exist, prepare
local `TRX_APP_ORIGIN`, `TRX_SUPABASE_URL`, and `TRX_SUPABASE_PUBLISHABLE_KEY` values
from [authentication setup](authentication.md). The encryption key is the fifth
secret. The example mounts secret version 1; use each secret's actual version.

```sh
gcloud artifacts repositories create trx --repository-format=docker --location="$TRX_REGION"
export TRX_IMAGE="${TRX_REGION}-docker.pkg.dev/${TRX_PROJECT_ID}/trx/backend:v1"
gcloud builds submit --tag "$TRX_IMAGE" .

for secret in trx-openrouter-key trx-typesafe-key trx-database-url trx-listener-url trx-token-encryption-key; do
  gcloud secrets add-iam-policy-binding "$secret" --member="serviceAccount:$TRX_RUNTIME_SA" --role=roles/secretmanager.secretAccessor
done

gcloud run deploy "$TRX_SERVICE" --image="$TRX_IMAGE" --region="$TRX_REGION" --service-account="$TRX_RUNTIME_SA" --allow-unauthenticated --min=0 --max=4 --concurrency=40 --cpu=1 --memory=2Gi --timeout=1800 --cpu-throttling --set-env-vars="GCP_PROJECT_ID=$TRX_PROJECT_ID,GCP_REGION=$TRX_REGION,PDF_BUCKET=$TRX_BUCKET,TASK_QUEUE=$TRX_QUEUE,TASK_CALLER_EMAIL=$TRX_TASK_SA,LANGSMITH_TRACING=false,APP_ORIGIN=$TRX_APP_ORIGIN,AUTH_CALLBACK_URL=$TRX_APP_ORIGIN/auth/callback,SUPABASE_URL=$TRX_SUPABASE_URL,SUPABASE_PUBLISHABLE_KEY=$TRX_SUPABASE_PUBLISHABLE_KEY,SUPABASE_JWT_ISSUER=$TRX_SUPABASE_URL/auth/v1,SUPABASE_JWT_AUDIENCE=authenticated,SUPABASE_JWKS_URL=$TRX_SUPABASE_URL/auth/v1/.well-known/jwks.json,AUTH_SESSION_TTL_SECONDS=86400,AUTH_LOGIN_ATTEMPT_TTL_SECONDS=300" --set-secrets="OPENROUTER_API_KEY=trx-openrouter-key:1,TYPESAFE_API_KEY=trx-typesafe-key:1,DATABASE_URL=trx-database-url:1,DATABASE_LISTENER_URL=trx-listener-url:1,TOKEN_ENCRYPTION_KEY=trx-token-encryption-key:1"

export TRX_SERVICE_URL="$(gcloud run services describe "$TRX_SERVICE" --region="$TRX_REGION" --format='value(status.url)')"
gcloud run services update "$TRX_SERVICE" --region="$TRX_REGION" --update-env-vars="TASK_AUDIENCE=$TRX_SERVICE_URL"
curl --fail "$TRX_SERVICE_URL/health"
```

Builds require the selected Cloud Build service account to have the documented
build permissions. If organization policy blocks a public endpoint, resolve that
policy before using this single-service, route-authenticated design.

`--allow-unauthenticated` opens Cloud Run's transport; FastAPI must protect user
routes and the internal route separately. Cloud Run IAM cannot protect just one
route. Verify task audience and the allowed service-account identity.

On the initial revision, the internal route must reject processing while
`TASK_AUDIENCE` is unset; enable enqueue/processing only after the URL update and
OIDC verification. Handle SIGTERM by stopping new claims, cancelling work safely,
and leaving recoverable state; close DB listeners and local SSE subscribers.

CPU, memory, instance cap, and request concurrency above are initial candidates.
Request concurrency includes SSE and uploads; **do not set it to 2 to limit jobs**.
The queue controls dispatches. Benchmark two conversions and their memory use;
raise CPU/memory if needed. Use a shorter application deadline to attempt
cancellation and persist timeout failure before task expiry. Do not automatically
continue timed-out runs; fence late writes and use durable failure finalization.
Follow the [confirmed recovery rules](cloud-tasks.md).

## Verify

Upload two PDFs and confirm both can progress while SSE remains responsive.
Reject unauthenticated internal requests. Reconnect SSE and replay saved events;
streams must reconnect before/after the Run timeout. Keep zero minimum instances
and request billing initially; open SSE streams still incur active billing.

## Rollback

Use a unique image tag for each deployment and record the last known good revision.
If a new revision fails validation, direct traffic back to the recorded revision:

```sh
gcloud run revisions list --service="$TRX_SERVICE" --region="$TRX_REGION"
gcloud run services update-traffic "$TRX_SERVICE" --region="$TRX_REGION" --to-revisions=LAST_KNOWN_GOOD_REVISION=100
```

Keep database changes backward-compatible with that revision. Traffic rollback
does not undo migrations or restart existing task attempts; use the persisted
claim/recovery rules. Avoid logging PDF contents, credentials, or callback codes;
emit sanitized structured logs with job/attempt IDs and persist safe failure reasons.
Cross-service log viewing/monitoring is part two, including failed/stuck jobs,
provider errors, queue backlog, and database connections.

[Build/deploy permissions](https://cloud.google.com/run/docs/deploying-source-code)
· [Secret configuration](https://cloud.google.com/run/docs/configuring/services/secrets)
