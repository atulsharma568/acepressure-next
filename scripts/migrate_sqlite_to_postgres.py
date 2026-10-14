"""Opt-in, resumable SQLite -> PostgreSQL shadow snapshot; no Flask imports.

Default: validate a read-only SQLite snapshot only. --apply writes verified
table checkpoints to acepressure_import, then atomically publishes that schema
as acepressure_shadow. Existing targets require --replace-target and are kept
under a generated previous-schema name. Credentials are environment-only.
"""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
DDL = ROOT / 'acepressure' / 'migrations' / 'postgresql' / '001_shadow_schema.sql'
TARGET = 'acepressure_shadow'
STAGE = 'acepressure_import'
DSN_ENV = 'ACEPRESSURE_POSTGRES_DSN'
FORMAT = 1
MAX_INT = (1 << 63) - 1
BASELINE = 'AcePressure 1.6.7 shadow baseline; SQLite 001-009'
PG_TYPES = {'t': 'text', 'j': 'jsonb', 'i': 'int8', 'b': 'bool', 's': 'int2', 'n': 'int4'}


class MigrationError(Exception):
    """Only fixed, non-sensitive diagnostics may be passed to this exception."""


@dataclass(frozen=True)
class Column:
    name: str
    kind: str
    nullable: bool


@dataclass(frozen=True)
class Table:
    name: str
    spec: str
    key: tuple
    identity: bool = False
    optional: bool = False

    @property
    def columns(self):
        return tuple(Column(name, kind.rstrip('?'), kind.endswith('?'))
                     for name, kind in (part.split(':') for part in self.spec.split()))


# Dependency order. Column order matches SQLite 001-009, including ALTERs.
TABLES = (
    Table('settings', 'key:t value:j', ('key',)),
    Table('supporters', 'id:t identity_hash:t email:t? name:t blocked:b muted:b', ('id',)),
    Table('sessions', 'id:t title:t started:i ended:i?', ('id',)),
    Table('soundboards', 'id:t name:t emoji:t media_filename:t? category:t min_paise:i '
          'display_order:i enabled:b duration_ms:i? created:i volume:s', ('id',)),
    Table('tips', 'id:t token:t supporter_id:t name:t display_paise:i requested_paise:i '
          'actual_paise:i? message:t created:i expires:i verified:i? session_id:t? '
          'reference:t? status:t tts:b voice:t sound:t alert_shown:b? tts_played:b? '
          'verification_source:t? note:t? soundboard_id:t?', ('id',)),
    Table('receipts', 'reference:t amount:i received:i ingested:i outcome:t tip_id:t?', ('reference',)),
    Table('amount_leases', 'amount:i until:i', ('amount',)),
    Table('goals', 'id:t title:t target:i starting:i period:t reset:t starts:i? ends:i? '
          'enabled:b design:t style:t session_id:t?', ('id',)),
    Table('alerts', 'id:i tip_id:t? payload:j created:i expires:i', ('id',), identity=True),
    Table('deliveries', 'alert_id:i channel:t state:t owner:t? lease:i?', ('alert_id', 'channel')),
    Table('audit', 'id:i at:i actor:t action:t object_id:t? detail:j', ('id',), identity=True),
    Table('rate_limits', 'bucket:t count:i until:i', ('bucket',)),
    Table('schema_version', 'version:i', ('version',)),
    Table('paytm_captures', 'id:i fingerprint:t captured_at:i amount_paise:i? outcome:t repeats:i',
          ('id',), identity=True),
    Table('paytm_events', 'fingerprint:t ingested:i amount_paise:i? outcome:t tip_id:t? repeats:i',
          ('fingerprint',)),
    Table('paytm_bridge', 'id:i token_hash:t enabled:b auto_match:b recipient_hash:t last_seen:i?', ('id',)),
    Table('paytm_inbox', 'id:i fingerprint:t received:i payment_minute:i? amount:i? status:t '
          'reason:t tip_id:t? candidates:j repeats:i', ('id',), identity=True),
    Table('supporter_aliases', 'source_id:t target_id:t', ('source_id',)),
    Table('browser_supporters', 'token_hash:t supporter_id:t expires:i', ('token_hash',)),
    Table('tts_health', 'id:i code:t? at:i?', ('id',), optional=True),
)
META = Table('_postgres_migrations', 'version:n name:t', ('version',))
RUN = Table('_import_run', 'id:n source_sha256:t schema_sha256:t state:t', ('id',))
CHECKPOINTS = Table('_import_tables', 'table_name:t row_count:i sha256:t', ('table_name',))


def quote(name):
    # All names come from the allowlisted contract or generated UUIDs, never data.
    if not re.fullmatch(r'[a-z_][a-z0-9_]*', name):
        raise MigrationError('Invalid internal SQL identifier.')
    return '"' + name + '"'


def relation(schema, table):
    return quote(schema) + '.' + quote(table)


def selected_columns(table):
    return ', '.join(quote(c.name) for c in table.columns)


def reject_json_constant(_value):
    raise ValueError('non-standard JSON constant')


def ordered_key(table, postgres=False):
    kinds = {c.name: c.kind for c in table.columns}
    return ', '.join(quote(k) + (' COLLATE "C"' if postgres else ' COLLATE BINARY')
                     if kinds[k] == 't' else quote(k) for k in table.key)


def normalize(table, row):
    """No lossy int()/str() casts, money conversion or rounding.

    SQLite stores JSON-shaped values as text. PostgreSQL stores those four
    fields as JSONB, so JSON is parsed and canonicalized for the checksum while
    the original logical value (including integer paise inside a payload) is
    preserved.
    """
    result = []
    if len(row) != len(table.columns):
        raise MigrationError(f'Unexpected column count in {table.name}.')
    for column, value in zip(table.columns, row):
        valid = False
        if column.kind == 'j':
            if isinstance(value, str):
                try:
                    value = json.loads(value, parse_constant=reject_json_constant)
                except (TypeError, ValueError, json.JSONDecodeError):
                    value = None
                    valid = False
                else:
                    valid = True
            elif value is None:
                # A PostgreSQL JSONB null is returned by psycopg as Python None;
                # source JSON null is never a SQL NULL because the column is NOT NULL.
                valid = True
            else:
                try:
                    json.dumps(value, ensure_ascii=False, allow_nan=False)
                except (TypeError, ValueError):
                    valid = False
                else:
                    valid = True
        elif value is None:
            valid = column.nullable
        elif column.kind == 't':
            valid = isinstance(value, str) and '\x00' not in value
            if valid:
                try:
                    value.encode('utf-8')
                except UnicodeError:
                    valid = False
        elif column.kind == 'b':
            valid = type(value) in (int, bool) and value in (0, 1)
            if valid:
                value = bool(value)
        else:
            bits = {'i': 64, 's': 16, 'n': 32}[column.kind]
            valid = type(value) is int and -(1 << (bits - 1)) <= value < (1 << (bits - 1))
        if not valid:
            raise MigrationError(f'Unsupported value in {table.name}.{column.name}; value suppressed.')
        result.append(value)
    return tuple(result)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


def target_values(table, row):
    """Adapt canonical JSON values without exposing them to logs."""
    return tuple(json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True,
                            allow_nan=False) if column.kind == 'j' else value
                 for column, value in zip(table.columns, row))


def digest_rows(table, rows):
    digest = hashlib.sha256(encoded([FORMAT, table.name, table.spec]))
    count = 0
    for row in rows:
        data = encoded(normalize(table, row))
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
        count += 1
    return {'count': count, 'sha256': digest.hexdigest()}


@contextmanager
def source_snapshot(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise MigrationError('The SQLite source must be an existing file.')
    # mode=ro includes committed WAL data. immutable=1 would incorrectly ignore
    # a live WAL. One read transaction pins the snapshot for all passes.
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, isolation_level=None, timeout=20)
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        db.execute('SELECT name FROM sqlite_schema LIMIT 1').fetchone()
        yield db
    finally:
        db.rollback()
        db.close()


def source_tables(db):
    objects = db.execute("SELECT name, type FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' "
                         "AND type IN ('table','view','trigger')").fetchall()
    names = {name for name, kind in objects if kind == 'table'}
    if any(kind != 'table' for _, kind in objects) or names - {t.name for t in TABLES}:
        raise MigrationError('Unsupported source tables, views or triggers; no data was imported.')
    if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
        raise MigrationError('SQLite integrity check failed; details suppressed.')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise MigrationError('SQLite foreign-key check failed; details suppressed.')
    for table in TABLES:
        if table.name not in names:
            if table.optional:
                continue
            raise MigrationError(f'Missing source table {table.name}; use a 1.6.7 backup.')
        info = db.execute(f'PRAGMA table_info({quote(table.name)})').fetchall()
        expected = [(c.name, 'TEXT' if c.kind in ('t', 'j') else 'INTEGER') for c in table.columns]
        actual = [(r[1], r[2].upper()) for r in info]
        keys = tuple(r[1] for r in sorted(info, key=lambda r: r[5]) if r[5])
        if actual != expected or keys != table.key:
            raise MigrationError(f'Unsupported source schema in {table.name}; use SQLite migrations 001-009.')
    return names


def source_rows(db, table, names, batch_size):
    if table.name not in names:
        return
    cursor = db.execute(f'SELECT {selected_columns(table)} FROM {quote(table.name)} '
                        f'ORDER BY {ordered_key(table)}')
    try:
        while rows := cursor.fetchmany(batch_size):
            for row in rows:
                yield normalize(table, row)
    finally:
        cursor.close()


def source_manifest(db, names, batch_size):
    sequences = dict(db.execute('SELECT name, seq FROM sqlite_sequence'))
    if set(sequences) - {t.name for t in TABLES if t.identity}:
        raise MigrationError('Unsupported SQLite identity sequence.')
    manifest = {}
    for table in TABLES:
        entry = digest_rows(table, source_rows(db, table, names, batch_size))
        entry['present'] = table.name in names
        if table.identity:
            high = db.execute(f'SELECT MAX(id) FROM {quote(table.name)}').fetchone()[0]
            sequence = sequences.get(table.name, 0)
            if type(sequence) is not int or sequence < 0:
                raise MigrationError(f'Invalid identity high-water mark in {table.name}.')
            next_id = max(0, high or 0, sequence) + 1
            if next_id > MAX_INT:
                raise MigrationError(f'Identity range exhausted in {table.name}.')
            entry['next_id'] = next_id
        manifest[table.name] = entry
    return manifest


def schema_exists(pg, schema):
    return pg.execute('SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname=%s)',
                      (schema,)).fetchone()[0]


def inspect_schema(pg, schema):
    """Reject unknown objects, column drift, user triggers and incomplete layouts."""
    objects = pg.execute('SELECT c.relname,c.relkind FROM pg_catalog.pg_class c '
                         'JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace '
                         "WHERE n.nspname=%s AND c.relkind NOT IN ('i','I','t')", (schema,)).fetchall()
    if not objects:
        return ()
    tables = {name for name, kind in objects if kind == 'r'}
    base = {t.name for t in TABLES} | {META.name}
    controls = {RUN.name, CHECKPOINTS.name}
    sequences = {t.name + '_id_seq' for t in TABLES if t.identity}
    if tables not in (base, base | controls) or set(objects) != (
            {(name, 'r') for name in tables} | {(name, 'S') for name in sequences}):
        raise MigrationError('Unexpected PostgreSQL schema objects; refusing to modify this schema.')
    specs = TABLES + (META,) + ((RUN, CHECKPOINTS) if controls <= tables else ())
    for table in specs:
        columns = pg.execute('SELECT a.attname,t.typname,a.attnotnull,a.attidentity '
                             'FROM pg_catalog.pg_attribute a '
                             'JOIN pg_catalog.pg_type t ON t.oid=a.atttypid '
                             'JOIN pg_catalog.pg_class c ON c.oid=a.attrelid '
                             'JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace '
                             'WHERE n.nspname=%s AND c.relname=%s AND a.attnum>0 '
                             'AND NOT a.attisdropped ORDER BY a.attnum', (schema, table.name)).fetchall()
        expected = [(c.name, PG_TYPES[c.kind], not c.nullable,
                     'd' if table.identity and c.name == 'id' else '') for c in table.columns]
        if columns != expected:
            raise MigrationError(f'PostgreSQL schema drift in {table.name}.')
    triggers = pg.execute('SELECT 1 FROM pg_catalog.pg_trigger t '
                          'JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid '
                          'JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace '
                          'WHERE n.nspname=%s AND NOT t.tgisinternal LIMIT 1', (schema,)).fetchone()
    if triggers:
        raise MigrationError('Unexpected PostgreSQL triggers; refusing to modify this schema.')
    if pg.execute(f'SELECT version,name FROM {relation(schema, META.name)}').fetchall() != [(1, BASELINE)]:
        raise MigrationError('Unrecognized PostgreSQL baseline version.')
    return specs


def lock_tables(pg, schema, specs, mode='SHARE'):
    if specs:
        tables = ', '.join(relation(schema, t.name) for t in specs)
        pg.execute(f'LOCK TABLE {tables} IN {mode} MODE')


def target_guard(pg, replace_target, exclusive=False):
    if not schema_exists(pg, TARGET):
        return False
    specs = inspect_schema(pg, TARGET)
    lock_tables(pg, TARGET, specs, 'ACCESS EXCLUSIVE' if exclusive else 'SHARE')
    nonempty = bool(specs) and any(pg.execute(
        f'SELECT EXISTS(SELECT 1 FROM {relation(TARGET, t.name)})').fetchone()[0] for t in TABLES)
    if nonempty and not replace_target:
        raise MigrationError('Target is non-empty; use --replace-target to explicitly replace this shadow snapshot.')
    return True


def archive_schema(pg, schema, prefix):
    archived = prefix + uuid.uuid4().hex
    pg.execute(f'ALTER SCHEMA {quote(schema)} RENAME TO {quote(archived)}')
    return archived


def create_stage(pg, ddl, source_hash, schema_hash):
    pg.execute(f'CREATE SCHEMA {quote(STAGE)}')
    pg.execute(f'SET LOCAL search_path TO {quote(STAGE)}, pg_catalog')
    # No parameters: psycopg uses the simple-query protocol for the SQL file.
    pg.execute(ddl)
    pg.execute(f'CREATE TABLE {relation(STAGE, RUN.name)} ('
               'id INTEGER PRIMARY KEY CHECK(id=1), source_sha256 TEXT NOT NULL, '
               "schema_sha256 TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('copying','complete')))")
    pg.execute(f'CREATE TABLE {relation(STAGE, CHECKPOINTS.name)} ('
               'table_name TEXT PRIMARY KEY, row_count BIGINT NOT NULL CHECK(row_count>=0), sha256 TEXT NOT NULL)')
    pg.execute(f'INSERT INTO {relation(STAGE, RUN.name)} VALUES (1,%s,%s,\'copying\')',
               (source_hash, schema_hash))
    inspect_schema(pg, STAGE)


def prepare_stage(pg, ddl, source_hash, schema_hash, resume=False, restart=False):
    with pg.transaction():
        if schema_exists(pg, STAGE):
            specs = inspect_schema(pg, STAGE)
            if RUN not in specs:
                raise MigrationError('Staging schema is not a recognized resumable import.')
            lock_tables(pg, STAGE, specs, 'ACCESS EXCLUSIVE')
            if restart:
                archive_schema(pg, STAGE, 'acepressure_abandoned_')
            elif resume:
                run = pg.execute(f'SELECT source_sha256,schema_sha256,state FROM {relation(STAGE, RUN.name)} '
                                 'WHERE id=1').fetchone()
                if run != (source_hash, schema_hash, 'copying'):
                    raise MigrationError('Source or migration contract changed; use the original backup or --restart-staging.')
                return
            else:
                raise MigrationError('An import checkpoint exists; use --resume or --restart-staging.')
        create_stage(pg, ddl, source_hash, schema_hash)


def postgres_digest(pg, schema, table, batch_size):
    with pg.cursor(name='acepressure_check_' + uuid.uuid4().hex) as cursor:
        cursor.execute(f'SELECT {selected_columns(table)} FROM {relation(schema, table.name)} '
                       f'ORDER BY {ordered_key(table, postgres=True)}')

        def rows():
            while batch := cursor.fetchmany(batch_size):
                yield from batch

        return digest_rows(table, rows())


def check_digest(table, actual, expected):
    if actual != {key: expected[key] for key in ('count', 'sha256')}:
        raise MigrationError(f'Row-count/checksum mismatch in {table.name}; publication refused.')


def copy_tables(pg, db, names, manifest, batch_size):
    for table in TABLES:
        with pg.transaction():
            lock_tables(pg, STAGE, (table, CHECKPOINTS), 'ACCESS EXCLUSIVE')
            checkpoint = pg.execute(f'SELECT row_count,sha256 FROM {relation(STAGE, CHECKPOINTS.name)} '
                                    'WHERE table_name=%s', (table.name,)).fetchone()
            expected = manifest[table.name]
            if checkpoint:
                check_digest(table, dict(zip(('count', 'sha256'), checkpoint)), expected)
            else:
                if pg.execute(f'SELECT EXISTS(SELECT 1 FROM {relation(STAGE, table.name)})').fetchone()[0]:
                    raise MigrationError(f'Uncheckpointed data in staging table {table.name}; refusing to overwrite.')
                rows = source_rows(db, table, names, batch_size)
                insert = (f'INSERT INTO {relation(STAGE, table.name)} ({selected_columns(table)}) VALUES ('
                          + ','.join('%s::jsonb' if column.kind == 'j' else '%s'
                                     for column in table.columns) + ')')
                with pg.cursor() as cursor:
                    while batch := list(islice(rows, batch_size)):
                        cursor.executemany(insert, (target_values(table, row) for row in batch))
            # A checkpoint is trusted only after re-reading the stored rows.
            check_digest(table, postgres_digest(pg, STAGE, table, batch_size), expected)
            if not checkpoint:
                pg.execute(f'INSERT INTO {relation(STAGE, CHECKPOINTS.name)} VALUES (%s,%s,%s)',
                           (table.name, expected['count'], expected['sha256']))
        print(f'{table.name}: {expected["count"]} rows checkpointed and verified.')


def verify_all(pg, schema, manifest, batch_size, sequences=True):
    for table in TABLES:
        check_digest(table, postgres_digest(pg, schema, table, batch_size), manifest[table.name])
        if sequences and table.identity:
            state = pg.execute(f'SELECT last_value,is_called FROM '
                               f'{relation(schema, table.name + "_id_seq")}').fetchone()
            if state != (manifest[table.name]['next_id'], False):
                raise MigrationError(f'Identity high-water mismatch in {table.name}.')


def verify_target(pg, manifest, batch_size):
    with pg.transaction():
        specs = inspect_schema(pg, TARGET)
        if not specs:
            raise MigrationError('The shadow target does not contain the PostgreSQL baseline.')
        lock_tables(pg, TARGET, specs)
        verify_all(pg, TARGET, manifest, batch_size)


def publish(pg, manifest, batch_size, replace_target):
    archived = None
    with pg.transaction():
        specs = inspect_schema(pg, STAGE)
        lock_tables(pg, STAGE, specs, 'ACCESS EXCLUSIVE')
        exists = target_guard(pg, replace_target, exclusive=True)
        # ALTER ... RESTART is transactional; setval() is not. Preserve deleted
        # AUTOINCREMENT high-water marks, not merely MAX(id) of surviving rows.
        for table in TABLES:
            if table.identity:
                pg.execute(f'ALTER TABLE {relation(STAGE, table.name)} ALTER COLUMN id '
                           f'RESTART WITH {manifest[table.name]["next_id"]}')
        verify_all(pg, STAGE, manifest, batch_size)
        pg.execute(f"UPDATE {relation(STAGE, RUN.name)} SET state='complete' WHERE id=1")
        if exists:
            archived = archive_schema(pg, TARGET, 'acepressure_previous_')
        pg.execute(f'ALTER SCHEMA {quote(STAGE)} RENAME TO {quote(TARGET)}')
    return archived


def completed_resume(pg, source_hash, schema_hash, manifest, batch_size):
    """Resolve an interrupted client's ambiguous COMMIT without re-importing."""
    with pg.transaction():
        if schema_exists(pg, STAGE) or not schema_exists(pg, TARGET):
            return False
        specs = inspect_schema(pg, TARGET)
        if RUN not in specs:
            return False
        lock_tables(pg, TARGET, specs)
        run = pg.execute(f'SELECT source_sha256,schema_sha256,state FROM {relation(TARGET, RUN.name)} '
                         'WHERE id=1').fetchone()
        if run != (source_hash, schema_hash, 'complete'):
            return False
        verify_all(pg, TARGET, manifest, batch_size)
        return True


@contextmanager
def postgres_connection():
    dsn = os.environ.get(DSN_ENV, '')
    if not dsn:
        raise MigrationError(f'Set {DSN_ENV} privately, or use a libpq service in that variable.')
    try:
        import psycopg
    except ImportError:
        raise MigrationError('PostgreSQL tooling is optional; requirements-postgres.txt is not installed.') from None
    with psycopg.connect(dsn, autocommit=True, connect_timeout=10,
                         application_name='acepressure-shadow-migration', client_encoding='utf8') as pg:
        if pg.info.server_version < 140000:
            raise MigrationError('The shadow migration requires PostgreSQL 14 or later.')
        pg.execute("SET lock_timeout='5s'")
        if not pg.execute('SELECT pg_catalog.pg_try_advisory_lock(1094927696,167)').fetchone()[0]:
            raise MigrationError('Another AcePressure shadow migration holds the database lock.')
        # This session-level lock is released on disconnect, including crashes.
        yield pg


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse ordinarily echoes unknown CLI values, possibly a pasted DSN.
        self.print_usage(sys.stderr)
        self.exit(2, 'Invalid arguments; use --help. Pass credentials through the environment only.\n')


def parse_args(argv):
    parser = PrivateParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Existing SQLite 1.6.7 database or consistent backup')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='Opt in to copying and publishing a shadow snapshot')
    mode.add_argument('--verify-only', action='store_true', help='Compare source with the committed shadow, without writes')
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument('--resume', action='store_true', help='Verify and reuse completed table checkpoints')
    recovery.add_argument('--restart-staging', action='store_true', help='Archive an abandoned import and start a new snapshot')
    parser.add_argument('--replace-target', '--allow-nonempty-target', dest='replace_target', action='store_true',
                        help='Allow non-empty shadow replacement; archive previous schema')
    parser.add_argument('--batch-size', type=int, default=500, help='Rows fetched/inserted per batch (1-10000)')
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 10000 or ((args.resume or args.restart_staging or args.replace_target) and not args.apply):
        parser.error('invalid option combination')
    return args


def run(args):
    with source_snapshot(args.source) as db:
        names = source_tables(db)
        manifest = source_manifest(db, names, args.batch_size)
        for table in TABLES:
            print(f'{table.name}: {manifest[table.name]["count"]} source rows validated.')
        if not (args.apply or args.verify_only):
            print('Source validation passed. Use --apply to opt in to a PostgreSQL shadow import.')
            return
        ddl = DDL.read_text(encoding='utf-8')
        source_hash = hashlib.sha256(encoded(manifest)).hexdigest()
        schema_hash = hashlib.sha256(encoded([FORMAT, ddl, [t.spec for t in TABLES]])).hexdigest()
        with postgres_connection() as pg:
            if args.verify_only:
                verify_target(pg, manifest, args.batch_size)
                print('Shadow row counts, checksums and identity high-water marks match the SQLite snapshot.')
                return
            if args.resume and completed_resume(pg, source_hash, schema_hash, manifest, args.batch_size):
                print('Previously committed shadow snapshot verified; no rows recopied.')
                return
            with pg.transaction():
                target_guard(pg, args.replace_target)
            prepare_stage(pg, ddl, source_hash, schema_hash, args.resume, args.restart_staging)
            copy_tables(pg, db, names, manifest, args.batch_size)
            archived = publish(pg, manifest, args.batch_size, args.replace_target)
            print('Verified shadow snapshot committed to acepressure_shadow. Flask still uses SQLite.')
            if archived:
                print(f'Previous target retained in schema {archived}.')


def main(argv=None):
    args = parse_args(argv)
    try:
        run(args)
        return 0
    except MigrationError as error:
        print(f'Migration refused: {error}', file=sys.stderr)
    except KeyboardInterrupt:
        print('Interrupted. Re-run with --apply --resume and the same source to inspect progress.', file=sys.stderr)
    except Exception as error:
        # Driver exceptions can contain passwords, SQL parameters, failed-row
        # details, token hashes and payment payloads. Never print/re-raise them.
        code = getattr(error, 'sqlstate', None)
        suffix = f' (SQLSTATE {code})' if isinstance(code, str) and re.fullmatch(r'[0-9A-Z]{5}', code) else ''
        print('Migration failed' + suffix + '; details suppressed to protect private data. '
              'Uncommitted work rolls back. Use --resume with the same source to verify progress.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
