"""Production entry point: durable services, authenticated cabinet, HTTP/WS."""
from __future__ import annotations

import os
import json
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def configure(environment):
    required = ('SCENA_TURSO_TURSO_DATABASE_URL', 'SCENA_TURSO_TURSO_AUTH_TOKEN',
                'SCENA_PUBLIC_BLOB_READ_WRITE_TOKEN', 'SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN',
                'SCENA_ADMIN_PASSWORD')
    missing = [name for name in required if not environment.get(name, '').strip()]
    if missing:
        raise RuntimeError('Missing SCENA configuration: ' + ', '.join(missing))
    if len(environment['SCENA_ADMIN_PASSWORD'].strip()) < 8:
        raise RuntimeError('The administrator password must contain at least eight characters.')
    environment['SCENA_ADMIN_PASSWORD'] = environment['SCENA_ADMIN_PASSWORD'].strip()
    environment['SCENA_CLOUD'] = '1'
    environment['SCENA_DB_PATH'] = '/tmp/scena-cloud/scena_master.db'
    environment['SCENA_APP_DIR'] = str(ROOT)
    environment['PYTHONPATH'] = str(ROOT)
    environment.pop('SCENA_PREVIEW_ONLY', None)
    return environment


def main():
    os.environ.update(configure(dict(os.environ)))
    os.environ.pop('SCENA_PREVIEW_ONLY', None)
    Path(os.environ['SCENA_DB_PATH']).parent.mkdir(parents=True, exist_ok=True)
    from scena_cloud_runtime import initialize_application
    from scena_database import connect
    from scena_core import get_settings, save_settings
    print('SCENA: initializing durable database', flush=True)
    initialize_application(os.environ['SCENA_DB_PATH'])
    connection = connect(os.environ['SCENA_DB_PATH'])
    try:
        connection.execute("INSERT OR IGNORE INTO app_meta(key,value) VALUES ('cloud_session_key',?)", (secrets.token_hex(32),))
        connection.commit()
        os.environ['SCENA_SESSION_SIGNING_KEY'] = connection.execute("SELECT value FROM app_meta WHERE key='cloud_session_key'").fetchone()[0]
        from scena_cloud_auth import password_tag
        connection.execute("INSERT INTO app_meta(key,value) VALUES ('cloud_auth_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (password_tag(),))
        connection.commit()
    finally:
        connection.close()
    settings = get_settings(os.environ['SCENA_DB_PATH'])
    domain = os.environ.get('VERCEL_PROJECT_PRODUCTION_URL', 'scenaonline.vercel.app')
    if not settings.get('public_base_url') or 'localhost' in settings['public_base_url']:
        save_settings(os.environ['SCENA_DB_PATH'], {'public_base_url': 'https://' + domain})
    report = {'status': 'ok', 'boot_id': secrets.token_hex(8), 'commit': os.environ.get('VERCEL_GIT_COMMIT_SHA', 'local')}
    if os.environ.get('VERCEL') == '1':
        from scena_cloud_checks import verify_services
        try:
            report.update(verify_services())
        except Exception:
            raise RuntimeError('SCENA durable service acceptance failed; inspect the configured database and Blob connections.') from None
    print('SCENA: durable services ready', flush=True)
    os.environ['SCENA_HEALTH_REPORT'] = json.dumps(report)
    os.chdir(ROOT)
    backend = subprocess.Popen([
        sys.executable, '-m', 'streamlit', 'run', 'scena-master-standalone.py',
        '--server.address', '127.0.0.1', '--server.port', '8501',
        '--server.headless', 'true', '--server.enableStaticServing', 'false',
    ])
    gateway = subprocess.Popen([sys.executable, 'deploy/serve_cloud.py'])
    def stop(*_):
        backend.terminate()
        gateway.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while backend.poll() is None and gateway.poll() is None:
            time.sleep(0.25)
    finally:
        stop()
        backend.wait(timeout=10)
        gateway.wait(timeout=10)
    raise SystemExit(backend.returncode or gateway.returncode or 0)


if __name__ == '__main__':
    main()
