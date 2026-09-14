"""SCENA's native HTML web entry point for Vercel."""
import asyncio
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if os.environ.get('SCENA_WEB_TESTING')!='1':
    from deploy.start_cloud import configure
    os.environ.update(configure(dict(os.environ)))
else:
    if not os.environ.get('SCENA_ADMIN_PASSWORD') or not os.environ.get('SCENA_DB_PATH'):
        raise RuntimeError('A test database and test password are required')
os.environ['SCENA_NATIVE_WEB']='1'
from scena_web.server import serve
if __name__=='__main__':asyncio.run(serve())
