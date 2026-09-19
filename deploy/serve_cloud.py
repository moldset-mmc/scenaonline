"""Same-origin HTTP/WebSocket gateway with a private cabinet session cookie."""
from __future__ import annotations

import asyncio
import html
import hmac
import json
import os
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import tornado.httpclient
import tornado.httputil
import tornado.web
import tornado.websocket

from scena_cloud_auth import COOKIE, make_session, safe_next, valid_session, password_is_current

BACKEND = 'http://127.0.0.1:8501'
LOGIN_NONCE = '__Host-scena_login'
_attempts = []
HOP_HEADERS = {'connection', 'upgrade', 'keep-alive', 'transfer-encoding', 'content-length', 'proxy-connection'}
IMMUTABLE_ASSET = re.compile(r'^/static/(?:js|css|media)/[^/]+\.[A-Za-z0-9_-]{8}\.(?:js|css|woff2?)$')


class Health(tornado.web.RequestHandler):
    def get(self):
        self.set_header('Cache-Control', 'no-store')
        self.write(json.loads(os.environ.get('SCENA_HEALTH_REPORT', '{"status":"starting"}')))


class Login(tornado.web.RequestHandler):
    def default_destination(self):
        from scena_i18n import normalize_locale
        locale = normalize_locale(self.get_argument('lang', 'ru'))
        return '/?page=admin&admin=1&lang=' + locale

    def get(self):
        if valid_session(self.get_cookie(COOKIE)):
            self.redirect(safe_next(self.get_argument('next', self.default_destination())))
            return
        self.form()

    def form(self, error=''):
        nonce = secrets.token_urlsafe(32)
        self.set_cookie(LOGIN_NONCE, nonce, secure=True, httponly=True, samesite='Strict', path='/', max_age=600)
        self.set_header('Cache-Control', 'no-store')
        self.set_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        from scena_i18n import language_query, normalize_locale, translate_literaltext
        target = safe_next(self.get_argument('next', self.default_destination()))
        query = {key: values[-1] for key, values in parse_qs(urlsplit(target).query).items()}
        locale = normalize_locale(self.get_argument('lang', query.get('lang', 'ru')))
        label = lambda value: html.escape(translate_literaltext(locale, value))
        destination = html.escape(target, quote=True)
        self.set_header('X-Robots-Tag', 'noindex, nofollow')
        languages = ''.join('<a href="'+html.escape('/auth/login?'+urlencode({'lang':lang, 'next':'/?'+urlencode(language_query(query, lang, page=query.get('page', 'admin')))}), quote=True)+'" hreflang="'+lang+'"'+(' aria-current="page"' if locale==lang else '')+'>'+lang.upper()+'</a>' for lang in ('ru','ro','en'))
        from scena_home_style import scene_brand_markup, scene_brand_css, scene_font_css
        self.write(f'''<!doctype html><html lang="{locale}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>SCENA — {label("Вход в кабинет")}</title>
        <style>*{{box-sizing:border-box}}body{{margin:0;background:#f7f2e8;color:#171512;font:18px system-ui;min-height:100vh;display:grid;place-items:center;padding:24px}}main{{width:min(100%,420px)}}small{{letter-spacing:.28em;color:#947647}}h1{{font:40px Georgia;margin:24px 0 12px}}p{{line-height:1.5;color:#625b51}}label{{display:block;margin:28px 0 8px}}input,button{{width:100%;padding:16px;border-radius:10px;font:inherit}}input{{border:1px solid #b7aa99;background:#fff}}button{{margin-top:16px;background:#191714;color:white;border:0;cursor:pointer}}a{{display:inline-block;color:#625b51;margin-top:26px}}.error{{color:#9b2424}}nav{{display:flex;gap:8px}}nav a{{min-width:44px;min-height:44px;display:grid;place-items:center;margin:0;text-decoration:none;border:1px solid #b7aa99;border-radius:8px}}nav a[aria-current="page"]{{background:#191714;color:white}}</style>
        <style>{scene_font_css()}{scene_brand_css()}.login-brand{{position:absolute;top:16px;left:50%;transform:translateX(-50%);width:min(calc(100% - 32px),1008px)}}.login-brand a{{margin:0}}</style>
        <header class="login-brand"><a class="scene-home-brand" aria-label="MB Studio. SCENA.live" href="/?page=scene&amp;lang={locale}">{scene_brand_markup()}</a></header>
        <main><small>MY SCENA</small><h1>{label("Вход в кабинет")}</h1><p>{label("Ваши страницы, записи и настройки.")}</p><nav aria-label="{label("Язык")}">{languages}</nav><p class="error" role="alert">{label(error)}</p>
        <form method="post" action="/auth/login"><input type="hidden" name="nonce" value="{nonce}"><input type="hidden" name="next" value="{destination}"><input type="hidden" name="lang" value="{locale}"><label for="password">{label("Пароль")}</label><input id="password" name="password" type="password" required autocomplete="current-password" autofocus><button type="submit">{label("Войти")}</button></form><a href="/?page=scene&amp;lang={locale}">← {label("Открыть мою Сцену")}</a></main></html>''')

    def post(self):
        origin = urlsplit(self.request.headers.get('Origin', ''))
        if origin.netloc != self.request.host or not hmac.compare_digest(self.get_cookie(LOGIN_NONCE, ''), self.get_body_argument('nonce', 'missing')):
            self.set_status(403)
            self.form('Обновите страницу входа и повторите попытку.')
            return
        now = time.monotonic()
        _attempts[:] = [stamp for stamp in _attempts if now - stamp < 60]
        if len(_attempts) >= 8:
            self.set_status(429)
            self.set_header('Retry-After', '60')
            self.form('Подождите одну минуту перед следующей попыткой.')
            return
        candidate = self.get_body_argument('password', '')
        if not hmac.compare_digest(candidate.encode(), os.environ['SCENA_ADMIN_PASSWORD'].encode()):
            _attempts.append(now)
            self.set_status(401)
            self.form('Неверный пароль.')
            return
        _attempts.clear()
        if not password_is_current():
            self.set_status(403)
            self.form('Версия доступа изменилась. Откройте актуальный адрес вашей Сцены.')
            return
        self.set_cookie(COOKIE, make_session(), secure=True, httponly=True, samesite='Lax', path='/', max_age=12*3600)
        self.clear_cookie(LOGIN_NONCE, path='/', secure=True, httponly=True, samesite='Strict')
        self.set_header('Cache-Control', 'no-store')
        self.redirect(safe_next(self.get_body_argument('next', self.default_destination())))


class Logout(tornado.web.RequestHandler):
    def get(self):
        self.clear_cookie(COOKIE, path='/', secure=True, httponly=True, samesite='Lax')
        self.set_header('Cache-Control', 'no-store')
        from scena_i18n import normalize_locale
        self.redirect('/auth/login?'+urlencode({'lang':normalize_locale(self.get_argument('lang', 'ru'))}))


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
