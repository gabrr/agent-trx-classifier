# Cloud Run

Cloud Run hosts the FastAPI user API, processing handler, maintenance handler and event streams. Complete the [bootstrap](README.md#google-cloud-bootstrap), database, authentication, bucket, queue and secret setup first.

## Before deployment

The [Docker setup](../database-and-docker/README.md) uses locked dependencies, CPU PyTorch and one non-root Uvicorn process. Docling models download on first conversion; measure cold-start time and decide whether to cache them in the production image.

Verify hosted login, real task delivery, proxy streaming and concurrent conversion capacity before launch. The [security guide](../trx-system-design/03-security-and-identity.md) explains why FastAPI authenticates each route family.

## Build and deploy

Use the shell loaded with your selected env file from [bootstrap](README.md#google-cloud-bootstrap). Confirm `AUTH_SUPABASE_URL` and `AUTH_SUPABASE_PUBLISHABLE_KEY` are configured as described in [authentication setup](authentication.md). The shell-local `image` value identifies this release; `_IMAGE` passes it to Cloud Build. The example mounts secret version 1; substitute each secret's actual version.

```sh
gcloud artifacts repositories create trx --repository-format=docker --location="$TASKS_LOCATION"
image="${TASKS_LOCATION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/trx/backend:YOUR_UNIQUE_RELEASE_TAG"
# Build the runtime target explicitly; the Dockerfile's final stage is the test image.
cat > /tmp/trx-cloudbuild.yaml <<'YAML'
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '--target', 'runtime', '-t', '${_IMAGE}', '.']
images: ['${_IMAGE}']
YAML
gcloud builds submit --config=/tmp/trx-cloudbuild.yaml \
  --substitutions="_IMAGE=$image" .

for secret in trx-openrouter-key trx-typesafe-key trx-database-url; do
  gcloud secrets add-iam-policy-binding "$secret" --member="serviceAccount:$RUNTIME_EMAIL" --role=roles/secretmanager.secretAccessor
done

gcloud run deploy trx-classifier \
  --image="$image" --region="$TASKS_LOCATION" \
  --service-account="$RUNTIME_EMAIL" --allow-unauthenticated \
  --min=0 --max=4 --concurrency=40 --cpu=1 --memory=2Gi \
  --timeout=1800 --cpu-throttling \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,TASKS_LOCATION=$TASKS_LOCATION,GCS_BUCKET=$GCS_BUCKET,TASKS_QUEUE=$TASKS_QUEUE,TASK_CALLER_EMAIL=$TASK_CALLER_EMAIL,MAINTENANCE_CALLER_EMAIL=$MAINTENANCE_CALLER_EMAIL,LANGSMITH_TRACING=false,AUTH_SUPABASE_URL=$AUTH_SUPABASE_URL,AUTH_SUPABASE_PUBLISHABLE_KEY=$AUTH_SUPABASE_PUBLISHABLE_KEY" \
  --set-secrets="OPENROUTER_API_KEY=trx-openrouter-key:1,TYPESAFE_API_KEY=trx-typesafe-key:1,DATABASE_URL=trx-database-url:1"

export BACKEND_URL="$(gcloud run services describe trx-classifier --region="$TASKS_LOCATION" --format='value(status.url)')"
gcloud run services update trx-classifier --region="$TASKS_LOCATION" --update-env-vars="BACKEND_URL=$BACKEND_URL"
curl --fail "$BACKEND_URL/health"
```

Builds require the selected Cloud Build service account to have the documented
build permissions. If organization policy blocks a public endpoint, resolve that
policy before using this single-service, route-authenticated design.

`--allow-unauthenticated` opens Cloud Run's transport; FastAPI must protect user
routes and the internal route separately. Cloud Run IAM cannot protect just one
route. Verify task audience and the allowed service-account identity.

The initial revision lacks `BACKEND_URL`, so job configuration and internal authentication fail closed. Complete the URL update and verify OIDC before allowing submissions. Then configure [scheduled maintenance](cloud-tasks.md#scheduled-maintenance). Verify shutdown/cancellation and durable recovery during revision replacement.

CPU, memory, instance cap, and request concurrency above are initial candidates.
Request concurrency includes SSE and uploads; **do not set it to 2 to limit jobs**.
The queue controls dispatches. Benchmark two conversions and their memory use;
raise CPU/memory if needed. Use a shorter application deadline to attempt
cancellation and persist timeout failure before task expiry. Do not automatically
continue timed-out runs; fence late writes and use durable failure finalization.
See [job recovery](../trx-system-design/01-architecture-and-services.md#recovery).

## Verify

Confirm `/docs`, `/redoc`, and `/openapi.json` return 404 without authentication. See the [security guide](../trx-system-design/03-security-and-identity.md) for route access rules.

Upload two PDFs and confirm both can progress while SSE remains responsive.
Reject unauthenticated internal requests. Reconnect SSE and replay saved events;
streams must reconnect before/after the Run timeout. Keep zero minimum instances
and request billing initially; open SSE streams still incur active billing.

## Rollback

Use a unique image tag for each deployment and record the last known good revision.
If a new revision fails validation, direct traffic back to the recorded revision:

```sh
gcloud run revisions list --service=trx-classifier --region="$TASKS_LOCATION"
gcloud run services update-traffic trx-classifier --region="$TASKS_LOCATION" --to-revisions=LAST_KNOWN_GOOD_REVISION=100
```

Keep database changes backward-compatible with that revision. Traffic rollback
does not undo migrations or restart existing task attempts; use the persisted
claim/recovery rules. Avoid logging PDF contents, credentials, or access tokens;
emit sanitized structured logs with job/attempt IDs and persist safe failure reasons.
Configure monitoring for failed/stuck jobs, provider errors, queue age, event delay and database connections.

[Container builds](https://cloud.google.com/build/docs/building/build-containers)
· [Build substitutions](https://cloud.google.com/build/docs/configuring-builds/substitute-variable-values)
· [Build/deploy permissions](https://cloud.google.com/run/docs/deploying-source-code)
· [Secret configuration](https://cloud.google.com/run/docs/configuring/services/secrets)
