"""Dependency-free checks for the opt-in PostgreSQL shadow slice."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts import migrate_sqlite_to_postgres as migration


ROOT = Path(__file__).resolve().parents[1]


def sqlite_migrations(path):
    db = sqlite3.connect(path)
    try:
        for sql_file in sorted((ROOT / 'acepressure' / 'migrations').glob('*.sql')):
            db.executescript(sql_file.read_text(encoding='utf-8'))
        db.commit()
    finally:
        db.close()


class PostgresMigrationContractTests(unittest.TestCase):
    def test_all_sqlite_migrations_form_the_expected_source_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.sqlite3'
            sqlite_migrations(path)
            with migration.source_snapshot(path) as db:
                names = migration.source_tables(db)
                manifest = migration.source_manifest(db, names, 2)
            self.assertEqual(names, {table.name for table in migration.TABLES if not table.optional})
            self.assertEqual(manifest['tips']['count'], 0)
            self.assertEqual(manifest['alerts']['next_id'], 1)

    def test_row_checksum_is_ordered_and_normalizes_sqlite_booleans(self):
        table = next(table for table in migration.TABLES if table.name == 'supporters')
        first = ('s1', 'h1', None, 'A', 0, 1)
        second = ('s2', 'h2', None, 'B', 1, 0)
        digest = migration.digest_rows(table, [first, second])
        reversed_digest = migration.digest_rows(table, [second, first])
        self.assertEqual(digest['count'], 2)
        self.assertNotEqual(digest['sha256'], reversed_digest['sha256'])
        self.assertEqual(migration.normalize(table, first)[4:], (False, True))

    def test_json_columns_are_canonicalized_for_postgres_jsonb(self):
        table = next(table for table in migration.TABLES if table.name == 'alerts')
        row = (7, None, '{"display_paise": 12345, "tts": true}', 10, 20)
        normalized = migration.normalize(table, row)
        self.assertEqual(normalized[2], {'display_paise': 12345, 'tts': True})
        self.assertEqual(migration.target_values(table, normalized)[2],
                         '{"display_paise":12345,"tts":true}')

    def test_ledger_amounts_are_read_as_integer_paise_without_conversion(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.sqlite3'
            sqlite_migrations(path)
            db = sqlite3.connect(path)
            try:
                db.execute("INSERT INTO supporters VALUES ('s1','h1',NULL,'A',0,0)")
                db.execute("INSERT INTO tips(id,token,supporter_id,name,display_paise,requested_paise,actual_paise,message,created,expires,status,tts,voice,sound) "
                           "VALUES ('t1','tok','s1','A',12345,12346,12344,'ok',1,2,'VERIFIED',0,'en-IN','chime')")
                db.commit()
            finally:
                db.close()
            with migration.source_snapshot(path) as source:
                names = migration.source_tables(source)
                tips = list(migration.source_rows(source, next(table for table in migration.TABLES if table.name == 'tips'), names, 10))
            self.assertEqual(tips[0][4:7], (12345, 12346, 12344))

    def test_source_only_mode_is_opt_in_and_does_not_echo_private_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.sqlite3'
            sqlite_migrations(path)
            stdout, stderr = StringIO(), StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = migration.main(['--source', str(path)])
            self.assertEqual(result, 0)
            self.assertIn('Use --apply to opt in', stdout.getvalue())
            self.assertNotIn('source.sqlite3', stdout.getvalue())
            self.assertEqual(stderr.getvalue(), '')

    def test_apply_safety_flags_require_explicit_apply(self):
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                migration.parse_args(['--source', 'backup.sqlite3', '--replace-target'])

    def test_postgres_contract_is_separate_from_sqlite_runner(self):
        ddl = migration.DDL.read_text(encoding='utf-8')
        self.assertIn('CREATE TABLE IF NOT EXISTS tips', ddl)
        self.assertIn('display_paise BIGINT', ddl)
        self.assertIn('requested_paise BIGINT', ddl)
        self.assertIn('payload JSONB', ddl)
        self.assertIn('detail JSONB', ddl)
        self.assertIn('CREATE INDEX IF NOT EXISTS tips_match', ddl)
        self.assertIn('CREATE UNIQUE INDEX IF NOT EXISTS one_active_session', ddl)
        self.assertNotIn('PRAGMA ', ddl)


if __name__ == '__main__':
    unittest.main()
