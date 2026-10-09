# Architecture and jobs

FastAPI accepts a statement file, stores a job, and asks Cloud Tasks to deliver a processing request. The browser reads progress separately. Closing the browser does not cancel the job.

## Services and data

```mermaid
flowchart TB
    B[Browser] -->|Same-origin routing| F[FastAPI on Cloud Run]
    B <-->|Sign in and client session| A[Supabase Auth]
    F -->|Token verification keys| A
    F <-->|Profiles, jobs, outbox, events and results| D[(PostgreSQL on Supabase)]
    F <-->|Upload and retrieve private inputs| S[Cloud Storage]
    F <-->|Create tasks and receive authenticated delivery| Q[Cloud Tasks]
    C[Cloud Scheduler] -->|Authenticated maintenance invocation| F
```

| Component | Responsibility |
| --- | --- |
| Browser | Authenticate, submit a file, retain its job ID, and display progress and results. |
| Job service | Save uploads, create jobs and enqueue intents, dispatch tasks, and run maintenance. |
| Cloud Tasks | Deliver processing requests with queue rate and retry controls. |
| Processing workflow | Claim an attempt, retrieve the file, run conversion/extraction/classification, and persist checkpoints and outcomes. |
| PostgreSQL | Store ownership, user profiles, job state, attempts, ordered events, checkpoints, outbox intents, and results. |
| Cloud Storage | Store private input files under immutable object names. |
| Cloud Scheduler | Invoke maintenance even when Cloud Run has no active instance. |

## Submission and processing

```mermaid
sequenceDiagram
    participant B as Browser
    participant F as FastAPI
    participant S as Cloud Storage
    participant D as PostgreSQL
    participant Q as Cloud Tasks
    B->>F: POST /api/jobs with file and idempotency key
    Note over F: Verify Bearer token and validate file
    F->>S: Upload private file
    F->>D: Commit file record, job, outbox and queued event
    F->>Q: Attempt named task creation
    Note over F,D: Failed dispatch remains pending in the outbox
    F-->>B: 202 with job ID and status
    Q->>F: POST /internal/process with job_id and OIDC token
    F->>D: Claim attempt under job row lock
    F->>S: Read persisted object generation
    Note over F: Run classifier and save progress/checkpoints
    F->>D: Commit result, terminal status and event
    F-->>Q: 204
```

The file upload and database commit are separate operations. If a commit outcome is unknown, the service retains the private object because a committed job may reference it. Retention reconciliation must handle abandoned objects separately.

A submission key is scoped to the authenticated user. Repeating the same submission returns its existing job; reusing the key for another file or retry is rejected. Identical files with different keys can create separate jobs.

## Job states

```mermaid
stateDiagram-v2
    [*] --> queued: Submission committed
    queued --> running: Attempt claimed
    running --> succeeded: Result committed
    running --> queued: Retryable error within budget
    queued --> failed: Delivery budget or deadline exhausted
    running --> failed: Permanent error, cancellation or deadline
    succeeded --> [*]
    failed --> [*]
```

A user retry of a failed job creates a new linked job. It does not reopen the original job. Cancellation in this diagram means processing cancellation by the server; there is no user cancellation endpoint.

## Recovery

| Situation | Behavior |
| --- | --- |
| Job committed, task creation fails or is uncertain | Retry the persisted outbox intent. Reconcile an existing task by its request contents. |
| Google remembers a task name after deleting the task | Save a fresh delivery intent within the recovery policy. |
| Duplicate delivery while an attempt is active | Return retryable 409. |
| Delivery after success or failure | Return 204 without running the classifier again. |
| Retryable processing error | Release the attempt and return 503 while attempts and time remain. |
| Saved stage from a previous attempt | Resume only when input, workflow, model and schema versions match. |
| Deadline or attempt budget exhausted | Commit failure and a safe error event. Maintenance finalizes jobs whose handler did not save an outcome. |
| Old attempt tries to write | Reject it unless its attempt ID, claim and deadline are still valid. |

The processing deadline is reduced when work first starts and is not reset by automatic retries. A timeout ends that job; an explicit user retry gets a new deadline. Completed stages can be reused, but an interrupted stage may run again and incur another provider charge. The application wrapper does not implement a separate provider retry loop; SDK retry behavior depends on each adapter.

Queue concurrency limits outstanding dispatches. It does not guarantee that timed-out provider calls have stopped. Attempt checks protect database writes; the implementation has no global worker-slot coordinator. Cloud Tasks also does not guarantee execution order. [Delivery limitations](https://cloud.google.com/tasks/docs/common-pitfalls)

## Interfaces and source

[API reference](../trx-classifier-contract.md#http-api) lists the routes. Implementation: [job service](../../src/services/jobs/postgres.py), [processor](../../src/workflows/job_processing/workflow.py), [job repository](../../src/db/repositories/jobs.py), and [task adapter](../../src/tools/task_queue/google.py).

[Events](02-events-and-live-updates.md) explains progress delivery. [Cloud Tasks deployment](../deployment/cloud-tasks.md) owns queue and maintenance setup.
