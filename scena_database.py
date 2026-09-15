"""SQLite API boundary: local files offline, authenticated libSQL in the cloud."""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3


def cloud_database(database=None):
    if os.environ.get('SCENA_CLOUD') != '1':
        return False
    if database is None:
        return True
    return str(database) == os.environ.get('SCENA_DB_PATH') or (
        not str(database).startswith('file:')
        and Path(database).resolve() == Path(os.environ['SCENA_DB_PATH']).resolve()
    )


class Row:
    def __init__(self, description, values):
        self._keys = tuple(column[0] for column in description)
        self._values = tuple(values)

    def keys(self):
        return list(self._keys)

    def __getitem__(self, key):
        if isinstance(key, str):
            for index, name in enumerate(self._keys):
                if name.casefold() == key.casefold():
                    return self._values[index]
            raise IndexError('No item with that key')
        return self._values[key]

    def __len__(self):
        return len(self._values)

    def __iter__(self):
        return iter(self._values)


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValueError as exc:
        # libsql 0.1.11 exposes SQLite engine errors as ValueError.
        message = str(exc)
        if 'constraint' in message.lower():
            raise sqlite3.IntegrityError(message) from exc
        if 'binding' in message.lower() or 'parameter' in message.lower():
            raise sqlite3.ProgrammingError(message) from exc
        raise sqlite3.OperationalError(message) from exc


class Cursor:
    def __init__(self, connection, native):
        self.connection, self.native = connection, native

    @property
    def description(self):
        return self.native.description

    @property
    def lastrowid(self):
        return self.native.lastrowid

    @property
    def rowcount(self):
        return self.native.rowcount

    def execute(self, sql, parameters=()):
        _call(self.native.execute, sql, parameters)
        return self

    def executemany(self, sql, parameters):
        _call(self.native.executemany, sql, list(parameters))
        return self

    def _row(self, value):
        if value is None:
            return None
        if self.connection.row_factory is sqlite3.Row:
            return Row(self.description, value)
        if self.connection.row_factory:
            return self.connection.row_factory(self, value)
        return tuple(value)

    def fetchone(self):
        return self._row(_call(self.native.fetchone))

    def fetchall(self):
        return [self._row(row) for row in _call(self.native.fetchall)]

    def fetchmany(self, size=1):
        return [self._row(row) for row in _call(self.native.fetchmany, size)]

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

    def close(self):
        self.native.close()


class Connection:
    def __init__(self, native, *, remote=False):
        self.remote = remote
        self.native, self.row_factory = native, None
        self._closed = False

    @property
    def in_transaction(self):
        return self.native.in_transaction

    def cursor(self):
        return Cursor(self, self.native.cursor())

    def execute(self, sql, parameters=()):
        return self.cursor().execute(sql, parameters)

    def executemany(self, sql, parameters):
        return self.cursor().executemany(sql, parameters)

    def executescript(self, sql):
        return Cursor(self, _call(self.native.executescript, sql))

    def commit(self):
        _call(self.native.commit)

    def rollback(self):
        _call(self.native.rollback)

    def close(self):
        if not self._closed:
            self._closed = True
            self.native.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind is not None:
            self.rollback()
        else:
            try:
                self.commit()
            except Exception:
                self.rollback()
                raise

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def is_connection(value):
    return isinstance(value, (sqlite3.Connection, Connection))


def connect(database, timeout=5, **kwargs):
    remote = cloud_database(database)
    if not remote and os.environ.get('SCENA_DB_DRIVER') != 'libsql':
        return sqlite3.connect(database, timeout=timeout, **kwargs)
    if kwargs.get('uri'):
        # Offline archive inspection always reads the requested local file.
        return sqlite3.connect(database, timeout=timeout, **kwargs)
    import libsql
    if remote:
        url = os.environ.get('SCENA_TURSO_TURSO_DATABASE_URL', '')
        token = os.environ.get('SCENA_TURSO_TURSO_AUTH_TOKEN', '')
        if not url or not token:
            raise RuntimeError('SCENA database credentials are missing.')
        native = _call(libsql.connect, url, auth_token=token, timeout=timeout, **kwargs)
    else:
        native = _call(libsql.connect, str(database), timeout=timeout, **kwargs)
    return Connection(native, remote=remote)


def snapshot_to_file(database, destination):
    """Export one consistent cloud read transaction to a portable SQLite file."""
    source = connect(database)
    target = sqlite3.connect(destination)
    try:
        source.execute('BEGIN')
        schema = source.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type='table' DESC,name").fetchall()
        target.execute('PRAGMA foreign_keys=OFF')
        for kind, name, sql in schema:
            if kind != 'table':
                continue
            target.execute(sql)
            quoted = '"' + name.replace('"', '""') + '"'
            cursor = source.execute('SELECT * FROM ' + quoted)
            marks = ','.join('?' for _ in cursor.description)
            while rows := cursor.fetchmany(256):
                target.executemany('INSERT INTO ' + quoted + ' VALUES (' + marks + ')', rows)
        if source.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone():
            target.execute('DELETE FROM sqlite_sequence')
            target.executemany('INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)', source.execute('SELECT name,seq FROM sqlite_sequence').fetchall())
        for kind, name, sql in schema:
            if kind != 'table':
                target.execute(sql)
        target.commit()
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise sqlite3.DatabaseError('Backup integrity verification failed.')
        source.commit()
    except Exception:
        source.rollback()
        raise
    finally:
        source.close()
        target.close()
