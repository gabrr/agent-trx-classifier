# Database and Docker

Implemented locally in TRX: 17 `private` tables, migration `0001`, owner-scoped
repositories, fenced job attempts, atomic result persistence, durable events and
a reconnecting LISTEN connection, activity history, authentication persistence,
Docker packaging, and health/readiness. The original agreed plan is preserved in
[HANDOFF.md](HANDOFF.md). Production migration and deployment have not been run.

## Local CLI

Run from `apps/agent-trx-classifier`, with Docker Desktop running. Use the explicit
Compose environment file to avoid interpolating the existing legacy `.env`.
The example file contains only local development credentials. For classification,
set provider keys in your shell; neither checks nor migrations call providers.
Local custom passwords must use URL-safe characters (letters, digits, `-`, `_`).

```sh
docker compose --env-file .env.compose.example build app
docker compose --env-file .env.compose.example up -d db
docker compose --env-file .env.compose.example run --rm migrate
docker compose --env-file .env.compose.example up -d app
curl --noproxy '*' --fail http://127.0.0.1:8080/health
curl --noproxy '*' --fail http://127.0.0.1:8080/ready
docker compose --env-file .env.compose.example logs --tail=50 app
```

The migration service uses the same runtime image. It receives only
`DATABASE_ADMIN_URL`; the app receives only the restricted `DATABASE_URL` and
`DATABASE_LISTENER_URL`. Consequently the planned `run app alembic upgrade head`
command is replaced with `run migrate`. Server startup never runs migrations.
Linux dependencies use CPU PyTorch via [uv’s documented index configuration](https://docs.astral.sh/uv/guides/integration/pytorch/), avoiding CUDA libraries.
One non-root Uvicorn worker binds `0.0.0.0:$PORT` (default 8080). Provider creation
is deferred until classification, so application checks need no AI keys.
`/health` reports liveness; `/ready` returns 200 after a bounded `SELECT 1`, or a
sanitized 503. It does not check providers, model downloads, or schema revision.

PostgreSQL listens only on loopback port 5433 by default. Initialization creates
`trx_dev`, `trx_test`, and `trx_app`; the development volume persists across
restarts. Init scripts run only on an empty volume. Changing local passwords on
an existing volume requires an explicit administrative role change. `down` keeps
the volume. No automatic file, job, result, or history deletion is configured.

Run the four tiny smoke tests and their migrations with one command:

```sh
docker compose --env-file .env.compose.example run --build --rm test
```

The test image is a separate Dockerfile target; pytest/dev dependencies are absent
from the runtime target. Tests refuse databases other than local `trx_test` and
clean up only their synthetic records, using the administrative test connection.
No PDFs, AI calls, queue calls, or production fixtures are used.

For Python-only development, `uv sync --locked` installs the dependencies. Set
runtime/listener URLs from `.env.example`, then `uv run trx-api`. For migrations,
set `DATABASE_ADMIN_URL` explicitly and run `uv run alembic upgrade head`.
Never use the administrator URL as the runtime URL.

## Configuration and Supabase boundary

Runtime configuration is `DATABASE_URL`, `DATABASE_ADMIN_URL` (migration commands
only), and `DATABASE_LISTENER_URL`. Legacy `DB_URL` is accepted only for a runtime
connection using `trx_app` (or Supabase's `trx_app.PROJECT_REF` username).
`DB_PASSWORD` supplies an absent URL password, or resolves literal `${DB_PASSWORD}`,
`$DB_PASSWORD`, `${PASSWORD}`, and `$PASSWORD` placeholders with proper URL
encoding. `.env` interpolation is disabled in Python. Unresolved legacy passwords,
administrative runtime users, and malformed URLs fail with sanitized messages.
Do not copy the current legacy administrative URL to the running application's
configuration. Migration commands deliberately have no legacy/runtime fallback.

Use a session-capable direct connection or Supabase session pooler for LISTEN;
a transaction pooler cannot preserve LISTEN state. The SQLAlchemy runtime disables
psycopg named prepared statements and bounds pool/connect waits. Supabase pooler
URLs can be supplied at runtime; credentials must be percent-encoded.

Reuse the existing Supabase project `acetate-agentic`, database `postgres`.
Prepare its restricted login `trx_app` separately through an administrative
connection with `NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT`, a separately managed
password, and CONNECT permission. The migration requires the role to exist; it
grants schema USAGE and the required table privileges. It neither creates a
production database nor modifies Supabase-managed schemas. Configure `private`
outside the exposed Data API schemas in the project settings before deployment.

After local review, the separate production command is:

```sh
# Supply the existing administrator URL securely in DATABASE_ADMIN_URL.
# Set this option ONLY if Supabase Auth uses the same existing project.
PGOPTIONS='-c trx.auth_same_project=true' uv run alembic upgrade head
```

Without that explicit option the migration does not reference `auth.users`.
With it, `private.users.id` also references the existing verified Auth user ID.
Local PostgreSQL never creates fake Supabase schemas. PDFs remain private GCS
references; Supabase Storage is unused. No production command was executed here.

## Repository usage and guarantees

Use `with session_factory(engine).begin() as session:` for every write operation.
Call synchronous repositories with `asyncio.to_thread` from async handlers, and
create/use/close the session inside that thread. Owner IDs and profile data must
come from verified authentication; request bodies are not a source of identity.
Repositories return ORM records; load the data needed before closing the session.

- `users`, `categories`, `accounts`, and `files` create/read the optional associations.
- `jobs.create_job` stores its outbox intent and queued event atomically and handles
  submission idempotency. Manual retry creates a fresh job/key linked to a terminal
  job. `claim_job`, `renew_claim`, and `guard_attempt` fence stale writers. Claims
  can be renewed for at most 1800 seconds and never beyond a job deadline.
- `results.complete_job` revalidates with the existing TRX model and persists the
  statement, ordered transactions, metrics, original result JSON, terminal event,
  and attempt/job completion in one transaction. Repeating successful completion
  for that attempt returns the existing statement. AI fields and money strings
  are preserved; later edits never modify `jobs.result`.
- `events.append_progress` retains `step_started`/`step_completed`. Completion and
  failure retain `result`/`error`. Job row locks protect sequence allocation.
  `NOTIFY job_updates` carries only the job UUID and commits with the event.
- `JobUpdateListener` has a dedicated connection, registers subscriptions before
  replay, deduplicates by sequence, and catches up subscribed jobs after reconnect.
  It queries progress on notifications/reconnect/subscription, never on a timer.
  Callbacks run on its database thread; future async SSE consumers must use
  `loop.call_soon_threadsafe` and unsubscribe on disconnect. An exception in a
  callback leaves its cursor unchanged and causes reconnect/catch-up.
- `checkpoints` requires saved output or a private storage reference and exact
  input/workflow/model/schema compatibility. Retry reuse also requires the same
  retained source file. `recover_enqueue` creates idempotent recovery intents for
  expired claims or queued jobs and fails exhausted/deadline jobs safely.
  The later scheduler/dispatcher must call it; no Cloud Tasks worker is added.
- `outbox` locks pending intents and records dispatch success or bounded exponential
  retry delays. The caller supplies sanitized errors; dispatch integration is later.
- `transactions.edit_transaction` validates fields/ownership, locks the row, reads
  the actual old values, and appends one activity row per changed effective value.
  Bucket overrides preserve the original AI classification. Activity is read/insert
  only for `trx_app`; there is no undo or deletion infrastructure.
- `authentication` stores only caller-hashed identifiers and caller-encrypted bytes
  with a key version. Login consume requires the hashed browser binding and is
  single-use under a row lock. Encryption, verified login, refresh, and cleanup
  services remain future integration work.

Composite foreign keys enforce owner consistency for files, batches, jobs,
retries, statements, accounts, and transactions. Attempt references must belong
to their job. Category triggers allow only shared system or same-owner categories;
category ownership is immutable. Probability shape/range/sum is also constrained
in PostgreSQL. The runtime role cannot create schemas/tables, delete records, or
update activity, events, checkpoints, original statements, or run metrics.
Administrative migration downgrade refuses destructive deletion until a retention
policy exists.

## Verification and remaining work

Local verification covers migration execution and all four smoke tests on
PostgreSQL 17, plus tiny checks for expired-attempt fencing, checkpoint compatibility,
LISTEN/replay sequence deduplication, and restricted role permissions. See the
[implementation report](IMPLEMENTATION.md) for container build and endpoint check results.

Future work: verified authentication and encryption services; GCS transport and
30,000,000-byte batch upload validation; durable job API/worker wiring; SSE wiring;
provider retry handling; an outbox dispatcher and recovery scheduler; Cloud Tasks,
production migration approval, image publication, Cloud Run deployment, and monitoring.
The current `/classify` flow and its existing per-file limit remain available.
