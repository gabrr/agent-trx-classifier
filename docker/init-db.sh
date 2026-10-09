#!/bin/sh
set -eu
psql --username "$POSTGRES_USER" --dbname postgres <<'SQL'
CREATE DATABASE trx_test;
REVOKE ALL ON DATABASE postgres, trx_test FROM PUBLIC;
SQL
for database in postgres trx_test; do
  psql --username "$POSTGRES_USER" --dbname "$database" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
done
