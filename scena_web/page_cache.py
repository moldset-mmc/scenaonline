"""Shared rendered public pages with transaction-bound content invalidation.

Never caches forms, owner views or error responses. Database triggers advance
one revision in the same transaction as an edit; a concurrent stale render
cannot be inserted under the new revision. Expiry also covers time-based content.
"""
from contextlib import closing
import hashlib
import os
import time
from urllib.parse import urlencode
from scena_database import connect

TTL = 300


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS scena_web_page_revision (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL)')
    db.execute('INSERT OR IGNORE INTO scena_web_page_revision VALUES (1,0)')
    db.execute('CREATE TABLE IF NOT EXISTS scena_web_pages (key TEXT PRIMARY KEY, version INTEGER NOT NULL, document TEXT NOT NULL, url TEXT NOT NULL, expires REAL NOT NULL)')
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for (table,) in tables:
        if table.startswith(('sqlite_', 'scena_web_')) or table == 'app_meta':
            continue
        quoted = '"' + table.replace('"', '""') + '"'
        for event in ('INSERT', 'UPDATE', 'DELETE'):
            name = 'scena_web_invalidate_' + hashlib.sha256((table + event).encode()).hexdigest()[:20]
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS {name} AFTER {event} ON {quoted} BEGIN
                UPDATE scena_web_page_revision SET version=version+1 WHERE id=1;
                DELETE FROM scena_web_pages;
            END''')


def key(query, browser_locale="ru", host=""):
    # Bound the key space; parameters with a functional effect are retained.
    if set(query) - {'page', 'lang', 'post', 'destination'}:
        return None
    if query.get('page', 'scene') not in {'scene', 'portfolio', 'professional', 'model', 'posts', 'post', 'shop'}:
        return None
    language_variant = next((v for v in ('ru', 'ro', 'en') if browser_locale.lower().startswith(v)), 'default') if query.get('lang') not in {'ru', 'ro', 'en'} else ''
    source = 'seo-v1|' + str(host).lower() + '|' + os.environ.get('VERCEL_GIT_COMMIT_SHA', 'local') + '|' + language_variant + '|' + urlencode(sorted(query.items()))
    return hashlib.sha256(source.encode()).hexdigest()


def lookup(cache_key):
    with closing(connect(os.environ['SCENA_DB_PATH'], isolation_level=None)) as db:
        row = db.execute('''SELECT r.version,p.document,p.url FROM scena_web_page_revision r
            LEFT JOIN scena_web_pages p ON p.key=? AND p.version=r.version AND p.expires>?
            WHERE r.id=1''', (cache_key, time.time())).fetchone()
    return row[0], (row[1], row[2]) if row[1] is not None else None


def save(cache_key, version, document, url):
    with closing(connect(os.environ['SCENA_DB_PATH'], isolation_level=None)) as db:
        # INSERT ... SELECT guards against edits during the render, across replicas.
        db.execute('''INSERT OR REPLACE INTO scena_web_pages(key,version,document,url,expires)
            SELECT ?,version,?,?,? FROM scena_web_page_revision WHERE id=1 AND version=?''',
            (cache_key, document, url, time.time() + TTL, version))
        # Cleanup is independent of the atomic cache insert; no transaction
        # remains open while another request/round trip is in progress.
        db.execute('DELETE FROM scena_web_pages WHERE expires<=?', (time.time(),))
