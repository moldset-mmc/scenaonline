"""Isolated regression tests: no live database, network, credentials or clients."""
import concurrent.futures
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scena_web.domain_migration import migrate_public_origin, NEW_ORIGIN, MIGRATION_KEY

PRODUCTION = {"VERCEL": "1", "VERCEL_ENV": "production"}


@contextmanager
def _test_database(path):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class DomainMigrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.database = str(Path(self.folder.name) / "test.db")
        with _test_database(self.database) as db:
            db.executescript("""
                CREATE TABLE profile_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE cache_revision (version INTEGER NOT NULL);
                INSERT INTO cache_revision VALUES (0);
                CREATE TRIGGER invalidate AFTER UPDATE ON profile_settings BEGIN
                    UPDATE cache_revision SET version=version+1;
                END;
            """)
            db.executemany("INSERT INTO profile_settings VALUES (?,?)", [
                ("public_base_url", "https://scenaonline.vercel.app"),
                ("model_indexed", "0"), ("profile_published", "1"),
                ("seo_google_verification", "preserve-existing-verification"),
                ("bio", "Preserve the owner's published text"),
            ])

    def read(self, sql, params=()):
        with _test_database(self.database) as db:
            return db.execute(sql, params).fetchall()

    def set_origin(self, value):
        with _test_database(self.database) as db:
            db.execute("UPDATE profile_settings SET value=? WHERE key='public_base_url'", (value,))

    def run_migration(self, environment=None):
        return migrate_public_origin(self.database, PRODUCTION if environment is None else environment,
                                     connector=sqlite3.connect)

    def test_migrates_and_preserves_unrelated_settings(self):
        before = dict(self.read("SELECT key,value FROM profile_settings"))
        self.assertEqual(self.run_migration(), "migrated")
        after = dict(self.read("SELECT key,value FROM profile_settings"))
        before["public_base_url"] = NEW_ORIGIN
        self.assertEqual(before, after)
        self.assertEqual(self.read("SELECT version FROM cache_revision"), [(1,)])
        receipt = json.loads(self.read("SELECT value FROM app_meta WHERE key=?", (MIGRATION_KEY,))[0][0])
        self.assertEqual(receipt, {"from": "https://scenaonline.vercel.app", "to": NEW_ORIGIN, "changed": True})

    def test_trailing_slash_old_origin(self):
        self.set_origin("https://scenaonline.vercel.app/")
        self.assertEqual(self.run_migration(), "migrated")

    def test_existing_new_origin(self):
        self.set_origin(NEW_ORIGIN)
        self.assertEqual(self.run_migration(), "already_current")

    def test_idempotency_and_later_owner_choice(self):
        self.run_migration()
        self.set_origin("https://another.example")
        self.assertEqual(self.run_migration(), "already_recorded")
        self.assertEqual(dict(self.read("SELECT key,value FROM profile_settings"))["public_base_url"], "https://another.example")

    def test_preview_and_local_are_read_only(self):
        for environment in ({}, {"VERCEL": "1", "VERCEL_ENV": "preview"},
                            {"VERCEL": "1", "VERCEL_ENV": "development"}, {"VERCEL_ENV": "production"}):
            with self.subTest(environment=environment):
                self.assertEqual(self.run_migration(environment), "skipped_environment")
        self.assertEqual(self.read("SELECT version FROM cache_revision"), [(0,)])
        self.assertEqual(self.read("SELECT * FROM app_meta"), [])

    def test_unexpected_or_missing_origin_is_not_overwritten(self):
        for value in ("https://another.example", "http://localhost:8501", "", "https://scenaonline.vercel.app/other"):
            self.set_origin(value)
            self.assertEqual(self.run_migration(), "skipped_unexpected_origin")
            self.assertEqual(dict(self.read("SELECT key,value FROM profile_settings"))["public_base_url"], value)
        with _test_database(self.database) as db:
            db.execute("DELETE FROM profile_settings WHERE key='public_base_url'")
        self.assertEqual(self.run_migration(), "skipped_unexpected_origin")
        self.assertEqual(self.read("SELECT * FROM app_meta"), [])

    def test_receipt_failure_rolls_back_setting_and_cache(self):
        with _test_database(self.database) as db:
            db.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON app_meta BEGIN SELECT RAISE(ABORT,'test rollback'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.run_migration()
        self.assertEqual(dict(self.read("SELECT key,value FROM profile_settings"))["public_base_url"], "https://scenaonline.vercel.app")
        self.assertEqual(self.read("SELECT version FROM cache_revision"), [(0,)])

    def test_concurrent_replicas_migrate_once(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.run_migration(), range(8)))
        self.assertEqual(results.count("migrated"), 1)
        self.assertEqual(results.count("already_recorded"), 7)
        self.assertEqual(self.read("SELECT version FROM cache_revision"), [(1,)])

    def test_platform_configuration_preserves_existing_setting(self):
        config = json.loads((Path(__file__).resolve().parents[1] / "vercel.json").read_text())
        self.assertEqual(config["git"]["deploymentEnabled"]["checkpoint/scena-hosting-2026-09-14"], False)
        self.assertNotIn("redirects", config)



if __name__ == "__main__":
    unittest.main()
