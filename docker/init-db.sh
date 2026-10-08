#!/bin/sh
set -eu
# Docker's initializer passes these values safely as psql variables.
psql --username "$POSTGRES_USER" --dbname postgres --set=app_password="$TRX_APP_PASSWORD" <<'SQL'
CREATE ROLE trx_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE DATABASE trx_dev;
CREATE DATABASE trx_test;
REVOKE ALL ON DATABASE trx_dev, trx_test FROM PUBLIC;
GRANT CONNECT ON DATABASE trx_dev, trx_test TO trx_app;
SQL
for database in trx_dev trx_test; do
  psql --username "$POSTGRES_USER" --dbname "$database" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER ROLE trx_app SET statement_timeout = '5s';
ALTER ROLE trx_app SET lock_timeout = '3s';
SQL
done
