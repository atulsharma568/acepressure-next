-- Optional schema-only bootstrap with psql. The Python importer bootstraps its
-- staging schema itself. This file is safe to replay on the baseline schema.
\set ON_ERROR_STOP on
BEGIN;
CREATE SCHEMA IF NOT EXISTS acepressure_shadow;
SET LOCAL search_path TO acepressure_shadow, pg_catalog;
\ir 001_shadow_schema.sql
COMMIT;
