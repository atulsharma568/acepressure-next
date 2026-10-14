# PostgreSQL shadow migration

AcePressure 1.6.7 still runs on its local SQLite WAL database. The PostgreSQL
files and importer here are an **opt-in shadow migration and verification step**;
they do not change Flask, routes, payment matching, OBS, templates, or static
assets. A production cutover is a separate, reviewed project after this shadow
copy has been checked against the live SQLite backup.

## What is included

- `acepressure/migrations/postgresql/001_shadow_schema.sql` is a replay-safe
  PostgreSQL 14+ baseline for SQLite migrations `001`–`009`, plus the lazily
  created `tts_health` table. It keeps paise, timestamps, counters, and identity
  values as integer types; uses booleans, identity columns, foreign keys,
  status/channel checks, partial indexes, and queue/reporting indexes; and keeps
  existing JSON-shaped settings, alert payloads, inbox candidates, and audit
  details as validated JSONB values; non-JSON text columns remain text.
- `scripts/migrate_sqlite_to_postgres.py` reads a consistent read-only SQLite snapshot,
  validates the schema and SQLite integrity, calculates per-table SHA-256
  checksums without displaying row values, and imports in resumable table
  checkpoints. Each checkpoint is counted and checksummed before its transaction
  commits. Publication rechecks every table and identity high-water mark before
  renaming the completed staging schema to `acepressure_shadow`.
- `requirements-postgres.txt` is optional. The normal Flask requirements do not
  install or import a PostgreSQL driver.

The importer also accepts an interrupted checkpoint with `--resume`. It will
not silently mix a different SQLite backup or schema contract into that
checkpoint. A non-empty `acepressure_shadow` schema is refused; the explicit
`--replace-target` flag is required and archives the previous schema under a
generated `acepressure_previous_*` name before publishing the new snapshot.

## Prerequisites

1. Stop/pause writes to AcePressure and create or choose a consistent SQLite
   backup. Do not point this at a database that is receiving payment activity.
2. Create a dedicated PostgreSQL database and role with permission to create
   the two shadow schemas. Do not put the password in a command argument.
3. Install the optional driver in a separate environment if needed:

   ```powershell
   python -m pip install -r requirements-postgres.txt
   ```

4. Set `ACEPRESSURE_POSTGRES_DSN` in the process environment or use a libpq
   service entry. The script never prints the DSN, credentials, row data,
   references, hashes, messages, settings, or payment payloads.

## Safe workflow

Validate the SQLite source without connecting to PostgreSQL:

```powershell
python scripts/migrate_sqlite_to_postgres.py --source "D:\backups\acepressure.sqlite3"
```

Import and publish a new shadow snapshot:

```powershell
python scripts/migrate_sqlite_to_postgres.py --source "D:\backups\acepressure.sqlite3" --apply
```

If a run stops after one or more committed table checkpoints, use the same
source backup and resume:

```powershell
python scripts/migrate_sqlite_to_postgres.py --source "D:\backups\acepressure.sqlite3" --apply --resume
```

Use `--restart-staging` only when deliberately abandoning the matching staged
copy. To replace an already populated shadow target, add
`--replace-target`; the previous target is retained for review and rollback.
After publication, run the read-only verification command and inspect ledger
totals, recent references, statuses, supporter links, alerts, and audit rows
using a protected PostgreSQL client:

```powershell
python scripts/migrate_sqlite_to_postgres.py --source "D:\backups\acepressure.sqlite3" --verify-only
```

The application continues to use `acepressure.sqlite3` after every command.
Changing `DATABASE_URL`, wiring PostgreSQL into Flask, or switching payment
verification is intentionally outside this migration slice and must wait for a
separately verified cutover and rollback plan.
