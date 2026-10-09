# Supabase PostgreSQL

PostgreSQL stores application ownership, jobs, results, user profiles, ordered events and recovery state. Supabase Auth manages provider identities separately. Complete [local database setup](../database-and-docker/README.md) before applying a production migration.

## Schema and migration

For the existing Acetate environment, use the `agent-trx-classifier` project and its `postgres` database. Confirm the target project before running administrative commands.

Application tables live in `private`, which must be excluded from Supabase's exposed Data API schemas. Supabase-managed schemas remain owned by Supabase. [Alembic migrations](../../migrations/versions/) define the application schema; Supabase CLI `db push` is not this application's migration mechanism.

Use the [production migration procedure](../database-and-docker/README.md#configuration-and-supabase-boundary). It explains the optional same-project `auth.users` foreign key. Runtime startup does not run migrations. Migration `0002` removes obsolete backend authentication tables only when they are empty; Supabase-managed authentication tables are unchanged.

## Database access

The backend and migrations use the `postgres` role. Use one `DATABASE_URL`, including the password, for the backend and migration commands.

The role has administrative database access. FastAPI repositories enforce verified ownership on user queries and preserve application history; direct SQL connections do not inherit a browser user's RLS identity.

## Connections and secrets

Use Supabase’s session-pooler connection for `DATABASE_URL`, or a direct connection when reachable. Queries and the notification listener use this same URL. The listener keeps its own connection open.

For the session pooler, use the dashboard's connection host/port/database with username `postgres.PROJECT_REF` and the database password. URL-encode credentials and configure TLS certificate verification supported by the driver. [Connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres)

Publish the database URL with the [secret helper](README.md#secrets-and-configuration):

```sh
publish_trx_secret DATABASE_URL trx-database-url
```

Each process has one dedicated listener plus the query pool configured in [engine.py](../../src/db/engine.py). Budget connections across maximum instances, revision overlap, administrative work and other applications. An instance cap is not a hard database connection cap.

[Events and live updates](../trx-system-design/02-events-and-live-updates.md) explains event ordering, transaction notifications and replay.

## Backup and recovery

Install PostgreSQL client tools. Configure administrative connections using restrictive libpq service/password files outside Git. Keep dumps encrypted and outside the repository.

```sh
pg_dump --dbname=service=trx_admin --schema=private --format=custom --no-owner \
  --file=/YOUR_PRIVATE_BACKUP_DIRECTORY/trx-private.dump
pg_restore --list /YOUR_PRIVATE_BACKUP_DIRECTORY/trx-private.dump
```

Back up before migrations and select a regular schedule based on acceptable data loss. Test restoration into an isolated database with compatible schema dependencies:

```sh
pg_restore --no-owner --no-privileges --dbname=service=trx_restore BACKUP_FILE
```

Reconcile unfinished jobs before resuming dispatch. When Auth foreign keys are enabled, the restore target must also supply the corresponding Auth users/dependencies.

A `private` schema dump is not a complete Supabase backup. Auth users/configuration and Storage objects need separate recovery coverage. Test these together; do not assume the selected hosting plan provides them.

## Verify

- Confirm authenticated requests cannot access another user's records.
- Commit an event and notification; receive it from another connection.
- Restart the listener and verify missed-event replay.
- Verify TLS, connection limits and the plan's storage/egress/availability constraints.
- Restore a backup and reconcile jobs and identity dependencies before serving traffic.

[Roles](https://supabase.com/docs/guides/database/postgres/roles), [hosting plans](https://supabase.com/pricing), [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html), [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html).
