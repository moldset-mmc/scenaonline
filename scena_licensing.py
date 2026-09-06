"""Signed, owner-bound PRO renewals. Only an issuer's public key is used here."""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


class LicenseError(ValueError):
    pass


def initialize_licensing(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS pro_code_redemptions (
        nonce TEXT PRIMARY KEY, owner_id TEXT NOT NULL, code_digest TEXT NOT NULL UNIQUE,
        days INTEGER NOT NULL CHECK(days BETWEEN 1 AND 730), redeemed_at TEXT NOT NULL,
        expires_at TEXT NOT NULL)""")


def _now(now=None):
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def owner_id(db_path) -> str:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT value FROM app_meta WHERE key='owner_id'").fetchone()
    if not row:
        raise LicenseError("Не найден номер вашего профиля. Перезапустите SCENA.")
    try:
        return str(uuid.UUID(row[0]))
    except ValueError as exc:
        raise LicenseError("Не удалось прочитать номер профиля.") from exc


def _decode(value: str) -> bytes:
    try:
        return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    except (ValueError, TypeError) as exc:
        raise LicenseError("Проверьте код: вставьте его полностью.") from exc


def _public_key(app_dir):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    path = Path(app_dir) / 'config' / 'pro-issuer-public.pem'
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError('wrong key type')
        return key
    except (OSError, ValueError, TypeError) as exc:
        raise LicenseError("Не удалось проверить код. Передайте его команде SCENA вместе с номером профиля.") from exc


def issuer_ready(app_dir) -> bool:
    try:
        _public_key(app_dir)
        return True
    except (LicenseError, ImportError):
        return False


def redeem_code(db_path, app_dir, code: str, *, now=None) -> dict:
    """Idempotent transaction: the same signed nonce can extend a profile once."""
    from cryptography.exceptions import InvalidSignature
    current = _now(now)
    token = ''.join(str(code).split())
    if not token or len(token) > 2048:
        raise LicenseError("Вставьте полный код продления SCENA.")
    try:
        prefix, body, signature = token.split('.')
        if prefix != 'SCENA1':
            raise ValueError('prefix')
        payload_bytes = _decode(body)
        _public_key(app_dir).verify(_decode(signature), payload_bytes)
        payload = json.loads(payload_bytes)
        if not isinstance(payload, dict) or set(payload) != {'v', 'owner', 'days', 'nonce', 'iat', 'exp'}:
            raise ValueError('fields')
        if type(payload['v']) is not int or payload['v'] != 1:
            raise ValueError('version')
        if type(payload['days']) is not int or not 1 <= payload['days'] <= 730:
            raise ValueError('duration')
        if type(payload['iat']) is not int or type(payload['exp']) is not int:
            raise ValueError('time')
        if payload['exp'] <= payload['iat']:
            raise ValueError('time order')
        uuid.UUID(payload['nonce'])
        if payload['owner'] != owner_id(db_path):
            raise LicenseError("Этот код создан для другого профиля. Проверьте номер у команды SCENA.")
    except LicenseError:
        raise
    except (InvalidSignature, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise LicenseError("Код не прошёл проверку. Скопируйте его целиком из сообщения SCENA.") from exc
    digest = hashlib.sha256(token.encode()).hexdigest()
    with sqlite3.connect(db_path, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('BEGIN IMMEDIATE')
        initialize_licensing(connection)
        existing = connection.execute('SELECT * FROM pro_code_redemptions WHERE nonce=?', (payload['nonce'],)).fetchone()
        if existing:
            if existing['code_digest'] != digest:
                raise LicenseError("Код уже использован. Обратитесь в SCENA за проверкой.")
            return {'expires_at': existing['expires_at'], 'days': existing['days'], 'already_used': True}
        if payload['iat'] > int(current.timestamp()) + 300 or payload['exp'] <= int(current.timestamp()):
            raise LicenseError("Срок активации кода истёк или ещё не начался. Запросите проверку в SCENA.")
        subscription = connection.execute("SELECT * FROM pro_subscriptions WHERE owner_key='master'").fetchone()
        if not subscription:
            raise LicenseError("Не удалось найти вашу подписку.")
        old_expiry = _now(datetime.fromisoformat(subscription['expires_at']))
        expiry = max(current, old_expiry) + timedelta(days=payload['days'])
        stamp, end = current.isoformat(timespec='seconds'), expiry.isoformat(timespec='seconds')
        connection.execute("""UPDATE pro_subscriptions SET tier='PRO', status='active',
            expires_at=?, updated_at=? WHERE owner_key='master'""", (end, stamp))
        connection.execute('INSERT INTO pro_code_redemptions VALUES (?,?,?,?,?,?)',
                           (payload['nonce'], payload['owner'], digest, payload['days'], stamp, end))
        return {'expires_at': end, 'days': payload['days'], 'already_used': False}


def sign_code(private_key, profile_id: str, days: int, *, now=None, valid_days: int = 14) -> str:
    """Issuer-only primitive. Call only after an operator verifies payment."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if not isinstance(private_key, Ed25519PrivateKey):
        raise LicenseError('An Ed25519 issuer key is required.')
    profile_id = str(uuid.UUID(profile_id))
    if type(days) is not int or not 1 <= days <= 730 or not 1 <= valid_days <= 90:
        raise LicenseError('Invalid duration.')
    current = _now(now)
    payload = {'v': 1, 'owner': profile_id, 'days': days, 'nonce': str(uuid.uuid4()),
               'iat': int(current.timestamp()), 'exp': int((current + timedelta(days=valid_days)).timestamp())}
    body = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
    return f'SCENA1.{encode(body)}.{encode(private_key.sign(body))}'
