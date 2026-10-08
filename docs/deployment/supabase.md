# Supabase PostgreSQL

Start on **Free**. Stores batches, jobs, results, and durable ordered events.
Setup: **CLI** for project/migrations; **dashboard** for signup and connection details.

## Existing project and migration

Reuse the existing `acetate-agentic` project and its `postgres` database. Do not
create another project/database for TRX. The administrative connection was checked
on October 8, 2026. Local implementation now uses Alembic migration `0001`;
see [database and Docker](../database-and-docker/README.md) for verified local
commands and the separate production migration command. Supabase CLI `db push`
is not the migration mechanism for this application. Production migration and
deployment remain follow-up work after review.

## Schema and connections

Put application tables in a `private` schema excluded from Supabase's exposed
Data API schemas. Supabase Auth manages its own users; do not recreate its tables.

| Table | Stores |
| --- | --- |
| `batches`, `jobs` | Verified owner ID, PDF object reference, status/result, completion/failure time, optional success message, safe error code/reason, diagnostic reference, retry-of job ID, attempt ID, claim expiry, and enqueue state. |
| `events` | Event ID, job ID, per-job sequence, attempt ID, type, timestamp, and output. |
| `outbox` | Transactional enqueue intent, deterministic task name, dispatch state, retry timing, and finalization scheduling. |
| `checkpoints`, `job_attempts` | Stage outputs or private Storage references, input/workflow/model/schema versions, attempt IDs, retry counts, timestamps, and sanitized failure details. |
| `sessions` | Hashed opaque ID, verified user ID, encrypted provider tokens, CSRF token, expiry, revocation, and refresh coordination state. |
| `login_attempts` | Hashed browser-bound attempt ID, encrypted PKCE verifier, expiry, and one-use state. |

Enforce unique `(job_id, sequence)` and indexes for owner/active jobs, session
hashes, and expired claims. Allocate sequences and update job/event state in the
same transaction. Include the outbox and saved-stage recovery tables in the initial
migration. Fence checkpoint/result writes with the current attempt and reject
writes to terminal runs. Preserve failed history when user retry creates a linked
replacement job; enforce idempotent retry submission.
Authentication expiry cleanup is later work. Keep events until a retention policy is agreed.
See [authentication](authentication.md) and [confirmed task decisions](cloud-tasks.md).

### Restricted runtime role

Before the reviewed production migration, run this as the migration owner in a trusted `psql` session.
Use `\password trx_app` there to set a password interactively; never commit it.

```sql
CREATE ROLE trx_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;
GRANT CONNECT ON DATABASE postgres TO trx_app;
```

Use the administrative Alembic command in the [implementation guide](../database-and-docker/README.md)
to create the schema and grant table access. Do not grant DELETE across application
tables, or UPDATE/DELETE/TRUNCATE on activity history. Events, checkpoints, statements,
and run metrics are immutable for the runtime role. Role ownership, DDL, inherited
privileged memberships, and Supabase service schema access are excluded. Verify
that `trx_app` has no CREATE permission through `public` or other inherited grants.
FastAPI repositories scope every query to a verified owner; direct SQL does not
inherit a browser user's RLS identity. Admin credentials stay outside Cloud Run.

### Connections

Use the dashboard's **Connect → Session pooler** details for the listener; it
supports IPv4 and session state. Store this SSL-enabled URI as
`DATABASE_LISTENER_URL`. `DATABASE_URL` can use session pooling initially, or
transaction pooling with a compatible driver. Never use transaction pooling for
`LISTEN`. Prefer a scoped application database role; reserve admin credentials
for migrations. For the session pooler, use the custom role username `trx_app.PROJECT_REF`
and its own password; retain the dashboard host/port/database. URL-encode the
password and require TLS with certificate verification supported by the driver.

Add these two values to local environment/`.env`, then use the [secret helper](README.md):

```sh
publish_trx_secret DATABASE_URL trx-database-url
publish_trx_secret DATABASE_LISTENER_URL trx-listener-url
```

Each backend process holds one dedicated listener connection on `job_updates`.
Append events and notify in one transaction. Listen/register before replay;
catch up on notifications and reconnects, deduplicate delivery, and use SSE
heartbeats without database queries. Use one Uvicorn process per instance,
a query pool capped at two connections, and one dedicated listener: initially
three connections per instance. Four instances means about twelve application
connections, plus deployment overlap/admin connections. Validate this against
the project limit; the Cloud Run instance cap is not a hard DB connection cap.

## Job outcomes and diagnostics

Persist success results and optional messages, or a safe failure code/reason and
diagnostic reference. Keep detailed sanitized attempt records private; user-facing
queries/events expose only safe errors. Conversion checkpoints may reference
private Storage objects to avoid filling the Free database with large text.

Failure finalization must work even if the last worker crashes. User retry creates
a new owned job linked to the original and reuses only compatible checkpoints.
Cross-service log aggregation/viewing is part two; outcome/attempt records are
part of the initial schema. Do not store PDF contents or secrets in diagnostics.

## Backup and recovery

Install PostgreSQL client tools. Configure a local `trx_admin` connection using
libpq service/password files with restrictive permissions; keep those files and
backups outside Git. Use a session-capable connection for admin work.

```sh
pg_dump --dbname=service=trx_admin --schema=private --format=custom --no-owner --file=/YOUR_PRIVATE_BACKUP_DIRECTORY/trx-private.dump
pg_restore --list /YOUR_PRIVATE_BACKUP_DIRECTORY/trx-private.dump
```

Take an encrypted private-schema backup before migrations and daily once live.
Test restoration to an isolated empty database using `pg_restore --no-owner
--no-privileges --dbname=service=trx_restore BACKUP_FILE`, then reapply grants.
Invalidate restored browser sessions and login attempts; reconcile unfinished
jobs before resuming task dispatch. Keep required token-encryption key versions
available securely for legitimate recovery.

This is an application-data backup, not a complete Supabase project backup:
Auth users/configuration and PDF objects need separate recovery coverage. Document
and test identity recovery before launch; keep retained bucket objects private.
Do not assume the Free project supplies a complete restore workflow.


## Verify

Commit a job event and `NOTIFY` from one connection; receive and read it through
another. Restart the listener and replay missed events. Test job ownership.
Free includes 500 MB database storage and 5 GB egress; inactive projects may pause
after a week. Add event retention and monitor usage before considering Pro.

[CLI reference](https://supabase.com/docs/reference/cli/supabase-projects-create)
· [Connections](https://supabase.com/docs/guides/database/connecting-to-postgres)
· [Free plan](https://supabase.com/pricing)

[Database roles](https://supabase.com/docs/guides/database/postgres/roles)
· [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html)
· [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html)
