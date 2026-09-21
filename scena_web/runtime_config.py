"""Shared cloud runtime configuration for current native and legacy launchers."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    'SCENA_TURSO_TURSO_DATABASE_URL',
    'SCENA_TURSO_TURSO_AUTH_TOKEN',
    'SCENA_PUBLIC_BLOB_READ_WRITE_TOKEN',
    'SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN',
    'SCENA_ADMIN_PASSWORD',
)


def configure(environment):
    """Validate and normalize one isolated cloud process environment."""
    missing = [name for name in REQUIRED if not environment.get(name, '').strip()]
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
    # A launcher must always initialize; only its own child may inherit completion.
    environment.pop('SCENA_INITIALIZED_DB', None)
    return environment
