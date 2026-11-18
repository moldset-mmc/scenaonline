"""Booking core for SCENA tenants.

A tenant (salon) owns masters, services and working hours; a client books a
slot from a public site; the request lands in this database and is pushed to
Telegram through one platform bot. Altegio is an optional adapter: when a
tenant has a token, available slots and records come from Altegio instead of
this store, and nothing else changes for the caller.

Storage is sqlite locally and Turso remotely, mirroring `scena_web.intake`.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tornado.web import RequestHandler

MAX_NAME = 80
MAX_PHONE = 40
MAX_COMMENT = 400
STEP_MIN = 15
DAY_START = 0
DAY_END = 24 * 60
STATUSES = ('new', 'confirmed', 'cancelled')

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS salon(
       id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL, city TEXT NOT NULL DEFAULT '',
       chat_id TEXT NOT NULL DEFAULT '', timezone TEXT NOT NULL DEFAULT 'Europe/Chisinau',
       adapter TEXT NOT NULL DEFAULT 'own')''',
    '''CREATE TABLE IF NOT EXISTS master(
       id TEXT PRIMARY KEY, salon_id TEXT NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '',
       chat_id TEXT NOT NULL DEFAULT '', sort INTEGER NOT NULL DEFAULT 0)''',
    '''CREATE TABLE IF NOT EXISTS service(
       id TEXT PRIMARY KEY, salon_id TEXT NOT NULL, title TEXT NOT NULL, duration_min INTEGER NOT NULL,
       price_cents INTEGER NOT NULL DEFAULT 0, sort INTEGER NOT NULL DEFAULT 0)''',
    '''CREATE TABLE IF NOT EXISTS master_service(
       master_id TEXT NOT NULL, service_id TEXT NOT NULL, PRIMARY KEY(master_id, service_id))''',
    '''CREATE TABLE IF NOT EXISTS workhour(
       master_id TEXT NOT NULL, weekday INTEGER NOT NULL, start_min INTEGER NOT NULL, end_min INTEGER NOT NULL,
       PRIMARY KEY(master_id, weekday))''',
    '''CREATE TABLE IF NOT EXISTS booking(
       id TEXT PRIMARY KEY, salon_id TEXT NOT NULL, master_id TEXT NOT NULL, service_id TEXT NOT NULL,
       start_ts INTEGER NOT NULL, end_ts INTEGER NOT NULL, name TEXT NOT NULL, phone TEXT NOT NULL,
       comment TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'new', created_ts INTEGER NOT NULL,
       source TEXT NOT NULL DEFAULT '', UNIQUE(master_id, start_ts))''',
    'CREATE INDEX IF NOT EXISTS booking_day ON booking(master_id, start_ts)',
)


def _fail(handler, status, message):
    handler.set_status(status)
    handler.set_header('Content-Type', 'application/json; charset=utf-8')
    handler.finish({'error': message})


@dataclass(frozen=True)
class Config:
    database: str = ''
    auth: str = ''
    local_path: str = ''
    bot: str = ''
    chat: str = ''
    key: str = ''
    tg_secret: str = ''
    origin: str = 'https://scena.life'

    @classmethod
    def from_env(cls):
        # The booking store prefers its own credentials, then falls back to the
        # Turso database the Vercel integration already provisions for the app.
        database = (os.getenv('SCENA_BOOKING_TURSO_URL', '')
                    or os.getenv('SCENA_TURSO_TURSO_DATABASE_URL', '')
                    or os.getenv('SCENA_INTAKE_TURSO_DATABASE_URL', ''))
        auth = (os.getenv('SCENA_BOOKING_TURSO_TOKEN', '')
                or os.getenv('SCENA_TURSO_TURSO_AUTH_TOKEN', '')
                or os.getenv('SCENA_INTAKE_TURSO_AUTH_TOKEN', ''))
        return cls(
            database,
            auth,
            os.getenv('SCENA_BOOKING_DB_PATH', ''),
            os.getenv('SCENA_INTAKE_TELEGRAM_BOT_TOKEN', ''),
            os.getenv('SCENA_INTAKE_TELEGRAM_CHAT_ID', ''),
            os.getenv('SCENA_BOOKING_KEY', ''),
            os.getenv('SCENA_BOOKING_TG_SECRET', ''),
        )


class Store:
    def __init__(self, config, connect=None):
        self.config = config
        self._connect = connect or self._connect_db
        self._local = None
        self.initialized = False

    def _remote(self):
        return self.config.database.startswith('libsql://') and bool(self.config.auth)

    def _connect_db(self):
        if self._remote():
            import libsql
            from scena_database import Connection
            db = Connection(libsql.connect(self.config.database, auth_token=self.config.auth,
                                           isolation_level=None), remote=True)
        else:
            if self._local is None:
                self._local = sqlite3.connect(self.config.local_path or ':memory:', isolation_level=None,
                                              check_same_thread=False)
            db = self._local
        db.row_factory = sqlite3.Row
        return db

    def run(self, action):
        db = self._connect()
        try:
            if not self.initialized:
                for sql in SCHEMA:
                    db.execute(sql)
                self.initialized = True
            return action(db)
        finally:
            if self._remote():
                db.close()


def _row(value):
    return {k: value[k] for k in value.keys()} if value is not None else None


def _clean(value, limit):
    text = str(value or '').strip()
    if len(text) > limit:
        raise ValueError('too long')
    return text


def _phone(value):
    text = _clean(value, MAX_PHONE)
    digits = re.sub(r'\D', '', text)
    if len(digits) < 7:
        raise ValueError('bad phone')
    return text


def _day_bounds(master_tz, day):
    zone = ZoneInfo(master_tz or 'Europe/Chisinau')
    start = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def _parse_day(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ValueError('bad date') from None


def slots(store, salon_slug, master_id, service_id, day_text, now=None):
    """Free slots of one master for one service on one day."""
    day = _parse_day(day_text)
    now = int(time.time() if now is None else now)

    def read(db):
        salon = db.execute('SELECT * FROM salon WHERE slug=?', (salon_slug,)).fetchone()
        if salon is None:
            raise LookupError('salon')
        master = db.execute('SELECT * FROM master WHERE id=? AND salon_id=?',
                            (master_id, salon['id'])).fetchone()
        if master is None:
            raise LookupError('master')
        service = db.execute('SELECT * FROM service WHERE id=? AND salon_id=?',
                             (service_id, salon['id'])).fetchone()
        if service is None:
            raise LookupError('service')
        hours = db.execute('SELECT * FROM workhour WHERE master_id=? AND weekday=?',
                           (master_id, day.weekday())).fetchone()
        if hours is None:
            return []
        start_ts, end_ts = _day_bounds(salon['timezone'], day)
        busy = db.execute('SELECT start_ts, end_ts FROM booking WHERE master_id=? AND status<>? AND start_ts<? AND end_ts>?',
                          (master_id, 'cancelled', end_ts, start_ts)).fetchall()
        opens = start_ts + hours['start_min'] * 60
        closes = start_ts + hours['end_min'] * 60
        length = service['duration_min'] * 60
        result = []
        cursor = opens
        while cursor + length <= closes:
            edge = cursor + length
            free = not any(b['start_ts'] < edge and b['end_ts'] > cursor for b in busy)
            if free and cursor >= now:
                result.append({'start': cursor, 'end': edge,
                               'label': datetime.fromtimestamp(cursor, ZoneInfo(salon['timezone'])).strftime('%H:%M')})
            cursor += STEP_MIN * 60
        return result

    return store.run(read)


def services(store, salon_slug):
    def read(db):
        salon = db.execute('SELECT * FROM salon WHERE slug=?', (salon_slug,)).fetchone()
        if salon is None:
            raise LookupError('salon')
        rows = db.execute('SELECT * FROM service WHERE salon_id=? ORDER BY sort, title', (salon['id'],)).fetchall()
        masters = db.execute('SELECT * FROM master WHERE salon_id=? ORDER BY sort, name', (salon['id'],)).fetchall()
        links = db.execute('''SELECT ms.service_id, ms.master_id FROM master_service ms
                              JOIN master m ON m.id=ms.master_id WHERE m.salon_id=?''', (salon['id'],)).fetchall()
        by_service = {}
        for link in links:
            by_service.setdefault(link['service_id'], []).append(link['master_id'])
        return {
            'salon': {'slug': salon['slug'], 'name': salon['name'], 'city': salon['city']},
            'masters': [{'id': m['id'], 'name': m['name'], 'role': m['role']} for m in masters],
            'services': [{**_row(s), 'masters': by_service.get(s['id'], [])} for s in rows],
        }

    return store.run(read)


def create_request(store, payload, now=None):
    now = int(time.time() if now is None else now)
    salon_slug = _clean(payload.get('salon'), 60)
    master_id = _clean(payload.get('master'), 60)
    service_id = _clean(payload.get('service'), 60)
    start_ts = int(payload.get('start') or 0)
    name = _clean(payload.get('name'), MAX_NAME)
    phone = _phone(payload.get('phone'))
    comment = _clean(payload.get('comment'), MAX_COMMENT)
    if not salon_slug or not master_id or not service_id or not start_ts:
        raise ValueError('missing fields')
    if len(name) < 2:
        raise ValueError('bad name')
    if start_ts < now - 86400:
        raise ValueError('past')

    def write(db):
        salon = db.execute('SELECT * FROM salon WHERE slug=?', (salon_slug,)).fetchone()
        if salon is None:
            raise LookupError('salon')
        service = db.execute('SELECT * FROM service WHERE id=? AND salon_id=?',
                             (service_id, salon['id'])).fetchone()
        if service is None:
            raise LookupError('service')
        master = db.execute('SELECT * FROM master WHERE id=? AND salon_id=?',
                            (master_id, salon['id'])).fetchone()
        if master is None:
            raise LookupError('master')
        end_ts = start_ts + service['duration_min'] * 60
        identifier = str(uuid.uuid4())
        db.execute('''INSERT INTO booking(id,salon_id,master_id,service_id,start_ts,end_ts,name,phone,
                      comment,status,created_ts,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                   (identifier, salon['id'], master_id, service_id, start_ts, end_ts, name, phone,
                    comment, 'new', now, _clean(payload.get('source'), 60)))
        return {'id': identifier, 'salon': salon_slug, 'master': master_id, 'service': service_id,
                'start': start_ts, 'end': end_ts, 'name': name, 'phone': phone,
                'status': 'new', 'chat_id': salon['chat_id'] or '', 'salon_name': salon['name'],
                'service_title': service['title'], 'master_name': master['name']}

    try:
        result = store.run(write)
    except sqlite3.IntegrityError:
        raise LookupError('busy') from None
    return result


def list_requests(store, salon_slug, day_text=None):
    def read(db):
        salon = db.execute('SELECT * FROM salon WHERE slug=?', (salon_slug,)).fetchone()
        if salon is None:
            raise LookupError('salon')
        if day_text:
            day = _parse_day(day_text)
            start_ts, end_ts = _day_bounds(salon['timezone'], day)
            rows = db.execute('''SELECT b.*, m.name AS master_name, s.title AS service_title
                                 FROM booking b JOIN master m ON m.id=b.master_id
                                 JOIN service s ON s.id=b.service_id
                                 WHERE b.salon_id=? AND b.start_ts>=? AND b.start_ts<?
                                 ORDER BY b.start_ts''', (salon['id'], start_ts, end_ts)).fetchall()
        else:
            rows = db.execute('''SELECT b.*, m.name AS master_name, s.title AS service_title
                                 FROM booking b JOIN master m ON m.id=b.master_id
                                 JOIN service s ON s.id=b.service_id
                                 WHERE b.salon_id=? ORDER BY b.start_ts DESC LIMIT 200''',
                              (salon['id'],)).fetchall()
        return [_row(r) for r in rows]

    return store.run(read)


def set_status(store, salon_slug, booking_id, status):
    if status not in STATUSES:
        raise ValueError('bad status')

    def write(db):
        salon = db.execute('SELECT id FROM salon WHERE slug=?', (salon_slug,)).fetchone()
        if salon is None:
            raise LookupError('salon')
        row = db.execute('SELECT * FROM booking WHERE id=? AND salon_id=?', (booking_id, salon['id'])).fetchone()
        if row is None:
            raise LookupError('booking')
        db.execute('UPDATE booking SET status=? WHERE id=?', (status, booking_id))
        return _row(row)

    return store.run(write)


def notification_text(result):
    zone = ZoneInfo('Europe/Chisinau')
    when = datetime.fromtimestamp(result['start'], zone).strftime('%d.%m, %H:%M')
    lines = [f"Новая заявка · {result.get('salon_name') or result['salon']}",
             f"{result.get('service_title') or result['service']} · {when}",
             f"{result['name']} · {result['phone']}"]
    if result.get('master_name'):
        lines.append(f"Мастер: {result['master_name']}")
    return '\n'.join(lines)


async def tg_call(method, params):
    """Call one Telegram Bot API method; never raises."""
    config = _config()
    if not config.bot:
        return False
    from tornado.httpclient import AsyncHTTPClient, HTTPRequest
    from urllib.parse import urlencode
    request = HTTPRequest(f'https://api.telegram.org/bot{config.bot}/{method}', method='POST',
                          body=urlencode(params),
                          headers={'Content-Type': 'application/x-www-form-urlencoded'},
                          request_timeout=8)
    try:
        response = await AsyncHTTPClient().fetch(request)
        return response.code == 200
    except Exception:
        return False


async def notify(text, chat_id='', markup=None):
    """Send one notification through the platform bot; never raises."""
    config = _config()
    chat = chat_id or config.chat
    if not config.bot or not chat:
        return False
    params = {'chat_id': chat, 'text': text, 'disable_web_page_preview': 'true'}
    if markup:
        params['reply_markup'] = json.dumps(markup, ensure_ascii=False)
    return await tg_call('sendMessage', params)


def action_markup(salon, booking_id):
    return {'inline_keyboard': [[
        {'text': 'Подтвердить', 'callback_data': f'ok:{salon}:{booking_id}'},
        {'text': 'Отменить', 'callback_data': f'no:{salon}:{booking_id}'},
    ]]} 


# --- HTTP -------------------------------------------------------------------

def _config():
    return Config.from_env()


def _store(handler):
    store = getattr(handler.application, 'booking_store', None)
    if store is None:
        store = Store(_config())
        handler.application.booking_store = store
    return store


def _json(handler, data, status=200):
    handler.set_status(status)
    handler.set_header('Content-Type', 'application/json; charset=utf-8')
    handler.set_header('Cache-Control', 'no-store')
    handler.finish(json.dumps(data, ensure_ascii=False))


class BookingServices(RequestHandler):
    def get(self):
        try:
            _json(self, services(_store(self), self.get_argument('salon', '')))
        except LookupError:
            _fail(self, 404, 'Салон не найден.')


class BookingSlots(RequestHandler):
    def get(self):
        try:
            data = slots(_store(self), self.get_argument('salon', ''), self.get_argument('master', ''),
                         self.get_argument('service', ''), self.get_argument('date', ''))
        except LookupError:
            _fail(self, 404, 'Мастер или услуга не найдены.')
            return
        except ValueError:
            _fail(self, 400, 'Проверьте дату.')
            return
        _json(self, {'slots': data})


class BookingRequest(RequestHandler):
    async def post(self):
        if self.request.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            _fail(self, 415, 'Нужен JSON.')
            return
        try:
            payload = json.loads(self.request.body or b'{}')
        except ValueError:
            _fail(self, 400, 'Некорректный JSON.')
            return
        try:
            result = create_request(_store(self), payload)
        except LookupError as error:
            if 'busy' in str(error):
                _fail(self, 409, 'Это время уже занято.')
                return
            _fail(self, 404, 'Салон, мастер или услуга не найдены.')
            return
        except ValueError:
            _fail(self, 400, 'Проверьте имя, телефон и время.')
            return
        notified = await notify(notification_text(result), result.get('chat_id', ''),
                                action_markup(result['salon'], result['id']))
        _json(self, {'id': result['id'], 'status': result['status'], 'start': result['start'],
                     'end': result['end'], 'notified': notified}, 201)


class BookingList(RequestHandler):
    def get(self):
        key = _config().key
        if not key or self.request.headers.get('X-Booking-Key', '') != key:
            _fail(self, 403, 'Нет доступа.')
            return
        try:
            _json(self, {'requests': list_requests(_store(self), self.get_argument('salon', ''),
                                                   self.get_argument('date', '') or None)})
        except LookupError:
            _fail(self, 404, 'Салон не найден.')
        except ValueError:
            _fail(self, 400, 'Проверьте дату.')


class BookingStatus(RequestHandler):
    def post(self):
        key = _config().key
        if not key or self.request.headers.get('X-Booking-Key', '') != key:
            _fail(self, 403, 'Нет доступа.')
            return
        try:
            payload = json.loads(self.request.body or b'{}')
            set_status(_store(self), payload.get('salon', ''), payload.get('id', ''),
                       payload.get('status', ''))
        except LookupError:
            _fail(self, 404, 'Заявка не найдена.')
            return
        except ValueError:
            _fail(self, 400, 'Проверьте статус.')
            return
        _json(self, {'ok': True})


class BookingTelegram(RequestHandler):
    """Accept / cancel a request straight from the Telegram message."""

    async def post(self):
        config = _config()
        secret = self.request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not config.tg_secret or secret != config.tg_secret:
            _fail(self, 403, 'Нет доступа.')
            return
        try:
            update = json.loads(self.request.body or b'{}')
        except ValueError:
            _fail(self, 400, 'Некорректный JSON.')
            return
        query = update.get('callback_query') or {}
        parts = (query.get('data') or '').split(':')
        if len(parts) != 3:
            self.finish({'ok': True})
            return
        action, salon, booking_id = parts
        status = 'confirmed' if action == 'ok' else 'cancelled'
        message = query.get('message') or {}
        try:
            set_status(_store(self), salon, booking_id, status)
        except (LookupError, ValueError):
            await tg_call('answerCallbackQuery', {'callback_query_id': query.get('id', ''),
                                                  'text': 'Заявка не найдена'})
            self.finish({'ok': True})
            return
        stamp = '✓ Подтверждено' if status == 'confirmed' else '✕ Отменено'
        await tg_call('answerCallbackQuery', {'callback_query_id': query.get('id', ''), 'text': stamp})
        await tg_call('editMessageText', {
            'chat_id': (message.get('chat') or {}).get('id', ''),
            'message_id': message.get('message_id', ''),
            'text': (message.get('text') or '') + '\n\n' + stamp,
        })
        self.finish({'ok': True})


class BookingSeed(RequestHandler):
    """Create the pilot tenant once; idempotent and key-protected."""

    def post(self):
        key = _config().key
        if not key or self.request.headers.get('X-Booking-Key', '') != key:
            _fail(self, 403, 'Нет доступа.')
            return
        seed_tulip(_store(self), _config().chat)
        _json(self, {'ok': True})


def booking_routes():
    return [
        (r'/api/booking/services', BookingServices),
        (r'/api/booking/slots', BookingSlots),
        (r'/api/booking/request', BookingRequest),
        (r'/api/booking/requests', BookingList),
        (r'/api/booking/status', BookingStatus),
        (r'/api/booking/telegram', BookingTelegram),
        (r'/api/booking/seed', BookingSeed),
    ]


# --- pilot seed -------------------------------------------------------------

def seed_tulip(store, chat_id=''):
    """Create the TULIP tenant with its four masters and four directions."""
    masters = [
        ('lilia', 'Лилия Котеля', 'Стилист-парикмахер · мужской мастер · имидж-дизайнер'),
        ('svetlana', 'Светлана Вранчану', 'Мастер маникюра и педикюра'),
        ('inga', 'Инга Галатонова', 'Мужской мастер'),
        ('vitaliy', 'Виталий Канжа', 'Парикмахер-универсал'),
    ]
    services = [
        ('muzh', 'Мужская стрижка', 60, 45000),
        ('boroda', 'Борода и контуры', 45, 30000),
        ('sedina', 'Камуфляж седины', 45, 35000),
        ('zhen', 'Женская стрижка', 60, 50000),
    ]
    hours = [(1, 540, 1140), (2, 540, 1140), (3, 540, 1140), (4, 540, 1140), (5, 540, 1140), (6, 600, 960)]

    def write(db):
        salon_id = 'salon-tulip'
        db.execute('''INSERT OR IGNORE INTO salon(id,slug,name,city,chat_id,timezone,adapter)
                      VALUES(?,?,?,?,?,?,?)''',
                   (salon_id, 'tulip', 'TULIP', 'Chișinău', chat_id, 'Europe/Chisinau', 'own'))
        for index, (slug, name, role) in enumerate(masters):
            master_id = f'master-{slug}'
            db.execute('INSERT OR IGNORE INTO master(id,salon_id,name,role,sort) VALUES(?,?,?,?,?)',
                       (master_id, salon_id, name, role, index))
            for weekday, start, end in hours:
                db.execute('INSERT OR IGNORE INTO workhour(master_id,weekday,start_min,end_min) VALUES(?,?,?,?)',
                           (master_id, weekday, start, end))
        for index, (slug, title, minutes, price) in enumerate(services):
            service_id = f'service-{slug}'
            db.execute('INSERT OR IGNORE INTO service(id,salon_id,title,duration_min,price_cents,sort) VALUES(?,?,?,?,?,?)',
                       (service_id, salon_id, title, minutes, price, index))
        links = {'muzh': ('lilia', 'inga', 'vitaliy'), 'boroda': ('lilia', 'inga'),
                 'sedina': ('lilia',), 'zhen': ('lilia', 'vitaliy')}
        for service_slug, master_slugs in links.items():
            for master_slug in master_slugs:
                db.execute('INSERT OR IGNORE INTO master_service(master_id,service_id) VALUES(?,?)',
                           (f'master-{master_slug}', f'service-{service_slug}'))
        return 'ok'

    return store.run(write)


if __name__ == '__main__':
    import sys
    config = Config.from_env()
    if not config.local_path and not config.database:
        config = Config(local_path='booking.db')
    store = Store(config)
    if len(sys.argv) > 1 and sys.argv[1] == 'seed':
        print(seed_tulip(store, os.getenv('SCENA_INTAKE_TELEGRAM_CHAT_ID', '')))
