"""Initialize shared schema once per version, not once per incoming replica."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
_lock=threading.Lock()
_ready=False
REPORT={}


def initialize():
    global _ready
    with _lock:
        if _ready:return
        started=time.monotonic()
        from scena_database import connect,cloud_database
        from scena_core import init_db
        from scena_media import initialize as media_initialize
        from .storage import initialize as web_initialize
        database=os.environ['SCENA_DB_PATH']
        Path(database).parent.mkdir(parents=True,exist_ok=True)
        revision=hashlib.sha256(b''.join((ROOT/name).read_bytes() for name in (
            'scena_core.py','scena_cabinet.py','scena_publications.py','scena_shop.py',
            'scena_prompts.py','scena_licensing.py','scena_shop_telegram.py','scena_service_telegram.py','scena_web/storage.py','scena_web/page_cache.py'))).hexdigest()
        try:
            with connect(database) as db:
                metadata=dict(db.execute("SELECT key,value FROM app_meta WHERE key IN ('cloud_native_schema','cloud_session_key')").fetchall())
        except Exception:
            # Only a first local/new database lacks app_meta; transport failures
            # must still fail closed through the normal migration connection.
            metadata={}
        if metadata.get('cloud_native_schema')!=revision:
            init_db(database)
            media_initialize()
            web_initialize()
            with connect(database) as db:
                db.execute("INSERT INTO app_meta(key,value) VALUES ('cloud_native_schema',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(revision,))
        with connect(database) as db:
            if not metadata.get('cloud_session_key'):
                db.execute("INSERT OR IGNORE INTO app_meta(key,value) VALUES ('cloud_session_key',?)",(secrets.token_hex(32),))
                metadata['cloud_session_key']=db.execute("SELECT value FROM app_meta WHERE key='cloud_session_key'").fetchone()[0]
            os.environ['SCENA_SESSION_SIGNING_KEY']=metadata['cloud_session_key']
        from scena_cloud_runtime import _ready as initialized_databases
        initialized_databases.add(str(database))
        from scena_cloud_auth import password_tag
        deployment=os.environ.get('VERCEL_DEPLOYMENT_ID') or os.environ.get('VERCEL_URL') or 'local-native'
        marker='cloud_auth_deployment:'+deployment
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM app_meta WHERE key=?',(marker,)).fetchone():
                db.execute("INSERT INTO app_meta(key,value) VALUES ('cloud_auth_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(password_tag(),))
                db.execute('INSERT INTO app_meta(key,value) VALUES (?,?)',(marker,'1'))
        REPORT.update({'status':'ok','runtime':'native-html','commit':os.environ.get('VERCEL_GIT_COMMIT_SHA','local'),
                       'boot_id':secrets.token_hex(8),'database':'connected'})
        if os.environ.get('VERCEL')=='1':
            receipt_key='cloud_native_checks:'+os.environ.get('VERCEL_GIT_COMMIT_SHA',deployment)
            with connect(database) as db:
                saved=db.execute('SELECT value FROM app_meta WHERE key=?',(receipt_key,)).fetchone()
            if saved:
                REPORT.update(json.loads(saved[0]))
                REPORT['checks_scope']='verified_for_this_deployment'
            else:
                from scena_cloud_checks import verify_services
                report=verify_services()
                with connect(database) as db:
                    db.execute('INSERT OR REPLACE INTO app_meta(key,value) VALUES (?,?)',(receipt_key,json.dumps(report)))
                REPORT.update(report)
                REPORT['checks_scope']='verified_this_process'
        from .domain_migration import migrate_public_origin
        REPORT['seo_domain_migration']=migrate_public_origin(database, os.environ)
        REPORT['startup_seconds']=round(time.monotonic()-started,3)
        os.environ['SCENA_HEALTH_REPORT']=json.dumps(REPORT)
        _ready=True
        print('SCENA native ready: '+json.dumps({'seconds':REPORT['startup_seconds'],'commit':REPORT['commit']}),flush=True)
