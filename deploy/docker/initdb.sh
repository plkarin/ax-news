#!/bin/sh
# The database of a new install (README, Installation), on the first start
# of the db container. 002 belongs to features removed before v1.0.0.
set -e
for m in 001_schema 003_personal_sources 004_catalog_tv 005_articles_lookups; do
  psql -v ON_ERROR_STOP=1 -q --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "/migrations/$m.sql"
done
