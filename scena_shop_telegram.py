"""Owner-bound Telegram order leads. Orders commit before network delivery.

Credentials are encrypted separately from portable owner data. A fresh code
binds the bot only to the private Telegram username saved in the owner's profile.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
from urllib.parse import urlsplit

from scena_database import connect
from scena_integrations import TelegramBotAdapter
from scena_telegram_setup import _TOKEN_PATTERN


class ConnectionError(ValueError):
    pass


def initialize(con):
    con.execute('''CREATE TABLE IF NOT EXISTS shop_telegram_connection (
        id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)''')
    columns = {row[1] for row in con.execute('PRAGMA table_info(shop_orders)')}
    # Existing orders must not suddenly generate historical notifications.
    for name, definition in {
        'telegram_status': "TEXT NOT NULL DEFAULT 'skipped'",
        'telegram_attempts': 'INTEGER NOT NULL DEFAULT 0',
        'telegram_retry_at': 'REAL NOT NULL DEFAULT 0',
        'telegram_message_id': "TEXT NOT NULL DEFAULT ''",
    }.items():
        if name not in columns:
            con.execute(f'ALTER TABLE shop_orders ADD COLUMN {name} {definition}')


def _cipher():
    from cryptography.fernet import Fernet
    key = os.environ.get('SCENA_TELEGRAM_CREDENTIAL_KEY') or os.environ.get('SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN')
    if not key:
        raise ConnectionError('Для подключения Telegram нужен ключ защищённого хранилища сайта.')
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(('scena-shop-telegram-v1\0'+key).encode()).digest()))


def _load(db):
    with connect(db) as con:
        row = con.execute('SELECT payload FROM shop_telegram_connection WHERE id=1').fetchone()
    if not row:
        return {}
    try:
        return json.loads(_cipher().decrypt(row[0].encode()))
    except Exception:
        raise ConnectionError('Подключите Telegram снова: сохранённое подключение недоступно.') from None


def _save(db, value):
    payload = _cipher().encrypt(json.dumps(value).encode()).decode()
    with connect(db) as con:
        con.execute('INSERT INTO shop_telegram_connection(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (payload,))


def owner_username(db):
    with connect(db) as con:
        row = con.execute("SELECT value FROM profile_settings WHERE key='telegram_url'").fetchone()
    value = (row[0] if row else '').strip()
    if value.startswith(('https://', 'http://', 't.me/')):
        parsed = urlsplit(value if '://' in value else 'https://'+value)
        value = parsed.path.strip('/') if parsed.hostname in ('t.me', 'telegram.me') and not parsed.query and not parsed.fragment else ''
    value = value.lstrip('@')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', value):
        raise ConnectionError('Сначала укажите ваш личный Telegram в «Моя сцена», например @username.')
    return value.lower()


def _adapter(config):
    return TelegramBotAdapter(bot_token=config['token'], admin_chat_id=config.get('chat_id') or '1', timeout=4)


def begin_connection(db, token, *, now=None):
    token = str(token or os.environ.get('SCENA_TELEGRAM_BOT_TOKEN', '')).strip()
    if not _TOKEN_PATTERN.fullmatch(token):
        raise ConnectionError('Вставьте полный токен вашего бота из @BotFather.')
    username = owner_username(db)
    _cipher()  # Verify durable storage before contacting Telegram.
    try:
        bot = _adapter({'token':token})._call('getMe', {})
        if not isinstance(bot, dict) or not bot.get('is_bot') or not bot.get('username'):
            raise ValueError()
    except Exception:
        raise ConnectionError('Не удалось проверить бота. Проверьте токен и повторите попытку.') from None
    try:
        config = _load(db)
    except ConnectionError:
        config = {}  # A newly verified bot can replace an unreadable connection.
    config['pending'] = {'token':token, 'username':username, 'bot':bot['username'],
        'code':'SCENA CONNECT '+secrets.token_hex(10).upper(), 'started':time.time() if now is None else now}
    _save(db, config)
    return connection_status(db)


def confirm_connection(db, *, now=None):
    config = _load(db)
    pending = config.get('pending', {})
    now = time.time() if now is None else now
    if not pending or now-pending['started'] > 600:
        raise ConnectionError('Код действует 10 минут. Создайте новый код подключения.')
    if pending['username'] != owner_username(db):
        raise ConnectionError('Telegram в профиле изменился. Создайте новый код подключения.')
    try:
        updates = _adapter(pending)._call('getUpdates', {'limit':100, 'timeout':0})
        candidates = set()
        for update in updates if isinstance(updates, list) else []:
            message = update.get('message', {})
            chat, sender = message.get('chat', {}), message.get('from', {})
            chat_id = str(chat.get('id', ''))
            if (message.get('text', '').strip() == pending['code'] and chat.get('type') == 'private'
                and re.fullmatch(r'[1-9][0-9]{0,19}', chat_id) and str(sender.get('id')) == chat_id
                and sender.get('is_bot') is False and not message.get('forward_origin')
                and str(chat.get('username', '')).lower() == pending['username']
                and pending['started']-5 <= float(message.get('date', 0)) <= now+60):
                candidates.add(chat_id)
    except Exception:
        raise ConnectionError('Не удалось прочитать код. Повторите попытку; используйте отдельного бота SCENA без другого сервиса.') from None
    if len(candidates) != 1:
        raise ConnectionError('Свежий код не найден в личном чате @'+pending['username']+'. Отправьте код указанному боту и нажмите ещё раз.')
    _save(db, {key:pending[key] for key in ('token','username','bot')} | {'chat_id':candidates.pop()})
    return connection_status(db)


def connection_status(db):
    config = _load(db)
    try:
        matches = config.get('username') == owner_username(db)
    except ConnectionError:
        matches = False
    pending = config.get('pending', {})
    return {'connected':bool(config.get('chat_id') and matches), 'username':config.get('username', ''),
        'pending':{key:pending[key] for key in ('code','bot','username','started') if key in pending}}


def lead_text(order):
    from scena_shop import money
    lines = ['SCENA · новый заказ '+order['reference'], '',
        'Покупатель: '+order['customer_name'], 'Телефон: '+order['phone']]
    for key, label in (('telegram','Telegram'), ('email','Email')):
        if order[key]:
            lines.append(label+': '+order[key])
    lines += ['Способ связи: '+{'phone':'телефон','email':'email','telegram':'Telegram'}[order['preferred_contact']], '', 'Товары:']
    for item in order['items']:
        lines.append(f"• {item['name_ru'][:80]} · {item['quantity']} × {money(item['unit_price_cents'])}")
    lines += ['', 'Итого: '+money(order['total_cents']), 'Оплата и получение согласовываются лично.']
    if order['note']:
        lines += ['', 'Комментарий: '+order['note'][:700]]
    return '\n'.join(lines).encode('utf-16-le')[:7800].decode('utf-16-le', errors='ignore')


def dispatch(db, *, order_id=None, now=None, adapter=None):
    """Claim one durable lead; never roll back a committed customer order.

Retry pending leads through the owner's explicit Retry action.
Telegram has no idempotency key: an ambiguous transport timeout can produce a
duplicate message on retry; the stable order reference identifies the same lead.
"""
    from scena_shop import _connect, _order
    now = time.time() if now is None else now
    try:
        if adapter is None:
            config = _load(db)
            if not config.get('chat_id') or config.get('username') != owner_username(db):
                return 'unconfigured'
            adapter = _adapter(config)
        if not adapter.configured:
            return 'unconfigured'
        with _connect(db) as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute("SELECT id FROM shop_orders WHERE telegram_status IN ('queued','retry','sending') AND telegram_retry_at<=?" + (' AND id=?' if order_id else '') + ' ORDER BY created_at,id LIMIT 1', (now,order_id) if order_id else (now,)).fetchone()
            if not row:
                return 'idle'
            target = row[0]
            con.execute("UPDATE shop_orders SET telegram_status='sending',telegram_attempts=telegram_attempts+1,telegram_retry_at=? WHERE id=?", (now+60,target))
            order = _order(con, target)
        try:
            result = adapter._call('sendMessage', {'chat_id':adapter.admin_chat_id, 'text':lead_text(order), 'link_preview_options':{'is_disabled':True}})
            if not isinstance(result, dict) or result.get('message_id') is None:
                raise ValueError()
        except Exception:
            with _connect(db) as con:
                con.execute("UPDATE shop_orders SET telegram_status='retry',telegram_retry_at=? WHERE id=?", (now+min(3600,30*2**min(order['telegram_attempts'],6)),target))
            return 'retry'
        with _connect(db) as con:
            con.execute("UPDATE shop_orders SET telegram_status='sent',telegram_message_id=?,telegram_retry_at=0 WHERE id=?", (str(result['message_id']),target))
        return 'sent'
    except Exception:
        # No provider response or secret enters the page, logs or order receipt.
        return 'retry'


def render_settings(db, locale):
    from scena_ui import st
    st.subheader('Telegram · '+{'ru':'уведомления о заказах','ro':'notificări despre comenzi','en':'order notifications'}[locale])
    try:
        try:
            status = connection_status(db)
        except ConnectionError as error:
            st.warning(str(error))
            status = {'connected':False,'pending':{}}
        if status['connected']:
            st.success('Заказы отправляются в Telegram @'+status['username'])
        else:
            st.info('Подключите личный Telegram, указанный в «Моя сцена», чтобы получать заказы из маркета.')
        st.caption('Создайте отдельного бота через @BotFather → /newbot. Токен вставьте только сюда. Затем отправьте боту код из этого окна.')
        with st.form('shop_telegram_connect'):
            token = st.text_input('Токен бота из @BotFather', type='password', max_chars=230)
            if st.form_submit_button('Получить код подключения'):
                begin_connection(db, token)
                # Do not retain a credential in the rendered form or its state.
                if os.environ.get('SCENA_NATIVE_WEB') == '1':
                    from scena_web.context import current
                    ctx = current.get()
                    for identity,w in ctx.widgets.items():
                        if w.get('group') == 'shop_telegram_connect' and w.get('kind') == 'text':
                            ctx.state.get('_web_values', {}).pop(identity, None)
                st.rerun()
        if status['pending']:
            pending = status['pending']
            st.link_button('Открыть @'+pending['bot'], 'https://t.me/'+pending['bot'])
            st.write('Отправьте из @'+pending['username']+' это сообщение боту:')
            st.code(pending['code'])
            if st.button('Код отправлен — подключить Telegram'):
                confirm_connection(db)
                st.rerun()
        if status['connected'] and st.button('Повторить отправку ожидающего заказа'):
            result = dispatch(db)
            st.success('Уведомление отправлено.' if result == 'sent' else 'Нет заказов, готовых к повторной отправке.') if result in ('sent','idle') else st.warning('Telegram пока недоступен. Заказ остаётся в очереди.')
    except ConnectionError as error:
        st.warning(str(error))
