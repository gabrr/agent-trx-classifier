# Database and Docker

Docker Compose runs PostgreSQL, the FastAPI backend, a separate migration command and an isolated test service. Application tables live in `private`. The backend and migrations use the `postgres` role.

The schema is defined by [Alembic migrations](../../migrations/versions/) and [database models](../../src/db/models/). [HANDOFF.md](HANDOFF.md) and [IMPLEMENTATION.md](IMPLEMENTATION.md) are historical records, not current setup instructions.

## Local CLI

Run from `apps/agent-trx-classifier` with Docker Desktop available. Create `.env` from [`.env.example`](../../.env.example) and fill in the required service settings. Compose reads `.env` automatically and forwards provider settings, including LangSmith, to the backend. It sets the database URLs to its local `db` container; direct Python runs use the URL in `.env`. Local PostgreSQL credentials and ports are fixed in [Compose](../../compose.yaml).

```sh
docker compose build app
docker compose up -d db
docker compose run --rm migrate
docker compose up -d app
curl --noproxy '*' --fail http://127.0.0.1:8080/health
curl --noproxy '*' --fail http://127.0.0.1:8080/ready
docker compose logs --tail=50 app
```

Use `docker compose --env-file .env.prod` to select another settings file. This still runs the local Docker stack. [Production deployment](../deployment/README.md) describes the hosted services.

Local PostgreSQL uses `postgres` as both username and password by default and uses the `postgres` database for the application. Initialization creates a separate `trx_test` database on an empty volume. Initialization does not rerun on an existing volume; changing passwords then requires an administrative role change. PostgreSQL binds to loopback on port 5432. `docker compose down` preserves the development volume.

The backend runs one non-root Uvicorn process on `0.0.0.0:$PORT`, default 8080. Dependencies are locked; Linux PyTorch uses CPU wheels. Provider initialization is deferred, so health startup does not require AI credentials. Actual login, uploads and dispatch require their provider configuration.

`/health` checks liveness. `/ready` runs a bounded `SELECT 1`; it does not verify schema revision, providers or model downloads.

Run the complete test suite against the isolated test database:

```sh
docker compose run --build --rm test
```

The test service migrates `trx_test` and runs `tests/`. Provider substitutes avoid live AI/cloud calls. Test dependencies are in a separate image target. Test configuration refuses production database targets; use only synthetic records.

For Python-only development, run `uv sync --locked`, set `DATABASE_URL` from [`.env.example`](../../.env.example), and use `uv run trx-api`. Run `uv run alembic upgrade head` using the same `DATABASE_URL`. Server startup never runs migrations.

## Configuration and Supabase boundary

| Setting | Responsibility |
| --- | --- |
| `DATABASE_URL` | Connection for queries, event listening and migrations. |

The [configuration code](../../src/config.py) reads `DATABASE_URL` with its password included. URL-encode special characters in the password. Environment interpolation is disabled when loading `.env`. Malformed URLs are rejected without exposing credentials.

Use a direct or session-pooler address for `DATABASE_URL`. The listener opens a separate connection using that same URL. The [query engine](../../src/db/engine.py) disables named prepared statements and bounds pool/connect waits. Use TLS with appropriate certificate verification for hosted connections.

For the existing Acetate deployment, use Supabase project `agent-trx-classifier`, database `postgres`. Keep `private` outside the Data API's exposed schemas. [Supabase setup](../deployment/supabase.md) owns role and connection instructions.

Apply the hosted migration using a securely supplied `DATABASE_URL`:

```sh
# Enable Auth linkage only when application tables and Supabase Auth share a project.
PGOPTIONS='-c trx.auth_same_project=true' uv run alembic upgrade head
```

With the option, `private.users.id` references the existing `auth.users` ID. Omit it for a database without that dependency. Local PostgreSQL does not create Supabase schemas. Migrations do not create a production database or Supabase Auth users. Plan backups and compatibility before applying a migration.

## Persistence guarantees

- User repository operations scope access to verified owner IDs. Composite foreign keys prevent cross-owner associations.
- Job creation commits the outbox and queued event together. Claims and outcome writes lock the job and reject stale attempts.
- Successful completion commits the statement, ordered transactions, metrics, original result, terminal status and event together.
- Event sequence allocation and notification happen under the job lock. One session-capable listener per process catches up subscribers from durable history.
- Checkpoints record input/workflow/model/schema compatibility. The processing wrapper reuses only matching stage state.
- Transaction edits validate ownership, preserve original AI fields and append changed-field activity in the same transaction. Repository support does not imply an exposed HTTP editing endpoint.
- Repositories preserve immutable history. The `postgres` role can administer the schema and modify data directly. Migration downgrade refuses destructive deletion without an explicit retention design.

Create/use/close synchronous database sessions inside worker threads when called from async handlers. For writes, use a transaction context. [Repositories](../../src/db/repositories/) define the operations; [job integration](../authentication-and-jobs.md) shows their callers.

Automatic file/history deletion is not configured. Define retention, backup/restore and operational monitoring for the hosted environment. [Deployment](../deployment/README.md) lists setup and launch checks.

Migration `0002` removes the obsolete backend session and login-attempt tables created by the initial migration. It refuses removal if either table contains data. Supabase-managed `auth` tables remain unchanged.
