"""SCENA intake. Independent database and private objects; no salon credentials."""
from __future__ import annotations

import asyncio
from contextlib import closing
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import hmac
from io import BytesIO
import json
import os
import re
import sqlite3
import time
import uuid
import warnings

from PIL import Image
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.web import HTTPError, RequestHandler

MAX_PHOTO = 4 * 1024 * 1024
TTL = 30 * 86400
MIMES = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}
READINESS = ['Уже есть', 'Создадим вместе', 'Пока не знаю']
ENUMS = {
    'specialty': ['Визажист', 'Стилист', 'Бьюти-мастер', 'Салон / студия', 'Другое'],
    'booking': ['Заявка на сайте', 'Через мессенджер', 'Обсудим вместе'],
    'style': ['Светлый и воздушный', 'Выразительный и яркий', 'Сдержанный и элегантный', 'Доверюсь вам'],
    'domainStatus': READINESS, 'github': READINESS, 'vercel': READINESS,
    'timing': ['Как можно скорее', 'В течение месяца', 'Без спешки'],
}
ARRAYS = {
    'features': ['Запись на услуги', 'Портфолио', 'Курсы', 'Магазин', 'Визитка и QR', 'Нужна помощь с выбором'],
    'languages': ['Русский', 'Română', 'English'],
}
LENGTHS = {'name': 70, 'brand': 80, 'city': 80, 'services': 450, 'inspiration': 200,
           'about': 220, 'domain': 120, 'accountEmail': 160, 'contact': 160, 'notes': 250}
EMAIL = r'[^\s@]+@[^\s@]+\.[^\s@]+'
SCHEMA = [
    '''CREATE TABLE IF NOT EXISTS intake (
       id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, answers TEXT NOT NULL, manifest TEXT NOT NULL,
       ip_hash TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, reserved_bytes INTEGER NOT NULL,
       state TEXT NOT NULL DEFAULT 'uploading', message_id INTEGER)''',
    'CREATE INDEX IF NOT EXISTS intake_rate ON intake(ip_hash, created)',
    '''CREATE TABLE IF NOT EXISTS intake_photos (
       intake_id TEXT NOT NULL, position INTEGER NOT NULL, location TEXT NOT NULL,
       PRIMARY KEY(intake_id, position))''',
]


def fail(status, message):
    raise HTTPError(status, reason=message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != {'id', 'answers', 'photos', 'website'}:
        fail(400, 'Проверьте анкету.')
    try:
        identifier = str(uuid.UUID(payload['id']))
    except (ValueError, TypeError, AttributeError):
        fail(400, 'Некорректный номер анкеты.')
    if payload['id'] != identifier or payload['website'] != '':
        fail(400, 'Проверьте анкету.')
    answers = payload['answers']
    if not isinstance(answers, dict) or set(answers) != set(LENGTHS) | set(ENUMS) | set(ARRAYS) | {'consent'}:
        fail(400, 'Проверьте поля анкеты.')
    a = dict(answers)
    for key, limit in LENGTHS.items():
        if not isinstance(a[key], str) or len(a[key].strip()) > limit:
            fail(400, 'Слишком длинное или некорректное поле.')
        a[key] = a[key].strip()
        if any(ord(c) < 32 and c not in '\n\r\t' for c in a[key]):
            fail(400, 'Некорректные символы в анкете.')
    for key, options in ENUMS.items():
        if a[key] not in options:
            fail(400, 'Выберите вариант в анкете.')
    for key, options in ARRAYS.items():
        values = a[key]
        if not isinstance(values, list) or not 1 <= len(values) <= len(options) or any(v not in options for v in values):
            fail(400, 'Выберите варианты в анкете.')
        if len(set(values)) != len(values):
            fail(400, 'Варианты не должны повторяться.')
    if len(a['name']) < 2 or a['consent'] is not True:
        fail(400, 'Укажите имя и подтвердите согласие.')
    if a['accountEmail'] and not re.fullmatch(EMAIL, a['accountEmail']):
        fail(400, 'Проверьте email.')
    contact = a['contact']
    if not (re.fullmatch(r'@[a-zA-Z0-9_]{5,32}', contact) or re.fullmatch(EMAIL, contact)
            or (re.fullmatch(r'[+\d ()-]{7,30}', contact) and len(re.sub(r'\D', '', contact)) >= 7)):
        fail(400, 'Проверьте контакт для связи.')
    photos = payload['photos']
    if not isinstance(photos, list) or len(photos) > 6:
        fail(400, 'Можно добавить до 6 фотографий.')
    for p in photos:
        if (not isinstance(p, dict) or set(p) != {'sha256', 'bytes', 'type'}
                or not isinstance(p['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', p['sha256'])
                or type(p['bytes']) is not int or not 0 < p['bytes'] <= MAX_PHOTO
                or not isinstance(p['type'], str) or p['type'] not in MIMES):
            fail(400, 'Подойдут JPG, PNG или WebP до 4 МБ.')
    return identifier, a, photos


@dataclass(frozen=True)
class Config:
    database: str
    auth: str
    blob: str
    bot: str
    chat: str
    enabled: bool
    origin: str = 'https://scena.life'
    max_bytes: int = 256 * 1024 * 1024

    @classmethod
    def from_env(cls):
        prefix = 'SCENA_INTAKE_'
        return cls(os.getenv(prefix + 'TURSO_DATABASE_URL', ''), os.getenv(prefix + 'TURSO_AUTH_TOKEN', ''),
                   os.getenv(prefix + 'BLOB_READ_WRITE_TOKEN', ''), os.getenv(prefix + 'TELEGRAM_BOT_TOKEN', ''),
                   os.getenv(prefix + 'TELEGRAM_CHAT_ID', ''), os.getenv(prefix + 'ENABLED') == '1')

    def configured(self):
        return bool(self.enabled and self.database.startswith('libsql://') and self.auth and self.blob
                    and re.fullmatch(r'\d+:[A-Za-z0-9_-]+', self.bot) and re.fullmatch(r'[1-9]\d{4,19}', self.chat))


class Store:
    def __init__(self, config, connect=None):
        self.config = config
        self._connect = connect or self._remote
        self.initialized = False

    def _remote(self):
        import libsql
        from scena_database import Connection
        db = Connection(libsql.connect(self.config.database, auth_token=self.config.auth, isolation_level=None), remote=True)
        db.row_factory = sqlite3.Row
        return db

    def run(self, action):
        with closing(self._connect()) as db:
            if not self.initialized:
                for sql in SCHEMA:
                    db.execute(sql)
                self.initialized = True
            return action(db)

    def row(self, identifier):
        return self.run(lambda db: db.execute('SELECT * FROM intake WHERE id=?', (identifier,)).fetchone())

    def token(self, purpose, row):
        # Dedicated private-store credential only; no salon secret fallback.
        message = f"scena-intake-v1:{purpose}:{row['id']}:{row['fingerprint']}"
        return hmac.new(self.config.blob.encode(), message.encode(), hashlib.sha256).hexdigest()

    def authorize(self, identifier, token, purpose):
        row = self.row(identifier)
        if not row or row['expires'] <= time.time() or not hmac.compare_digest(self.token(purpose, row), token):
            fail(404, 'Ссылка недоступна или срок её действия истёк.')
        return row

    def start(self, payload, ip):
        identifier, answers, manifest = validate(payload)
        fingerprint = hashlib.sha256(canonical([answers, manifest]).encode()).hexdigest()
        ip_hash = hmac.new(self.config.blob.encode(), ('ip:' + ip).encode(), hashlib.sha256).hexdigest()
        now = time.time()
        def create(db):
            db.execute('''INSERT OR IGNORE INTO intake(id,fingerprint,answers,manifest,ip_hash,created,expires,reserved_bytes)
                SELECT ?,?,?,?,?,?,?,? WHERE
                (SELECT count(*) FROM intake WHERE ip_hash=? AND created>?) < 4 AND
                (SELECT count(*) FROM intake) < 2000 AND
                (SELECT COALESCE(sum(reserved_bytes),0) FROM intake) + ? <= ?''',
                (identifier, fingerprint, canonical(answers), canonical(manifest), ip_hash, now, now + TTL,
                 sum(p['bytes'] for p in manifest), ip_hash, now - 3600,
                 sum(p['bytes'] for p in manifest), self.config.max_bytes))
            return db.execute('SELECT * FROM intake WHERE id=?', (identifier,)).fetchone()
        row = self.run(create)
        if not row:
            fail(429, 'Приём временно ограничен. Попробуйте позже.')
        if row['fingerprint'] != fingerprint:
            fail(409, 'Эта анкета уже отправлялась с другими данными. Обновите номер и повторите отправку.')
        if row['expires'] <= now:
            fail(410, 'Срок черновика истёк. Начните новую анкету.')
        return {**receipt(row), 'uploadToken': self.token('upload', row)}

    def put_photo(self, identifier, position, token, content, mime):
        row = self.authorize(identifier, token, 'upload')
        manifest = json.loads(row['manifest'])
        if row['state'] != 'uploading' or not 0 <= position < len(manifest):
            fail(409, 'Фотографии этой анкеты уже нельзя изменить.')
        expected = manifest[position]
        if len(content) != expected['bytes'] or mime != expected['type'] or hashlib.sha256(content).hexdigest() != expected['sha256']:
            fail(400, 'Фотография изменилась. Выберите её заново.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as photo:
                    if photo.format != MIMES[mime] or photo.width * photo.height > 40_000_000 or getattr(photo, 'n_frames', 1) != 1:
                        raise ValueError('Unsupported image')
                    photo.verify()
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            fail(400, 'Не удалось прочитать фотографию. Сохраните её как обычный JPG, PNG или WebP.')
        exists = self.run(lambda db: db.execute('SELECT 1 FROM intake_photos WHERE intake_id=? AND position=?', (identifier, position)).fetchone())
        if not exists:
            location = self.write_blob(f'intake/{identifier}/{position}-{expected["sha256"]}', content, mime)
            self.run(lambda db: db.execute('INSERT OR IGNORE INTO intake_photos VALUES (?,?,?)', (identifier, position, location)))
        return {'uploaded': True}

    def write_blob(self, path, content, mime):
        from vercel import blob
        return blob.put(path, content, access='private', token=self.config.blob, content_type=mime,
                        overwrite=True, add_random_suffix=False).url

    def read_photo(self, row, position):
        p = self.run(lambda db: db.execute('SELECT location FROM intake_photos WHERE intake_id=? AND position=?', (row['id'], position)).fetchone())
        manifest = json.loads(row['manifest'])
        if not p or not 0 <= position < len(manifest):
            fail(404, 'Фотография недоступна.')
        from vercel import blob
        response = blob.get(p['location'], access='private', token=self.config.blob, use_cache=False)
        expected = manifest[position]
        if response.status_code != 200 or len(response.content) != expected['bytes'] or hashlib.sha256(response.content).hexdigest() != expected['sha256']:
            fail(502, 'Не удалось загрузить фотографию.')
        return response.content, expected['type']

    def claim(self, identifier, token):
        row = self.authorize(identifier, token, 'upload')
        claimed = self.run(lambda db: db.execute('''UPDATE intake SET state='sending' WHERE id=? AND state='uploading'
            AND (SELECT count(*) FROM intake_photos WHERE intake_id=?)=? RETURNING id''',
            (identifier, identifier, len(json.loads(row['manifest'])))).fetchone())
        if not claimed and row['state'] == 'uploading':
            # A concurrent send may have won. Re-read before declaring missing uploads.
            row = self.row(identifier)
            if row['state'] == 'uploading':
                fail(409, 'Дождитесь загрузки всех фотографий.')
        return row, bool(claimed)

    def outcome(self, identifier, state, message_id=None):
        self.run(lambda db: db.execute("UPDATE intake SET state=?, message_id=? WHERE id=? AND state='sending'", (state, message_id, identifier)))


def receipt(row):
    return {'stored': row['state'] != 'uploading', 'delivered': row['state'] == 'sent'}


def telegram_text(row, store):
    a = json.loads(row['answers'])
    v = lambda key: a[key] or '—'
    gallery = f"{store.config.origin}/newcard/photos/{row['id']}#{store.token('gallery', row)}"
    text = '\n'.join([
        'НОВАЯ АНКЕТА · SCENA.LIVE', f"№ {row['id']}", '', f"{a['name']} · {a['specialty']}",
        f"Бренд: {v('brand')}", f"Город: {v('city')}", f"Контакт: {a['contact']}", '',
        f"Нужно: {', '.join(a['features'])}", f"Языки: {', '.join(a['languages'])}", f"Запись: {a['booking']}",
        f"Услуги и цены:\n{v('services')}", '', f"Стиль: {a['style']}", f"Примеры: {v('inspiration')}",
        f"О себе: {v('about')}", '', f"Домен: {a['domainStatus']} · {v('domain')}",
        f"GitHub: {a['github']}", f"Vercel: {a['vercel']}", f"Email для аккаунтов: {v('accountEmail')}",
        f"Сроки: {a['timing']}", f"Комментарий: {v('notes')}", '',
        f'Фотографии · закрытая ссылка на 30 дней:\n{gallery}' if json.loads(row['manifest']) else 'Фотографии: не приложены',
        'Согласие на передачу анкеты и материалов: получено.',
    ])
    if len(text.encode('utf-16-le')) // 2 > 4096:
        fail(400, 'Текст слишком длинный для Telegram. Сократите описание.')
    return text


class Telegram:
    def __init__(self, config):
        self.config = config
        self.checked_until = 0
        self.valid = False

    async def call(self, method, payload):
        # No URL, token, body or upstream exception is logged by this module.
        response = await AsyncHTTPClient().fetch(HTTPRequest(
            f'https://api.telegram.org/bot{self.config.bot}/{method}', method='POST',
            headers={'Content-Type': 'application/json'}, body=canonical(payload),
            connect_timeout=5, request_timeout=12, follow_redirects=False), raise_error=False)
        return json.loads(response.body)

    async def ready(self):
        if not self.config.configured():
            return False
        if time.monotonic() < self.checked_until:
            return self.valid
        try:
            me = await self.call('getMe', {})
            chat = await self.call('getChat', {'chat_id': self.config.chat})
            self.valid = bool(me.get('ok') and me.get('result', {}).get('username', '').lower() == 'scenalive_bot'
                              and chat.get('ok') and chat.get('result', {}).get('type') == 'private'
                              and str(chat.get('result', {}).get('id')) == self.config.chat)
        except Exception:
            self.valid = False
        self.checked_until = time.monotonic() + 60
        return self.valid

    async def send(self, text):
        try:
            result = await self.call('sendMessage', {'chat_id': self.config.chat, 'text': text,
                'protect_content': True, 'link_preview_options': {'is_disabled': True}})
        except Exception:
            return 'uncertain', None
        message = result.get('result', {})
        if result.get('ok') is True and type(message.get('message_id')) is int and str(message.get('chat', {}).get('id')) == self.config.chat:
            return 'sent', message['message_id']
        return ('failed' if result.get('ok') is False else 'uncertain'), None


@lru_cache(maxsize=1)
def services():
    config = Config.from_env()
    return Store(config), Telegram(config)


class IntakeHandler(RequestHandler):
    def initialize(self, service=None):
        self.store, self.telegram = service or services()

    def set_default_headers(self):
        self.set_header('Cache-Control', 'no-store')
        self.set_header('X-Content-Type-Options', 'nosniff')
        self.set_header('X-Robots-Tag', 'noindex, nofollow')
        self.set_header('Referrer-Policy', 'no-referrer')

    def write_error(self, status_code, **kwargs):
        # Never include exception strings from providers (which may contain credentials).
        error = kwargs.get('exc_info', (None, None, None))[1]
        message = error.reason if isinstance(error, HTTPError) and error.reason else 'Сервис временно недоступен. Ответы остались в форме.'
        self.finish({'error': message})

    def log_exception(self, typ, value, tb):
        if not isinstance(value, HTTPError):
            # Stable class only: no user payloads, private URLs or credentials.
            import logging
            logging.getLogger(__name__).error('Intake operation failed: %s', typ.__name__)

    def origin(self):
        if self.request.headers.get('Origin') != self.store.config.origin:
            fail(403, 'Отправьте анкету со страницы SCENA.LIVE.')

    def token(self):
        auth = self.request.headers.get('Authorization', '')
        token = auth.removeprefix('Bearer ')
        if not auth.startswith('Bearer ') or not re.fullmatch('[a-f0-9]{64}', token):
            fail(404, 'Ссылка недоступна.')
        return token

    def body(self):
        if len(self.request.body) > 32 * 1024 or self.request.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            fail(400, 'Некорректный формат анкеты.')
        try:
            return json.loads(self.request.body)
        except (ValueError, UnicodeError):
            fail(400, 'Некорректный формат анкеты.')


class IntakeStatus(IntakeHandler):
    async def get(self):
        self.finish({'ready': await self.telegram.ready()})


class IntakeStart(IntakeHandler):
    async def post(self):
        self.origin()
        if not await self.telegram.ready():
            fail(503, 'Приём заявок ещё не подключён.')
        payload = self.body()
        # Verify maximum Telegram size before reserving any storage.
        identifier, answers, manifest = validate(payload)
        telegram_text({'id': identifier, 'answers': canonical(answers), 'manifest': canonical(manifest), 'fingerprint': '0'*64}, self.store)
        # Vercel overwrites x-vercel-forwarded-for. Do not trust arbitrary X-Forwarded-For.
        ip = self.request.headers.get('X-Vercel-Forwarded-For', '').split(',')[0].strip() if os.getenv('VERCEL') else self.request.remote_ip
        if not ip:
            fail(503, 'Сервис временно недоступен.')
        result = await asyncio.to_thread(self.store.start, payload, ip)
        self.finish(result)


class IntakePhoto(IntakeHandler):
    async def put(self, identifier, position):
        self.origin()
        if len(self.request.body) > MAX_PHOTO:
            fail(413, 'Фотография должна быть до 4 МБ.')
        if not self.store.config.configured():
            fail(503, 'Приём временно приостановлен.')
        result = await asyncio.to_thread(self.store.put_photo, identifier, int(position), self.token(),
            self.request.body, self.request.headers.get('Content-Type', '').split(';')[0])
        self.finish(result)

    async def get(self, identifier, position):
        row = await asyncio.to_thread(self.store.authorize, identifier, self.token(), 'gallery')
        content, mime = await asyncio.to_thread(self.store.read_photo, row, int(position))
        self.set_header('Content-Type', mime)
        self.set_header('Content-Disposition', f'inline; filename="scena-{int(position)+1}.{MIMES[mime].lower()}"')
        self.finish(content)


class IntakeSend(IntakeHandler):
    async def post(self, identifier):
        self.origin()
        if not await self.telegram.ready():
            fail(503, 'Telegram пока недоступен. Повторите отправку позже.')
        row, claimed = await asyncio.to_thread(self.store.claim, identifier, self.token())
        if claimed:
            # Claim persists before the external side effect; retries cannot duplicate a message.
            state, message_id = await self.telegram.send(telegram_text(row, self.store))
            await asyncio.to_thread(self.store.outcome, identifier, state, message_id)
            self.finish({'stored': True, 'delivered': state == 'sent'})
        else:
            self.finish(receipt(row))


class IntakeGallery(IntakeHandler):
    async def get(self, identifier):
        row = await asyncio.to_thread(self.store.authorize, identifier, self.token(), 'gallery')
        self.finish({'id': identifier, 'count': len(json.loads(row['manifest']))})


def intake_routes(service=None):
    options = {'service': service}
    identifier = r'([a-f0-9-]{36})'
    return [
        (r'/api/intake/status', IntakeStatus, options),
        (r'/api/intake/start', IntakeStart, options),
        (rf'/api/intake/{identifier}/send', IntakeSend, options),
        (rf'/api/intake/{identifier}/photos/([0-5])', IntakePhoto, options),
        (rf'/api/intake/{identifier}/gallery', IntakeGallery, options),
    ]
