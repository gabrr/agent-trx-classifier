# Implementation report — October 8, 2026

> Historical verification report for the database/Docker stage on October 8, 2026. Its remaining-work list describes that stage, not current capabilities. Use [Database and Docker](README.md) and [job integration](../authentication-and-jobs.md) for current guidance.

The agreed local database/Docker scope is implemented in `apps/agent-trx-classifier`.
Production schemas were not changed. No images were pushed, and no cloud services
were deployed. Existing TRX workflow models, `classify()`, `events()`, nullable
extracted fields, monetary strings, and probability validation remain intact.

## Migration and behavior

`migrations/versions/0001_initial_schema.py` creates all 17 application tables,
indexes, constraints, report bucket seeds, category ownership guards, and role
grants in `private`. Its SQL is frozen independently of future ORM changes.
Alembic's version table also lives in `private`. Local initialization creates only
`trx_dev`, `trx_test`, and restricted `trx_app`. Supabase Auth linkage is opt-in
for the same-project administrative migration; local PostgreSQL has no fake Auth
schemas. The migration refuses destructive downgrade.

Repository operations atomically persist job/outbox creation, attempts/progress,
results, and transaction edits with activity history. Composite ownership links,
job-row locks, active-attempt/expiry fencing, and idempotent completion prevent
cross-owner associations, racing sequences, and stale completion writes.

## CLI checks and results

The full command sequence is in [README.md](README.md). Results on local Docker
PostgreSQL 17 and Linux ARM64/Python 3.12:

| Check | Result |
| --- | --- |
| `docker compose --env-file .env.compose.example build app` | Passed; final runtime image approximately 1.75 GB, with locked CPU PyTorch dependencies. |
| `docker compose --env-file .env.compose.example up -d db` | Passed; local database healthy. |
| `docker compose --env-file .env.compose.example run --rm migrate` | Passed; administrator-only migration service uses the runtime image. |
| `docker compose --env-file .env.compose.example up -d app` | Passed; one non-root worker, app healthy. |
| `curl --noproxy '*' --fail http://127.0.0.1:8080/health` | HTTP 200, `{"status":"ok"}`. |
| `curl --noproxy '*' --fail http://127.0.0.1:8080/ready` | HTTP 200, `{"status":"ready"}`. |
| `docker compose --env-file .env.compose.example logs --tail=20 app` | Clean startup and successful health/readiness requests. |
| `docker compose --env-file .env.compose.example run --build --rm test` | Four smoke tests passed. Repeated on a fresh task-owned local test schema: migration and all four tests passed in the container (0.87 seconds). |
| `uvx ruff check .` | Passed. |
| `uvx ruff format --check .` | Passed; 95 Python files formatted. |
| `git diff --check` | Passed. |

Additional tiny local checks passed: lease expiry/reclaim fencing, exact checkpoint
compatibility, durable LISTEN notification/replay, catch-up after terminating the
test listener connection, sequence deduplication, and denied audit updates, event
deletion, and runtime DDL. Container inspection confirmed a nonzero user ID, CPU
Torch, successful Docling imports, no pytest in the runtime, and no administrative
URL in its environment. No providers were called or PDFs processed.

Docker's credential helper initially stalled public pulls; verification used an
empty temporary Docker config pointing at the existing CLI plugins and local
daemon. An HTTP Debian cache hash mismatch was resolved by using HTTPS, matching
the normalizer pattern. The initial CUDA lock exceeded available Docker disk
space; Linux dependencies now select CPU wheels following
[uv's PyTorch guide](https://docs.astral.sh/uv/guides/integration/pytorch/). Only
obsolete images/cache records created by this task were removed. The temporary
native PostgreSQL verification instance under `/tmp` was stopped. Final Compose
app/database containers remain running with the development volume retained.

## Changed files

Existing user changes to `docs/index.md`, untracked deployment documents, and
`.DS_Store` were preserved. The prior database handoff README was retained as
`HANDOFF.md`. No parent-repository files were changed. Implementation files:

- `.dockerignore`
- `.env.example`
- `.env.compose.example`
- `Dockerfile`
- `compose.yaml`
- `alembic.ini`
- `pyproject.toml`
- `uv.lock`
- `src/config.py`
- `src/api/app.py`
- `src/api/main.py`
- `README.md`
- `docs/deployment/README.md`
- `docs/deployment/supabase.md`
- `docs/deployment/cloud-run.md`
- `docs/database-and-docker/README.md`
- `docs/database-and-docker/HANDOFF.md`
- `docs/database-and-docker/IMPLEMENTATION.md`
- `docker/init-db.sh`
- `migrations/env.py`
- `migrations/versions/0001_initial_schema.py`
- `src/db/__init__.py`
- `src/db/base.py`
- `src/db/engine.py`
- `src/db/listener.py`
- `src/db/models/__init__.py`
- `src/db/models/accounts.py`
- `src/db/models/activity_events.py`
- `src/db/models/authentication.py`
- `src/db/models/categories.py`
- `src/db/models/checkpoints.py`
- `src/db/models/events.py`
- `src/db/models/files.py`
- `src/db/models/jobs.py`
- `src/db/models/outbox.py`
- `src/db/models/statements.py`
- `src/db/models/transactions.py`
- `src/db/models/users.py`
- `src/db/repositories/__init__.py`
- `src/db/repositories/accounts.py`
- `src/db/repositories/authentication.py`
- `src/db/repositories/categories.py`
- `src/db/repositories/checkpoints.py`
- `src/db/repositories/events.py`
- `src/db/repositories/files.py`
- `src/db/repositories/jobs.py`
- `src/db/repositories/outbox.py`
- `src/db/repositories/results.py`
- `src/db/repositories/transactions.py`
- `src/db/repositories/users.py`
- `src/db/session.py`
- `tests/db/test_smoke.py`

## Remaining integration work

Verified authentication/encryption and login/refresh services; GCS upload transport
and batch limits; durable job API/worker integration; SSE subscribers; bounded
provider retries; recovery scheduling/outbox dispatch; Cloud Tasks; production
role provision and administrative migration after review; image publication and
Cloud Run deployment; model artifact caching/sizing and monitoring. Production
readiness must also verify that `private` is excluded from the Data API and the
listener uses a session-capable connection.

At this stage, classification still ran through a direct HTTP endpoint. The current
API submits jobs through `/api/jobs`; use the [API contract](../trx-classifier-contract.md#http-api).
