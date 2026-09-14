"""Server-only, expiring cabinet sessions. No credentials in URLs or HTML."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

COOKIE = '__Host-scena_session'
_active_version_cache = (0, '')


def _key():
    return bytes.fromhex(os.environ['SCENA_SESSION_SIGNING_KEY'])


def password_tag():
    return hmac.new(_key(), os.environ['SCENA_ADMIN_PASSWORD'].encode(), hashlib.sha256).hexdigest()


def password_is_current():
    global _active_version_cache
    if os.environ.get('SCENA_CLOUD') != '1':
        return True
    try:
        now = time.monotonic()
        if now - _active_version_cache[0] > 5:
            from scena_database import connect
            connection = connect(os.environ['SCENA_DB_PATH'])
            try:
                row = connection.execute("SELECT value FROM app_meta WHERE key='cloud_auth_version'").fetchone()
            finally:
                connection.close()
            _active_version_cache = (now, row[0] if row else '')
        return hmac.compare_digest(_active_version_cache[1], password_tag())
    except Exception:
        return False


def make_session(*, now=None):
    now = int(time.time() if now is None else now)
    body = json.dumps({'until': now + 12*3600, 'nonce': secrets.token_hex(16), 'version': password_tag()}, separators=(',', ':')).encode()
    payload = base64.urlsafe_b64encode(body).decode().rstrip('=')
    signature = hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature


def valid_session(token, *, now=None):
    try:
        if not token or len(token) > 1024:
            return False
        payload, signature = token.split('.')
        expected = hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        body = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        now = time.time() if now is None else now
        return body['until'] > now and hmac.compare_digest(body['version'], password_tag()) and password_is_current()
    except (ValueError, KeyError, TypeError, UnicodeError):
        return False


def safe_next(value):
    return value if value.startswith('/') and not value.startswith('//') and '\\' not in value and '\r' not in value and '\n' not in value else '/?page=admin&admin=1&lang=ru'
