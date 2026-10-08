# Google Cloud Tasks

One task per PDF, one shared queue, **up to two concurrent dispatches** across
all users. Setup: **CLI**. Run after the [bootstrap](README.md).

## Create and authorize

```sh
gcloud tasks queues create "$TRX_QUEUE" --location="$TRX_REGION" --max-concurrent-dispatches=2 --max-dispatches-per-second=2 --max-attempts=5 --min-backoff=10s --max-backoff=300s

gcloud tasks queues add-iam-policy-binding "$TRX_QUEUE" --location="$TRX_REGION" --member="serviceAccount:$TRX_RUNTIME_SA" --role=roles/cloudtasks.enqueuer

gcloud iam service-accounts add-iam-policy-binding "$TRX_TASK_SA" --member="serviceAccount:$TRX_RUNTIME_SA" --role=roles/iam.serviceAccountUser

gcloud tasks queues describe "$TRX_QUEUE" --location="$TRX_REGION"
```

Keep Google's Cloud Tasks service-agent role intact; it generates the OIDC token.
The task-caller identity needs no database, storage, or AI access.

## Application integration

Refactor the existing `classify` workflow into the processing handler below.
The browser uploads through the job API; only authenticated tasks trigger that
handler. Keep the TRX conversion/extraction/classification workflow reusable.

Create tasks using the Google client library and runtime service identity:

- URL: `TASK_AUDIENCE + /internal/jobs/{id}/process`; method POST.
- OIDC service account: `TASK_CALLER_EMAIL`; audience: `TASK_AUDIENCE`.
- Payload: job reference only; PDF bytes stay in Storage.
- Set each task's dispatch deadline explicitly to **1,800 seconds**; finish or
  cancel work before that deadline. Return 204 after committing success or a
  terminal failure; use a retryable non-2xx only when automatic retry is intended.

Claim jobs atomically, identify attempts, and make completion idempotent. Retry
transient failures; persist permanent failure and acknowledge it. Recover expired
claims and record a terminal outcome when attempts are exhausted; do not leave
jobs permanently active. Queue retries alone do not maintain application status.

Two dispatches are not a strict cap on surviving executions after timeouts.
Global worker-slot enforcement is deferred. Attempt cancellation, fence stale
attempts, and prevent a timed-out worker from changing a terminal failure.

## Verify

Submit three jobs: at most two task requests should be outstanding. Inject one
transient failure and confirm its retry produces one persisted result. Test a
crash after result commit but before the 204 response.

[Queue settings](https://cloud.google.com/tasks/docs/configuring-queues)
· [Task creation and OIDC](https://cloud.google.com/tasks/docs/creating-http-target-tasks)
· [Deadlines](https://cloud.google.com/tasks/docs/reference/rest/v2/projects.locations.queues.tasks)

## Confirmed recovery decisions

These decisions are agreed; implementation is still pending. The queue command's
five attempts/backoff values are initial candidates, not a measured retry budget.

| Scenario | Chosen behavior |
| --- | --- |
| Job saved, enqueue fails or outcome is unknown | **Automatic recovery:** persist enqueue intent with the job in a transactional outbox; retry named task creation reliably. |
| Worker crashes halfway through | **Resume saved stages:** reuse completed conversion/extraction/classification checkpoints instead of restarting the whole PDF. |
| Temporary provider error | **Brief bounded retries inside the handler**, then a Cloud Tasks retry if attempts/time remain. Honor provider backoff and bound combined retries. |
| Retry budget exhausted | **Persist failure and show its reason to the user.** No automatic repair/reprocessing after failure; the user can explicitly retry. Retain diagnostics. |
| Processing deadline reached | **Persist timeout failure; attempt cancellation.** No automatic continuation or restart for that timed-out run. Revisit long-running processing later. |
| Result committed but acknowledgment lost | **Completed-job check:** repeated delivery returns success without another AI call or result write. |
| Timed-out worker survives alongside another delivery | **Keep the job failed and report the error.** Reject stale writes; do not start another attempt for that failed run. Global two-slot coordination is deferred. |

### Enqueue and checkpoint recovery

A durable authenticated dispatcher consumes outbox records; a background loop
alone is insufficient when Cloud Run can scale to zero. Trigger dispatch through
a scheduled maintenance invocation or another durable delivery mechanism; its
provisioning is implementation work. Use deterministic task names to reconcile
uncertain creates; task naming does not replace database idempotency.

Checkpoint each completed stage before advancing. Store structured outputs in
PostgreSQL; large converted text may use private Storage references. Record input
identity and workflow/model/schema versions; resume only compatible checkpoints.
An interrupted stage may run again and incur another provider charge. Attempt
claims and checkpoint/result writes must be fenced against stale workers.

### Failure, acknowledgment, and explicit retry

Maintain an application attempt budget independent of unverified task headers.
On success or terminal failure, commit the job outcome and durable event, issue
`NOTIFY job_updates` in that transaction, then acknowledge the task. A later
delivery for an already terminal run returns 204 without processing again.
Transient failures return non-2xx only while the application allows retries.

Do not rely on Cloud Tasks to update PostgreSQL when its retries end. Include a
durable finalization check for the case where the last handler crashes before
saving failure. A scheduled, authenticated finalization task on the shared queue
can enforce a persisted overall job deadline, inspect the run, fence it, and
record failure if still unfinished. This records an outcome; it does not repair
or restart the PDF. If PostgreSQL is unavailable, finalization must retry.
It reads recovery state, not periodically polled progress. Its deadline and
application retry budget must be coordinated with the queue configuration.

Use an application processing deadline shorter than 1,800 seconds, leaving time
to cancel and commit failure. If the process dies first, the finalization check
records the timeout/exhaustion outcome. Cancellation is best effort: reject late
writes even if the old process survives. Fencing does not guarantee exactly two
live executions; that stronger coordination is deferred by decision.

An authenticated, owner-checked user retry creates a new job linked to the failed
job, referencing the retained PDF and compatible checkpoints. Keep the original
failure/history intact. Make retry submission idempotent so repeated clicks do
not create multiple replacement jobs. Concurrent identical PDF uploads remain
allowed; content deduplication is deferred.

### Persisted outcome and diagnostics

| Outcome | Persist |
| --- | --- |
| Success | Structured result, completion timestamp, optional success message. |
| Failure | Stable error code, safe user-facing reason, failure timestamp, diagnostic reference. |
| Attempt | Job/attempt IDs, stage, timestamps, retry counts, outcome, and sanitized technical details. |

The upload already returned 202; later errors arrive through SSE and persisted
job status, not a second response to the upload. Use messages such as “Processing
timed out. Please try again.” Never expose stack traces, credentials, or private
provider responses to the user. Retain diagnostic records without PDF contents.

Cross-service log viewing, dashboards, alerting, and monitoring are **part two**.
Part one still records job outcomes/attempt diagnostics and sanitized structured
logs with job/attempt IDs; no additional logging platform is selected now.

### Verify these decisions

Test unknown enqueue outcome, crash after a checkpoint, bounded provider retries,
last-attempt crash/finalization, timeout, explicit retry, and a lost acknowledgment.
Ensure failed jobs emit a durable event, stale workers cannot overwrite failure,
and successful terminal deliveries do not call AI again.

[Delivery/retry limitations](https://cloud.google.com/tasks/docs/common-pitfalls)
