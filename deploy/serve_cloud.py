"""Same-origin HTTP/WebSocket gateway with a private cabinet session cookie."""
from __future__ import annotations

import asyncio
import json
import os
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import tornado.httpclient
import tornado.httputil
import tornado.web
import tornado.websocket

from scena_cloud_auth import COOKIE, make_session, safe_next, valid_session, password_is_current

BACKEND = 'http://127.0.0.1:8501'
from scena_web.auth_handlers import Login, Logout, LOGIN_NONCE, _attempts
HOP_HEADERS = {'connection', 'upgrade', 'keep-alive', 'transfer-encoding', 'content-length', 'proxy-connection'}
IMMUTABLE_ASSET = re.compile(r'^/static/(?:js|css|media)/[^/]+\.[A-Za-z0-9_-]{8}\.(?:js|css|woff2?)$')


class Health(tornado.web.RequestHandler):
    def get(self):
        self.set_header('Cache-Control', 'no-store')
        self.write(json.loads(os.environ.get('SCENA_HEALTH_REPORT', '{"status":"starting"}')))


def forwarded_headers(request):
    headers = tornado.httputil.HTTPHeaders()
    for name, value in request.headers.get_all():
        if name.lower() not in HOP_HEADERS and not name.lower().startswith(('x-scena-', 'sec-websocket-')):
            headers.add(name, value)
    token = request.cookies.get(COOKIE)
    if token and valid_session(token.value):
        headers['X-Scena-Session'] = token.value
    return headers


class Proxy(tornado.web.RequestHandler):
    async def prepare(self):
        if self.request.method not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}:
            self.set_status(405)
            self.finish()
            return
        query = parse_qs(self.request.query)
        is_admin = query.get('admin') == ['1'] or query.get('page') == ['admin']
        if is_admin and not valid_session(self.get_cookie(COOKIE)):
            self.redirect('/auth/login?' + urlencode({'next': self.request.uri}))
            return
        request = tornado.httpclient.HTTPRequest(
            BACKEND + self.request.uri, method=self.request.method,
            headers=forwarded_headers(self.request),
            body=self.request.body if self.request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else None,
            follow_redirects=False, decompress_response=False, request_timeout=120,
            allow_nonstandard_methods=True,
        )
        try:
            response = await tornado.httpclient.AsyncHTTPClient().fetch(request, raise_error=False)
        except (tornado.httpclient.HTTPClientError, OSError):
            self.set_status(503)
            self.set_header('Retry-After', '3')
            self.finish('SCENA запускается. Обновите страницу через несколько секунд.')
            return
        self.set_status(response.code)
        for name, value in response.headers.get_all():
            if name.lower() not in HOP_HEADERS:
                self.add_header(name, value)
        if is_admin:
            self.set_header('Cache-Control', 'no-store')
        elif (response.code == 200 and self.request.method in {'GET', 'HEAD'}
              and IMMUTABLE_ASSET.fullmatch(self.request.path)
              and 'Set-Cookie' not in response.headers):
            # Browser max-age alone did not cache container responses on Vercel.
            # Only content-hashed framework assets are shared between visitors.
            self.set_header('Vercel-CDN-Cache-Control', 'public, max-age=31536000, immutable')
        self.finish(response.body or b'')


class SocketProxy(tornado.websocket.WebSocketHandler):
    upstream = None

    def check_origin(self, origin):
        return urlsplit(origin).netloc == self.request.host

    def select_subprotocol(self, subprotocols):
        return 'streamlit' if 'streamlit' in subprotocols else None

    async def open(self):
        request = tornado.httpclient.HTTPRequest(
            BACKEND.replace('http:', 'ws:') + self.request.uri,
            headers=forwarded_headers(self.request), request_timeout=30,
        )
        raw_protocols = self.request.headers.get('Sec-WebSocket-Protocol', '')
        protocols = [p.strip() for p in raw_protocols.split(',')] if raw_protocols else None
        try:
            self.upstream = await tornado.websocket.websocket_connect(request, subprotocols=protocols, max_message_size=100*1024*1024)
            asyncio.create_task(self.relay())
        except Exception:
            self.close(code=1011, reason='SCENA reconnect')

    async def relay(self):
        try:
            while self.upstream:
                message = await self.upstream.read_message()
                if message is None:
                    break
                await self.write_message(message, binary=isinstance(message, bytes))
        except tornado.websocket.WebSocketClosedError:
            pass
        finally:
            self.close()

    async def on_message(self, message):
        if self.upstream:
            await self.upstream.write_message(message, binary=isinstance(message, bytes))

    def on_close(self):
        if self.upstream:
            self.upstream.close()


async def serve():
    app = tornado.web.Application([
        (r'/healthz', Health),
        (r'/auth/login', Login), (r'/auth/logout', Logout),
        (r'/_stcore/stream', SocketProxy), (r'/.*', Proxy),
    ], websocket_ping_interval=20, websocket_ping_timeout=20, websocket_max_message_size=100*1024*1024)
    app.listen(int(os.environ.get('PORT', '80')), address='0.0.0.0', max_buffer_size=100*1024*1024)
    await asyncio.Event().wait()


if __name__ == '__main__':
    asyncio.run(serve())
