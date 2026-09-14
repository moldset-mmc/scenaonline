import os
from http.cookies import SimpleCookie
from urllib.parse import urlencode
from unittest.mock import patch
import unittest

try:
    import tornado
except ImportError:
    raise unittest.SkipTest('Install requirements-cloud.txt for cloud acceptance tests.')

from tornado import web, httpserver, httputil, websocket
from tornado.testing import AsyncHTTPTestCase, bind_unused_port, gen_test
from tornado.httpclient import HTTPRequest

from deploy import serve_cloud
from scena_cloud_auth import COOKIE, make_session


class Echo(web.RequestHandler):
    def get(self):
        self.write(self.request.headers.get('X-Scena-Session', 'anonymous'))


class EchoSocket(websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True
    def select_subprotocol(self, protocols):
        return 'streamlit'
    def open(self):
        self.write_message('authenticated' if self.request.headers.get('X-Scena-Session') else 'anonymous')
    def on_message(self, message):
        self.write_message(message, binary=isinstance(message, bytes))


class FrameworkAsset(web.RequestHandler):
    def get(self, filename):
        if filename.startswith('missing'):
            self.set_status(404)
        if filename.startswith('cookie'):
            self.set_cookie('fixture', 'private')
        self.set_header('Content-Type', 'application/javascript')
        self.write('/* immutable public framework asset */')


class GatewayTests(AsyncHTTPTestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'SCENA_SESSION_SIGNING_KEY': 'ab'*32, 'SCENA_ADMIN_PASSWORD': 'fixture-secret'})
        self.environment.start()
        serve_cloud._attempts.clear()
        super().setUp()

    def get_app(self):
        socket, port = bind_unused_port()
        self.backend = httpserver.HTTPServer(web.Application([(r'/_stcore/stream', EchoSocket), (r'/static/js/(.*)', FrameworkAsset), (r'/.*', Echo)]))
        self.backend.add_socket(socket)
        self.backend_patch = patch.object(serve_cloud, 'BACKEND', 'http://127.0.0.1:' + str(port))
        self.backend_patch.start()
        return web.Application([(r'/auth/login', serve_cloud.Login), (r'/auth/logout', serve_cloud.Logout), (r'/_stcore/stream', serve_cloud.SocketProxy), (r'/.*', serve_cloud.Proxy)])

    def tearDown(self):
        self.backend.stop()
        self.backend_patch.stop()
        self.environment.stop()
        super().tearDown()

    def test_private_route_redirects_and_spoofed_header_is_removed(self):
        response = self.fetch('/?page=admin', follow_redirects=False)
        self.assertEqual(response.code, 302)
        response = self.fetch('/', headers={'X-Scena-Session': 'forged'})
        self.assertEqual(response.body, b'anonymous')
        token = make_session()
        response = self.fetch('/?page=admin', headers={'Cookie': COOKIE + '=' + token})
        self.assertEqual(response.body.decode(), token)

    def test_unavailable_backend_returns_retryable_response(self):
        self.backend.stop()
        response = self.fetch('/')
        self.assertEqual(response.code, 503)
        self.assertEqual(response.headers['Retry-After'], '3')
        self.assertNotIn(b'Traceback', response.body)

    def test_only_successful_immutable_public_assets_enter_shared_cache(self):
        response = self.fetch('/static/js/index.Abc123_-.js')
        self.assertEqual(response.code, 200)
        self.assertIn('max-age=31536000', response.headers['Vercel-CDN-Cache-Control'])
        for path in ('/', '/auth/login', '/static/js/index.js',
                     '/static/js/missing.Abc123_-.js', '/static/js/cookie.Abc123_-.js'):
            response = self.fetch(path)
            self.assertNotIn('Vercel-CDN-Cache-Control', response.headers)
        token = make_session()
        response = self.fetch('/?page=admin', headers={'Cookie': COOKIE + '=' + token})
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertNotIn('Vercel-CDN-Cache-Control', response.headers)

    def test_login_uses_csrf_and_sets_secure_http_only_session(self):
        response = self.fetch('/auth/login')
        cookies = SimpleCookie()
        for header in response.headers.get_list('Set-Cookie'):
            cookies.load(header)
        nonce = cookies[serve_cloud.LOGIN_NONCE].value
        body = urlencode({'nonce': nonce, 'password': 'fixture-secret', 'next': '/?page=admin'})
        headers = {'Cookie': serve_cloud.LOGIN_NONCE + '=' + nonce, 'Origin': self.get_url('/').rstrip('/'), 'Content-Type': 'application/x-www-form-urlencoded'}
        response = self.fetch('/auth/login', method='POST', body=body, headers=headers, follow_redirects=False)
        self.assertEqual(response.code, 302)
        self.assertEqual(response.headers['Location'], '/?page=admin')
        session = next(h for h in response.headers.get_list('Set-Cookie') if h.startswith(COOKIE + '='))
        self.assertIn('HttpOnly', session)
        self.assertIn('Secure', session)
        self.assertIn('SameSite=Lax', session)
        response = self.fetch('/auth/login', method='POST', body=body, follow_redirects=False)
        self.assertEqual(response.code, 403)

    @gen_test
    async def test_authenticated_websocket_preserves_binary_messages(self):
        token = make_session()
        request = HTTPRequest(self.get_url('/_stcore/stream').replace('http:', 'ws:'), headers={'Cookie': COOKIE + '=' + token, 'Origin': self.get_url('/').rstrip('/')})
        connection = await websocket.websocket_connect(request, subprotocols=['streamlit'])
        self.assertEqual(await connection.read_message(), 'authenticated')
        await connection.write_message(b'fixture-message', binary=True)
        self.assertEqual(await connection.read_message(), b'fixture-message')
        connection.close()
