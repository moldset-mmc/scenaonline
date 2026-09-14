import io
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
    import libsql
    import vercel
except ImportError:
    raise unittest.SkipTest('Install requirements-cloud.txt for cloud acceptance tests.')

from PIL import Image
from scena_database import connect, snapshot_to_file
from scena_cloud_auth import make_session, valid_session, safe_next


class DatabaseAdapterTests(unittest.TestCase):
    def test_transactions_rows_constraints_and_portable_snapshot(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SCENA_DB_DRIVER': 'libsql'}):
            database = Path(folder) / 'source.db'
            connection = connect(database)
            connection.row_factory = sqlite3.Row
            connection.execute('CREATE TABLE items(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE)')
            with connection:
                connection.execute('INSERT INTO items(name) VALUES (?)', ('kept',))
            with self.assertRaises(sqlite3.IntegrityError), connection:
                connection.execute('INSERT INTO items(name) VALUES (?)', ('rolled-back',))
                connection.execute('INSERT INTO items(name) VALUES (?)', ('kept',))
            rows = connection.execute('SELECT * FROM items').fetchall()
            self.assertEqual(dict(rows[0]), {'id': 1, 'name': 'kept'})
            self.assertEqual(rows[0]['NAME'], 'kept')
            self.assertEqual(len(rows), 1)
            connection.close()
            target = Path(folder) / 'backup.db'
            snapshot_to_file(database, target)
            with sqlite3.connect(target) as restored:
                self.assertEqual(restored.execute('SELECT name FROM items').fetchall(), [('kept',)])
                self.assertEqual(restored.execute('PRAGMA integrity_check').fetchone()[0], 'ok')


class CookieTests(unittest.TestCase):
    def test_expiry_tampering_password_rotation_and_return_url(self):
        with patch.dict(os.environ, {'SCENA_SESSION_SIGNING_KEY': 'ab'*32, 'SCENA_ADMIN_PASSWORD': 'fixture-secret'}):
            token = make_session(now=100)
            self.assertTrue(valid_session(token, now=101))
            self.assertFalse(valid_session(token, now=50000))
            self.assertFalse(valid_session(token + 'a', now=101))
            os.environ['SCENA_ADMIN_PASSWORD'] = 'rotated-fixture-secret'
            self.assertFalse(valid_session(token, now=101))
            self.assertEqual(safe_next('/?page=admin'), '/?page=admin')
            self.assertTrue(safe_next('//untrusted.example').startswith('/?page=admin'))


class CloudInitializationTests(unittest.TestCase):
    def test_publication_reads_keep_legacy_conversion_without_schema_writes(self):
        from scena_cloud_runtime import initialize_application, _ready
        from scena_core import add_post
        from scena_publications import list_publications
        import scena_database
        with tempfile.TemporaryDirectory() as folder:
            database = str(Path(folder) / 'cloud.db')
            environment = {'SCENA_CLOUD': '1', 'SCENA_DB_PATH': database,
                           'SCENA_TURSO_TURSO_DATABASE_URL': database,
                           'SCENA_TURSO_TURSO_AUTH_TOKEN': 'fixture'}
            with patch.dict(os.environ, environment):
                initialize_application(database)
                # Legacy writes still acquire their publication metadata on read.
                post = add_post(database, title_ru='Тест', title_ro='Test',
                                body_ru='Текст', body_ro='Text')
                statements = []
                original = scena_database._call
                def record(function, *args, **kwargs):
                    if function.__name__ == 'execute':
                        statements.append(args[0].strip().upper())
                    return original(function, *args, **kwargs)
                with patch.object(scena_database, '_call', record):
                    records = list_publications(database)
                self.assertEqual([item['post_id'] for item in records], [post])
                self.assertFalse(any(sql.startswith(('CREATE ', 'ALTER ')) for sql in statements))
                _ready.discard(database)


class DurableMediaTests(unittest.TestCase):
    def test_private_original_public_rendition_and_cache_recovery(self):
        from scena_media import initialize, persist, hydrate
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / 'manifest.db'
            media = root / 'media'
            media.mkdir()
            image = media / 'portrait.png'
            Image.new('RGB', (640, 800), '#aabbcc').save(image)
            original = image.read_bytes()
            objects = {}
            def put(path, content, **options):
                url = 'https://' + options['access'] + '.example/' + path
                objects[url] = content
                return SimpleNamespace(url=url)
            def get(url, **options):
                self.assertEqual(options['access'], 'private')
                return SimpleNamespace(content=objects[url], status_code=200)
            with patch.dict(os.environ, {'SCENA_DB_PATH': str(database), 'SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN': 'fixture-private', 'SCENA_PUBLIC_BLOB_READ_WRITE_TOKEN': 'fixture-public'}), patch('scena_media.cloud_database', return_value=True), patch('vercel.blob.put', side_effect=put), patch('vercel.blob.get', side_effect=get):
                initialize()
                persist(image, root)
                self.assertEqual(len(objects), 1)
                self.assertTrue(next(iter(objects)).startswith('https://private.'))
                persist(image, root, public=True)
                self.assertEqual(len(objects), 2)
                image.unlink()
                hydrate(root, force=True)
                self.assertEqual(image.read_bytes(), original)
                failed = media / 'failed.png'
                failed.write_bytes(original)
                with patch('vercel.blob.put', side_effect=OSError('fixture upload failure')):
                    with self.assertRaises(OSError):
                        persist(failed, root)
                with sqlite3.connect(database) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM scena_media_files').fetchone()[0], 1)

    def test_cloud_restore_replaces_data_only_after_backup_validation(self):
        from scena_core import init_db, get_settings, save_settings
        from scena_transfer import build_backup, TransferValidationError
        from scena_cloud_restore import restore_cloud
        from scena_media import initialize
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            source.mkdir()
            (source / 'media').mkdir()
            image = source / 'media/photo.png'
            Image.new('RGB', (640, 800), '#335577').save(image)
            source_db = source / 'source.db'
            init_db(source_db)
            save_settings(source_db, {'master_name': 'Restored fixture'})
            backup = build_backup(source_db, source / 'media')
            live = root / 'live'
            live.mkdir()
            (live / 'media').mkdir()
            target = live / 'live.db'
            init_db(target)
            save_settings(target, {'master_name': 'Current fixture'})
            objects = {}
            def put(path, content, **options):
                url = 'https://private.example/' + path
                objects[url] = content
                return SimpleNamespace(url=url)
            def get(url, **options):
                return SimpleNamespace(content=objects[url], status_code=200)
            settings = {'SCENA_CLOUD': '1', 'SCENA_DB_PATH': str(target), 'SCENA_TURSO_TURSO_DATABASE_URL': str(target), 'SCENA_TURSO_TURSO_AUTH_TOKEN': 'fixture', 'SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN': 'fixture-private'}
            with patch.dict(os.environ, settings), patch('vercel.blob.put', side_effect=put), patch('vercel.blob.get', side_effect=get):
                initialize()
                with self.assertRaises(TransferValidationError):
                    restore_cloud(b'broken archive', target, live)
                self.assertEqual(get_settings(target)['master_name'], 'Current fixture')
                restore_cloud(backup, target, live)
                self.assertEqual(get_settings(target)['master_name'], 'Restored fixture')
                self.assertEqual((live / 'media/photo.png').read_bytes(), image.read_bytes())
