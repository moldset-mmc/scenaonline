"""Small persistent service probes, with no customer records or secret output."""
import hashlib
import io
import json
import os
import uuid

from scena_database import connect


def verify_services():
    from PIL import Image
    from vercel import blob
    import httpx
    database = os.environ['SCENA_DB_PATH']
    connection = connect(database)
    try:
        previous = connection.execute("SELECT value FROM app_meta WHERE key='cloud_storage_probe'").fetchone()
        connection.execute('BEGIN IMMEDIATE')
        cursor = connection.execute("INSERT INTO posts(created_at) VALUES ('cloud-transaction-check')")
        if not cursor.lastrowid or not connection.execute('SELECT 1 FROM posts WHERE id=?', (cursor.lastrowid,)).fetchone():
            raise RuntimeError('Remote insert identity verification failed.')
        connection.rollback()
    finally:
        connection.close()
    if previous:
        receipt = json.loads(previous[0])
    else:
        output = io.BytesIO()
        Image.new('RGB', (4, 4), '#a98648').save(output, format='PNG')
        data = output.getvalue()
        key = 'scena-service-check/' + uuid.uuid4().hex + '.png'
        receipt = {'sha256': hashlib.sha256(data).hexdigest()}
        for access in ('private', 'public'):
            receipt[access] = blob.put(key, data, access=access, token=os.environ['SCENA_'+access.upper()+'_BLOB_READ_WRITE_TOKEN'], content_type='image/png').url
    for access in ('private', 'public'):
        print('SCENA: verifying ' + access + ' storage', flush=True)
        # Consistent cache-bypass reads are supported only on private stores.
        # Public probe paths are unique and never overwritten.
        response = blob.get(receipt[access], access=access, token=os.environ['SCENA_'+access.upper()+'_BLOB_READ_WRITE_TOKEN'], use_cache=access == 'public')
        print('SCENA: ' + access + ' read status ' + str(response.status_code), flush=True)
        if response.status_code != 200 or hashlib.sha256(response.content).hexdigest() != receipt['sha256']:
            raise RuntimeError('Cloud storage round-trip verification failed.')
    print('SCENA: verifying private access denial', flush=True)
    response = httpx.get(receipt['private'], timeout=20, follow_redirects=True)
    print('SCENA: unauthenticated private status ' + str(response.status_code), flush=True)
    if response.status_code not in (401, 403, 404):
        raise RuntimeError('Private media access verification failed.')
    print("SCENA: verifying database readback", flush=True)
    connection = connect(database)
    try:
        connection.execute("INSERT INTO app_meta(key,value) VALUES ('cloud_storage_probe',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(receipt),))
        connection.commit()
    finally:
        connection.close()
    connection = connect(database)
    try:
        if json.loads(connection.execute("SELECT value FROM app_meta WHERE key='cloud_storage_probe'").fetchone()[0]) != receipt:
            raise RuntimeError('Durable database readback failed.')
    finally:
        connection.close()
    return {'database': 'verified', 'public_storage': 'verified', 'private_storage': 'verified',
            'private_access': 'blocked_without_token', 'previous_probe_recovered': bool(previous)}
