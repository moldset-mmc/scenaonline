"""Exercise the real Streamlit server through the production gateway locally."""
import asyncio
from http.cookies import SimpleCookie
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlencode

try:
    import tornado
    import libsql
except ImportError:
    raise unittest.SkipTest('Install requirements-cloud.txt for cloud acceptance tests.')

import httpx
from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

from scena_cloud_auth import COOKIE


class RealStackTests(unittest.TestCase):
    def test_login_and_authenticated_streamlit_navigation(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = dict(os.environ)
            env.update({'PORT': str(port), 'SCENA_TURSO_TURSO_DATABASE_URL': str(Path(folder)/'cloud.db'),
                        'SCENA_TURSO_TURSO_AUTH_TOKEN': 'fixture', 'SCENA_PUBLIC_BLOB_READ_WRITE_TOKEN': 'fixture',
                        'SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN': 'fixture', 'SCENA_ADMIN_PASSWORD': 'stack-fixture-secret'})
            with (Path(folder)/'server.log').open('w+') as log:
                process = subprocess.Popen([sys.executable, 'deploy/start_cloud.py'], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
                base = 'http://127.0.0.1:' + str(port)
                try:
                    with httpx.Client(trust_env=False, timeout=3) as client:
                        for _ in range(100):
                            if process.poll() is not None:
                                log.seek(0)
                                self.fail(log.read()[-4000:])
                            try:
                                response = client.get(base+'/_stcore/health')
                            except httpx.TransportError:
                                time.sleep(.1)
                                continue
                            # The first accepted request must see a ready app.
                            self.assertEqual(response.status_code, 200)
                            break
                            time.sleep(.1)
                        else:
                            log.seek(0)
                            self.fail('Server startup failed: '+log.read()[-4000:])
                        self.assertEqual(client.get(base+'/').status_code, 200)
                        response = client.get(base+'/auth/login')
                        cookies = SimpleCookie()
                        for value in response.headers.get_list('set-cookie'):
                            cookies.load(value)
                        nonce = cookies['__Host-scena_login'].value
                        response = client.post(base+'/auth/login', data={'nonce':nonce,'password':'stack-fixture-secret','next':'/?page=admin&admin=1'}, headers={'Origin':base, 'Cookie':'__Host-scena_login='+nonce})
                        self.assertEqual(response.status_code, 302)
                        for value in response.headers.get_list('set-cookie'):
                            cookies.load(value)
                        token = cookies[COOKIE].value
                    async def run_page(query):
                        request = HTTPRequest(base.replace('http:', 'ws:')+'/_stcore/stream', headers={'Origin':base, 'Cookie':COOKIE+'='+token})
                        connection = await websocket_connect(request, subprotocols=['streamlit'], max_message_size=100*1024*1024)
                        message = BackMsg()
                        message.rerun_script.query_string = query
                        await connection.write_message(message.SerializeToString(), binary=True)
                        errors, text = [], []
                        try:
                            for _ in range(1000):
                                packet = await asyncio.wait_for(connection.read_message(), timeout=20)
                                self.assertIsNotNone(packet)
                                forward = ForwardMsg()
                                forward.ParseFromString(packet)
                                if forward.HasField('delta') and forward.delta.HasField('new_element'):
                                    element = forward.delta.new_element
                                    if element.HasField('exception'):
                                        errors.append(element.exception.message)
                                    text.append(str(element))
                                if forward.HasField('script_finished'):
                                    break
                        finally:
                            connection.close()
                        self.assertEqual(errors, [])
                        rendered = '\n'.join(text)
                        self.assertNotIn('Вход в кабинет', rendered)
                        self.assertIn('Выйти', rendered)
                    asyncio.run(run_page('page=admin&admin=1&lang=ru&section=work'))
                    asyncio.run(run_page('page=admin&admin=1&lang=ru&section=pages&view=scene'))
                finally:
                    process.terminate()
                    process.wait(timeout=15)
