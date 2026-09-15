"""Idle-expired libSQL streams must not break form snapshots or public cache.

The injected transport expires any interactive transaction after its first
statement. This deterministically reproduces the production failure without
network calls or retries of domain actions.
"""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scena_web import page_cache, storage
from scena_database import connect

IDLE_ERROR = 'SQLite error: interactive transaction was rolled back because the stream was idle for too long; retry the transaction'


class IdleExpiredConnection:
    def __init__(self, path, *, isolation_level=''):
        self.native = sqlite3.connect(path, isolation_level=isolation_level)
        self.statements = []
        self.expired = False
        self.closed = False

    def execute(self, sql, parameters=()):
        self.statements.append(sql)
        if self.expired:
            raise sqlite3.OperationalError(IDLE_ERROR)
        result = self.native.execute(sql, parameters)
        if self.native.in_transaction:
            self.native.rollback()
            self.expired = True
        return result

    def commit(self):
        if self.expired:
            raise sqlite3.OperationalError(IDLE_ERROR)
        self.native.commit()

    def rollback(self):
        if self.expired:
            raise sqlite3.OperationalError('cannot rollback - no transaction is active')
        self.native.rollback()

    def close(self):
        self.closed = True
        self.native.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind:
            self.rollback()
        else:
            self.commit()


class EphemeralAutocommitTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = Path(self.folder.name)/'fixture.db'
        self.environment = patch.dict(os.environ, {
            'SCENA_CLOUD':'0', 'SCENA_DB_DRIVER':'sqlite3', 'SCENA_DB_PATH':str(self.db),
            'SCENA_SESSION_SIGNING_KEY':'fixture-signing-key', 'SCENA_ADMIN_PASSWORD':'fixture-password',
        })
        self.environment.start(); self.addCleanup(self.environment.stop)
        storage.initialize()
        self.connections = []

    def fault_connect(self, path, **kwargs):
        connection = IdleExpiredConnection(path, **kwargs)
        self.connections.append(connection)
        return connection

    def test_injection_reproduces_form_commit_and_second_cache_statement_failures(self):
        with closing(self.fault_connect(self.db)) as connection:
            connection.execute('INSERT INTO scena_web_forms(token,browser_id,payload,expires) VALUES(?,?,?,?)', ('legacy','owner','encrypted',9999999999))
            with self.assertRaisesRegex(sqlite3.OperationalError, 'idle for too long'):
                connection.commit()
        with closing(self.fault_connect(self.db)) as connection:
            connection.execute('DELETE FROM scena_web_pages WHERE expires<=0')
            with self.assertRaisesRegex(sqlite3.OperationalError, 'idle for too long'):
                connection.execute('INSERT INTO scena_web_pages VALUES(?,?,?,?,?)', ('legacy',0,'old','/',9999999999))

    def test_form_insert_is_durable_without_commit_and_retains_single_use(self):
        with patch.object(storage,'connect',self.fault_connect):
            token = storage.save_form('owner',{'selected':42},{'page':'admin'}, {'control':{'kind':'text'}})
        self.assertEqual(len(self.connections),1)
        self.assertEqual(len(self.connections[0].statements),1)
        self.assertFalse(self.connections[0].expired)
        self.assertTrue(self.connections[0].closed)
        with self.assertRaises(ValueError):
            storage.load_form(token,'other-owner',consume=True)
        self.assertEqual(storage.load_form(token,'owner',consume=True)['state'],{'selected':42})
        with self.assertRaises(ValueError):
            storage.load_form(token,'owner',consume=True)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*),SUM(consumed) FROM scena_web_forms').fetchone(),(1,1))

    def test_cache_remains_idempotent_and_revision_guard_survives_expired_streams(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute('INSERT INTO scena_web_pages VALUES(?,?,?,?,?)',('expired',0,'old','/',0))
        with patch.object(page_cache,'connect',self.fault_connect):
            version, value = page_cache.lookup('fixture')
            self.assertIsNone(value)
            page_cache.save('fixture',version,'<p>current</p>','/?lang=en')
            page_cache.save('fixture',version,'<p>current</p>','/?lang=en')
            self.assertEqual(page_cache.lookup('fixture')[1],('<p>current</p>','/?lang=en'))
            with sqlite3.connect(self.db) as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM scena_web_pages').fetchone()[0],1)
                connection.execute('UPDATE scena_web_page_revision SET version=version+1 WHERE id=1')
            page_cache.save('fixture',version,'<p>stale</p>','/')
            self.assertIsNone(page_cache.lookup('fixture')[1])
            page_cache.save('fixture',version+1,'<p>updated</p>','/')
            self.assertEqual(page_cache.lookup('fixture')[1],('<p>updated</p>','/'))
        self.assertTrue(all(connection.closed and not connection.expired for connection in self.connections))

    def test_failed_insert_closes_connection_without_retry_or_creating_a_token(self):
        original = self.fault_connect
        def failing(path, **kwargs):
            connection = original(path,**kwargs)
            connection.expired = True
            return connection
        with patch.object(storage,'connect',failing), self.assertRaisesRegex(sqlite3.OperationalError,'idle for too long'):
            storage.save_form('owner',{}, {}, {})
        self.assertEqual(len(self.connections),1)
        self.assertEqual(len(self.connections[0].statements),1)
        self.assertTrue(self.connections[0].closed)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM scena_web_forms').fetchone()[0],0)

    def test_remote_adapter_honors_isolation_level_and_default_domain_transactions(self):
        try:
            import libsql
        except ImportError:
            self.skipTest('libsql cloud dependency is unavailable')
        # Exercise the real remote adapter path against a local libSQL fixture;
        # no network/database credentials are used.
        with patch.dict(os.environ,{'SCENA_CLOUD':'1','SCENA_TURSO_TURSO_DATABASE_URL':str(self.db),'SCENA_TURSO_TURSO_AUTH_TOKEN':'fixture'}):
            with closing(connect(self.db,isolation_level=None)) as connection:
                connection.execute('INSERT INTO scena_web_forms(token,browser_id,payload,expires) VALUES(?,?,?,?)', ('autocommit','owner','opaque',9999999999))
                self.assertFalse(connection.in_transaction)
            with closing(connect(self.db)) as connection:
                connection.execute('INSERT INTO scena_web_forms(token,browser_id,payload,expires) VALUES(?,?,?,?)', ('domain-rollback','owner','opaque',9999999999))
                self.assertTrue(connection.in_transaction)
                connection.rollback()
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute('SELECT token FROM scena_web_forms').fetchall(),[('autocommit',)])


if __name__ == '__main__':
    unittest.main()
