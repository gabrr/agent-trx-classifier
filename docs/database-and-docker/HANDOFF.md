# Database and Docker implementation handoff

> Historical implementation plan. Its proposed commands, limits and future-work descriptions are not the current system contract. Use [Database and Docker](README.md) for setup and [system design](../trx-system-design/README.md) for current behavior.

Status: agreed implementation plan, not completed implementation. This document
contains the table definitions so the implementation agent does not need to
redesign them. Do not create another production database.

## Scope and source of truth

Implement connections, migrations, table models, repositories, Docker packaging,
and simple local checks inside `apps/agent-trx-classifier`.

Reuse patterns from `apps/backend` and `apps/agent-normalizer`. TRX's existing
models and interfaces win every conflict. The authoritative output contract is
[`src/workflows/trx_classifier/models.py`](../../src/workflows/trx_classifier/models.py).
Preserve `classify()`, `events()`, nullable extracted fields, original monetary
strings, and TRX's probability validation. Do not copy backend migrations wholesale.

Excluded: budgets, wealth tables, learned rules, embeddings, identical-PDF
rejection, complete login implementation, Cloud Tasks integration, Cloud Run
deployment, and monitoring dashboards. Keep simple activity history in scope.

## Environments

| | Local | Production database |
| --- | --- | --- |
| PostgreSQL | Docker Compose container | Existing Supabase project `acetate-agentic` |
| Database | `trx_dev`; separate `trx_test` for tests | `postgres` |
| Application schema | `private` | `private` |
| Application role | Restricted `trx_app` | Restricted `trx_app` |
| Migration connection | Local administrator | Existing administrative connection |

The Supabase connection was tested from TRX on October 8, 2026. It connected as
`postgres` to database `postgres`. The only non-template database was `postgres`;
`public` had no tables. The existing service schemas were `auth`, `storage`,
`realtime`, `vault`, `extensions`, `graphql`, and `graphql_public`. No TRX tables
or `private` schema existed at that check. Supabase project names and PostgreSQL
database names are distinct.

Leave Supabase-managed schemas untouched. Application tables belong in `private`,
excluded from Supabase's exposed Data API schemas. PDFs use private Google Cloud
Storage, not Supabase Storage.

Current database configuration is documented in [Database and Docker](README.md#configuration-and-supabase-boundary). The application, listener and migrations use one `DATABASE_URL` with its password included.

## Complete table definitions

All following tables belong to `private`. `?` means nullable. `id` means a UUID
primary key unless another type is stated. Every timestamp uses `timestamptz`.
Use timezone-aware UTC defaults. Foreign keys refer to the tables in this schema.
Only fields marked `?` are nullable. These are proposed persistence definitions;
they do not change TRX's public classifier output.

### Users, categories, and accounts

```text
users
  id UUID PK                  verified Supabase user ID; not generated locally
  email text?
  display_name text?
  created_at timestamptz
  updated_at timestamptz

report_buckets
  key text PK
  label text

categories
  id UUID PK
  owner_id UUID? FK users
  key text
  name text
  is_system boolean
  created_at timestamptz
  updated_at timestamptz

accounts
  id UUID PK
  owner_id UUID FK users
  name text
  type text
  institution_name text?
  currency text
  opening_balance numeric
  is_active boolean
  created_at timestamptz
  updated_at timestamptz
```

- Supabase Auth remains authoritative for identity and email. Synchronize profile
  data from verified authentication, never an unverified request body. Authentication
  integration is later; repositories must accept verified user IDs now.
- Add a foreign key from `users.id` to `auth.users.id` only if Auth uses this same
  Supabase project. Local PostgreSQL must not require fake Supabase service schemas.
- Seed report buckets: `installments`, `fixed`, `variable`, `movements`.
- Categories are optional named application categories, separate from report
  buckets. TRX currently returns no category ID.
- Require system categories to have no owner and user categories to have an owner.
  Use separate unique indexes for system `key` and user `(owner_id, key)`.
- Accounts are optional statement associations. Do not infer them from institution
  names or require them to store a classifier result.

### Statements, transactions, and metrics

```text
statements
  id UUID PK
  job_id UUID UNIQUE FK jobs
  owner_id UUID FK users
  account_id UUID? FK accounts
  kind text
  institution_name text?
  currency text?
  statement_due_date date?
  statement_close_date date?
  statement_total text?
  page_count integer?
  created_at timestamptz

transactions
  id UUID PK
  trx_id text                 original TRX output id
  statement_id UUID FK statements
  owner_id UUID FK users
  position integer            preserves output ordering
  category_id UUID? FK categories
  date date?
  description text?
  amount text?
  currency text?
  cardholder text?
  card_last4 text?
  payment_method text?
  merchant_name text?
  installments_current integer?
  installments integer?
  foreign_amount text?
  foreign_currency text?
  running_balance text?
  report_bucket text FK report_buckets
  classification_confidence double precision
  classification_probabilities jsonb
  report_bucket_override text? FK report_buckets
  created_at timestamptz
  updated_at timestamptz

run_metrics
  job_id UUID PK FK jobs
  elapsed_seconds double precision
  classification_seconds double precision
  classification_model_calls integer
  transaction_count integer
```

- Statement kinds: `credit_card`, `checking_account`, `unknown`.
- One statement per successful job. Unique transaction `(statement_id, trx_id)`
  and `(statement_id, position)`; do not assume TRX IDs are globally unique.
- Preserve original AI bucket, confidence, and probabilities. User edits change
  `report_bucket_override`; the effective bucket is override or original bucket.
- All four probability keys are required, values must be finite and between 0
  and 1, and their sum must match TRX's existing tolerance (`abs_tol=0.02`).
  Validate through the existing TRX model before persistence.
- Do not require backend-only fields such as `transaction_nature`,
  `classification_reason`, draft state, or reversal state.
- Do not invent missing dates, descriptions, currencies, amounts, or accounts.
  Money remains text here; future financial calculations need validated decimal
  conversion. Do not silently round or transform amount signs.
- Save statement, transactions, metrics, original JSON result, and successful job
  completion in one transaction. Repeated completion must not duplicate records.

### Files, batches, and jobs

```text
uploaded_files
  id UUID PK
  owner_id UUID FK users
  filename text
  content_type text
  size_bytes bigint
  storage_bucket text
  storage_object text
  storage_generation text?
  checksum text?
  status text
  created_at timestamptz
  updated_at timestamptz

batches
  id UUID PK
  owner_id UUID FK users
  created_at timestamptz

jobs
  id UUID PK
  owner_id UUID FK users
  batch_id UUID? FK batches
  uploaded_file_id UUID FK uploaded_files
  retry_of_job_id UUID? FK jobs
  submission_key text
  status text
  current_stage text?
  active_attempt_id UUID? FK job_attempts
  claim_expires_at timestamptz?
  deadline_at timestamptz?
  result jsonb?
  result_schema_version text?
  success_message text?
  error_code text?
  error_reason text?
  diagnostic_reference text?
  created_at timestamptz
  updated_at timestamptz
  started_at timestamptz?
  finished_at timestamptz?
```

- Each accepted PDF gets its own job; batches only group submissions. The agreed
  upload allowance is any number of PDFs totaling at most 30,000,000 bytes.
  Upload transport and the existing file-limit adjustment are later API work.
- Job states: `queued`, `running`, `succeeded`, `failed`.
- Unique `(owner_id, submission_key)` prevents accidental repeated submissions.
  Identical-file rejection is deferred; checksum is not a uniqueness constraint.
- A deliberate user retry gets a new job and submission key, links the old job,
  and may reuse the retained PDF and compatible checkpoints.
- `result` is the original `NormalizedStatement` snapshot. Later user edits affect
  queryable transactions, not this original snapshot.
- Preserve PDFs and their references. Do not add automatic deletion on success.
- Handle the jobs/attempts foreign-key cycle explicitly in migrations; an active
  attempt must belong to the same job, not merely exist.

### Attempts, progress, recovery, and scheduling

```text
job_attempts
  id UUID PK
  job_id UUID FK jobs
  attempt_number integer
  status text
  claim_expires_at timestamptz?
  started_at timestamptz
  finished_at timestamptz?
  error_code text?
  error_details jsonb?

events
  id UUID PK
  job_id UUID FK jobs
  sequence bigint
  attempt_id UUID? FK job_attempts
  event_type text
  data jsonb
  created_at timestamptz

checkpoints
  id UUID PK
  job_id UUID FK jobs
  attempt_id UUID FK job_attempts
  stage text
  output jsonb?
  storage_reference text?
  input_fingerprint text
  workflow_version text
  model_version text
  schema_version text
  created_at timestamptz

outbox
  id UUID PK
  job_id UUID FK jobs
  action text
  task_name text UNIQUE
  payload jsonb
  dispatch_status text
  retry_count integer
  next_attempt_at timestamptz?
  dispatched_at timestamptz?
  last_error text?
  created_at timestamptz
```

- Unique `(job_id, attempt_number)` and `(job_id, sequence)`.
- Claim jobs atomically. Fence writes with the active attempt ID and claim expiry;
  stale attempts cannot write progress or replace terminal results.
- Retain TRX event names: `step_started`, `step_completed`, `result`, `error`.
  Additional job lifecycle names are separate from that existing contract.
- Append events and execute `NOTIFY job_updates` with the job reference in the
  same transaction. Notification payloads do not contain extracted data.
- Allocate sequences safely under concurrency, for example by locking the job
  row. Do not use an unlocked `MAX(sequence) + 1`.
- Create jobs and their outbox enqueue intents atomically. Dispatch is later work.
- Checkpoints need saved output or a private Storage reference. Only reuse stages
  with compatible input/workflow/model/schema versions.
- Recovery policy: automatic enqueue recovery; resume compatible stages after
  crashes; brief bounded provider retries before queue retries; terminal failure
  with a safe reason when exhausted or beyond deadline; manual retry creates a
  new job. Queue concurrency of two is a later Cloud Tasks setting, not a database
  guarantee that stale workers have stopped.

### Simple user activity history

```text
activity_events
  id UUID PK
  changed_by UUID FK users
  entity_id UUID
  field text
  old_value jsonb?
  new_value jsonb?
  created_at timestamptz
```

One row per changed field: who changed it, which record/field, what it was, what
it is, and when. Keep this exact simple shape; do not add context snapshots,
embedding fields, actor types, or undo infrastructure.

Verify ownership, read the real old value, and save the edit and activity event
in the same transaction. For bucket edits, record effective old/new bucket values.
Activity rows are append-only. Initial edit support concerns transactions;
`entity_id` stays generic for future backend entities. Vector processing is later.

### Authentication persistence only

```text
sessions
  id_hash text PK
  owner_id UUID FK users
  encrypted_provider_tokens bytea
  encryption_key_version text
  csrf_token_hash text
  expires_at timestamptz
  revoked_at timestamptz?
  refresh_version bigint
  refresh_claim_expires_at timestamptz?
  created_at timestamptz

login_attempts
  id_hash text PK
  browser_binding_hash text
  encrypted_pkce_verifier bytea
  encryption_key_version text
  expires_at timestamptz
  consumed_at timestamptz?
  created_at timestamptz
```

Do not store raw session IDs, plaintext provider tokens, or plaintext PKCE
verifiers. Full login/refresh behavior is outside this stage.

## Ownership, indexes, and permissions

- Every repository user operation accepts the verified owner ID and scopes its
  query to it. Never trust an owner ID submitted in the request body.
- Reject cross-owner links among batches, files, jobs, statements, accounts,
  transactions, retries, and user categories. System categories are shared.
- Index owner-scoped jobs by status/creation time, statement transactions by
  position, events by job/sequence, and outbox items by dispatch status/retry time.
  Index referencing foreign keys where needed for retrieval and integrity checks.
- Do not introduce cascading deletion of files, jobs, or audit history without a
  retention policy. Authentication expiry cleanup does not delete classifier results.
- `trx_app` has no superuser, create-database, create-role, or schema-creation
  rights. Grant only needed access to `private`; activity history is insert/read
  only for that role. Keep migrations on the administrative connection.

## Target folder structure

```text
agent-trx-classifier/
  Dockerfile
  .dockerignore
  compose.yaml
  alembic.ini
  pyproject.toml
  uv.lock
  .env.example
  migrations/
    env.py
    versions/0001_initial_schema.py
  src/
    config.py
    api/                         existing FastAPI code; add health/readiness
    tools/event_stream.py        progress events; entry points execute graphs directly
    workflows/trx_classifier/    preserve existing TRX models
    tools/                       preserve provider adapters
    db/
      base.py
      engine.py
      session.py
      listener.py
      models/
        users.py
        categories.py            categories + report buckets
        accounts.py
        statements.py
        transactions.py
        files.py
        jobs.py                  batches + jobs + attempts + metrics
        events.py
        checkpoints.py
        outbox.py
        activity_events.py
        authentication.py
      repositories/
        users.py
        categories.py
        accounts.py
        files.py
        jobs.py
        results.py
        transactions.py          edit + activity insert in one transaction
        events.py
        checkpoints.py
        outbox.py
        authentication.py
  tests/db/
    test_smoke.py
    _shared.py                   only if a helper is actually reused
  docs/database-and-docker/
    README.md
```

Repositories own persistence operations; existing workflow models own the output
contract. Keep blocking database work off the async event loop. Reuse backend
SQLAlchemy/psycopg/Alembic patterns where suitable without building generic
repository frameworks. Integrate pool startup/shutdown with FastAPI lifecycle.

## Docker and implementation steps

1. Read applicable `AGENTS.md` files and inspect the existing backend patterns.
2. Add configuration, dependencies, SQLAlchemy models, and Alembic migrations.
   Provision local `trx_dev`, `trx_test`, and restricted role using local Docker
   initialization. Do not assume local PostgreSQL has Supabase Auth tables.
3. Implement the repository operations described above, including atomic result
   persistence, guarded attempts, owner checks, and simple activity history.
4. Implement a dedicated session-capable `LISTEN job_updates` connection with
   reconnect/catch-up support. No periodic progress queries. Later SSE wiring
   must register subscribers before replay and deduplicate deliveries.
5. Add one Dockerfile using the project's supported Python version (currently
   Python >=3.12) and locked `uv.lock` dependencies. Verify Docling's Linux
   dependencies. Run as a non-root user, bind `0.0.0.0:$PORT`, default port 8080,
   and start one Uvicorn worker. Do not bake secrets into the image.
6. Add `.dockerignore` for `.env` files, `.venv`, Git, caches, and local inputs.
   Compose starts local PostgreSQL and the app, with a persistent development
   volume and a separate test database. Use the same Dockerfile for production;
   provide environment-specific configuration at runtime.
7. Add `GET /health` for application liveness and `GET /ready` for a bounded
   `SELECT 1` check. Return small responses and sanitized failures. Health checks
   must not call AI providers or process PDFs.
8. Run local migrations separately from server startup. Build, start, and verify
   through CLI. No automatic migration on every application instance startup.
9. Update this document and relevant deployment references with the actual
   working commands. Existing cloud-service documents remain later deployment
   guides, not authorization to deploy during this stage.

## Simple verification

Use just `tests/db/test_smoke.py` with tiny synthetic records:

1. Connect and execute `SELECT 1`.
2. Save a job/result and retrieve it through the repository.
3. Confirm another user cannot retrieve that job.
4. Edit a transaction and verify old/new values in activity history.

No AI calls, real PDFs, Cloud Tasks setup, large fixtures, or broad test framework.
Use `_shared.py` only for genuinely reused tiny helpers. Test against `trx_test`,
apply its migrations first, and clean up test data. Never write test fixtures to
production. Database constraints and atomic repository design remain required
even though the requested test suite is small.

Intended CLI flow (make these commands work during implementation):

```bash
docker compose build
docker compose up -d db
docker compose run --rm app alembic upgrade head
docker compose up -d app
curl --fail http://localhost:8080/health
curl --fail http://localhost:8080/ready
docker compose logs --tail=50 app
```

The migration command must select the administrative connection; normal startup
must select the restricted application connection. Document one command to run
the four smoke tests against `trx_test`. Keep test tooling outside the production
runtime where practical. Follow repository formatting/lint instructions.

Expected results: image builds, migrations succeed, both health checks return
200, and the four simple smoke tests pass.

## Production boundary and completion report

Prepare the schema and image for production, but do not deploy Cloud Run, push
images, or alter production schemas as part of local verification. Document the
separate administrative migration command for Supabase. Production migration
execution and deployment are follow-up actions after local work is reviewed.

Finish by listing changed files, created migrations, CLI checks and results,
and remaining integration work. Do not present prepared production configuration
as a completed production deployment.
