"""Owner-bound Telegram order leads. Orders commit before network delivery.

Credentials are encrypted separately from portable owner data. A fresh code
binds the bot only to the private Telegram username saved in the owner's profile.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from urllib.parse import urlsplit, urlencode
from uuid import UUID

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


def _amend_connection(db, before, changes):
    """Merge registration results without overwriting a refreshed binding."""
    with connect(db) as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT payload FROM shop_telegram_connection WHERE id=1').fetchone()
        latest = json.loads(_cipher().decrypt(row[0].encode())) if row else {}
        keys = ('token','username','chat_id','action_secret','webhook_secret')
        if any(latest.get(key) != before.get(key) for key in keys):
            raise ConnectionError('Подключение изменилось. Обновите страницу и повторите включение кнопок.')
        latest.update(changes)
        payload = _cipher().encrypt(json.dumps(latest).encode()).decode()
        con.execute('UPDATE shop_telegram_connection SET payload=? WHERE id=1', (payload,))
        return latest


def public_origin(db):
    """Use configured public identity, never the incoming Host header."""
    origin = os.environ.get('SCENA_PUBLIC_BASE_URL', '')
    if not origin and os.environ.get('VERCEL_PROJECT_PRODUCTION_URL'):
        origin = 'https://' + os.environ['VERCEL_PROJECT_PRODUCTION_URL']
    if not origin:
        with connect(db) as con:
            row = con.execute("SELECT value FROM profile_settings WHERE key='public_base_url'").fetchone()
        origin = row[0] if row else ''
    try:
        parsed = urlsplit(origin)
        if (parsed.scheme == 'https' and parsed.hostname and '.' in parsed.hostname
            and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
            and parsed.path in ('', '/') and parsed.port in (None, 443)):
            return 'https://' + parsed.hostname
    except ValueError:
        pass
    return ''


def order_path(order_id, locale='ru'):
    return '/?' + urlencode({'page':'admin', 'lang':locale if locale in ('ru','ro','en') else 'ru',
        'section':'pages', 'view':'shop', 'order':str(UUID(str(order_id)))})


def enable_actions(db):
    """Owner POST only. Do not replace another service's webhook."""
    config = _load(db)
    if not config.get('chat_id') or config.get('username') != owner_username(db):
        raise ConnectionError('Сначала подтвердите подключение личного Telegram.')
    origin = public_origin(db)
    if not origin or os.environ.get('SCENA_NATIVE_WEB') != '1':
        raise ConnectionError('Для кнопок нужен опубликованный сайт SCENA с HTTPS.')
    url = origin + '/scena-telegram'
    adapter = _adapter(config)
    try:
        info = adapter._call('getWebhookInfo', {})
        if not isinstance(info, dict):
            raise ValueError()
        if info.get('url') and (info['url'] != url or config.get('webhook_url') != url):
            raise ConnectionError('Этот бот подключён к другому сервису. Используйте отдельного бота для SCENA.')
        # Persist before registration: Telegram can deliver immediately. Keep
        # the same secrets when retrying an ambiguous registration timeout.
        config = _amend_connection(db, config, {
            'webhook_secret':config.get('webhook_secret') or secrets.token_urlsafe(32),
            'action_secret':config.get('action_secret') or secrets.token_hex(32),
            'webhook_url':url, 'webhook_ready':False})
        result = adapter._call('setWebhook', {'url':url, 'secret_token':config['webhook_secret'],
            'allowed_updates':['message','callback_query'], 'drop_pending_updates':False})
        if result is not True:
            raise ValueError()
        # Readback proves that Telegram accepted this endpoint, without
        # exposing its secret or the bot token to the browser.
        info = adapter._call('getWebhookInfo', {})
        if not isinstance(info, dict) or info.get('url') != url:
            raise ValueError()
        _amend_connection(db, config, {'webhook_ready':True})
    except ConnectionError:
        raise
    except Exception:
        raise ConnectionError('Не удалось включить кнопки Telegram. Заказы сохранены; повторите включение.') from None


def _binding_candidate(pending, message, now):
    chat, sender = message.get('chat', {}), message.get('from', {})
    chat_id = str(chat.get('id', ''))
    if (message.get('text', '').strip() == pending['code'] and chat.get('type') == 'private'
        and re.fullmatch(r'[1-9][0-9]{0,19}', chat_id) and str(sender.get('id')) == chat_id
        and sender.get('is_bot') is False and not message.get('forward_origin')
        and str(chat.get('username', '')).lower() == pending['username']
        and pending['started']-5 <= float(message.get('date', 0)) <= now+60
        and now-pending['started'] <= 600):
        return chat_id
    return None


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
        hooked = config.get('webhook_url') and config.get('token') == pending['token']
        updates = [] if hooked else _adapter(pending)._call('getUpdates', {'limit':100, 'timeout':0})
        candidates = set()
        if hooked and pending.get('verified_chat_id'):
            candidates.add(pending['verified_chat_id'])
        for update in updates if isinstance(updates, list) else []:
            if chat_id := _binding_candidate(pending, update.get('message', {}), now):
                candidates.add(chat_id)
    except Exception:
        raise ConnectionError('Не удалось прочитать код. Повторите попытку; используйте отдельного бота SCENA без другого сервиса.') from None
    if len(candidates) != 1:
        raise ConnectionError('Свежий код не найден в личном чате @'+pending['username']+'. Отправьте код указанному боту и нажмите ещё раз.')
    active = {key:pending[key] for key in ('token','username','bot')} | {'chat_id':candidates.pop()}
    if config.get('token') == pending['token']:
        active.update({key:config[key] for key in ('webhook_url','webhook_secret','webhook_ready') if key in config})
    active['action_secret'] = secrets.token_hex(32)  # Rebinding revokes old action buttons.
    _save(db, active)
    return connection_status(db)


def refresh_code(db, *, now=None):
    config = _load(db)
    pending = config.get('pending', {})
    if not pending or pending['username'] != owner_username(db):
        raise ConnectionError('Telegram в профиле изменился. Подключите бота для нового аккаунта.')
    pending.update(code='SCENA CONNECT '+secrets.token_hex(10).upper(), started=time.time() if now is None else now)
    pending.pop('verified_chat_id', None)
    _save(db, config)


def connection_status(db):
    config = _load(db)
    try:
        matches = config.get('username') == owner_username(db)
    except ConnectionError:
        matches = False
    pending = config.get('pending', {})
    return {'connected':bool(config.get('chat_id') and matches), 'username':config.get('username', ''),
        'actions_ready':bool(matches and config.get('webhook_ready')),
        'pending':{key:pending[key] for key in ('code','bot','username','started') if key in pending}}


def lead_text(order):
    from scena_shop import money, dial_number, _t
    lines = ['SCENA · заказ '+order['reference'], 'Статус: '+_t(order['status'], 'ru'), '',
        'Покупатель: '+order['customer_name'], 'Телефон: '+(dial_number(order['phone']) or order['phone'])]
    # Keep the number as plain text: Telegram automatically recognizes phone
    # entities. Manually submitted phone_number entities are ignored by Bot API.
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


def _signature(config, value):
    return base64.urlsafe_b64encode(hmac.new(config['action_secret'].encode(), value.encode(), hashlib.sha256).digest()[:12]).decode()


def lead_buttons(db, order, config):
    origin = public_origin(db)
    if not origin:
        return {}
    buttons = [[{'text':'Открыть заказ', 'url':origin + order_path(order['id'], order.get('locale', 'ru'))}]]
    if config.get('webhook_ready') and config.get('action_secret') and order['status'] == 'new':
        value = 'c:' + UUID(order['id']).hex + ':' + str(order['revision'])
        buttons.append([{'text':'Связались', 'callback_data':value + ':' + _signature(config, value)}])
    return {'reply_markup':{'inline_keyboard':buttons}}


def receive_update(db, update, secret, *, now=None):
    """Authenticated server-to-server entry. No browser session or public action URL."""
    config = _load(db)
    if not config.get('webhook_secret') or not hmac.compare_digest(str(secret), config['webhook_secret']):
        raise PermissionError('Invalid Telegram webhook')
    if not isinstance(update, dict):
        raise ValueError('Invalid Telegram update')
    now = time.time() if now is None else now
    pending = config.get('pending', {})
    if 'message' in update and pending and pending['token'] == config.get('token'):
        # Store only the verified candidate. CAS avoids overwriting a newly
        # refreshed code or a concurrent owner confirmation.
        candidate = _binding_candidate(pending, update['message'], now)
        if candidate:
            with connect(db) as con:
                con.execute('BEGIN IMMEDIATE')
                row = con.execute('SELECT payload FROM shop_telegram_connection WHERE id=1').fetchone()
                latest = json.loads(_cipher().decrypt(row[0].encode()))
                if latest.get('pending', {}).get('code') == pending['code']:
                    latest['pending']['verified_chat_id'] = candidate
                    payload = _cipher().encrypt(json.dumps(latest).encode()).decode()
                    con.execute('UPDATE shop_telegram_connection SET payload=? WHERE id=1', (payload,))
        return
    query = update.get('callback_query')
    if not isinstance(query, dict):
        return
    adapter = _adapter(config)
    sender, message = query.get('from', {}), query.get('message', {})
    chat = message.get('chat', {})
    try:
        matches_owner = config.get('username') == owner_username(db)
    except ConnectionError:
        matches_owner = False
    if (not config.get('chat_id') or not matches_owner
        or str(sender.get('id')) != config['chat_id'] or sender.get('is_bot') is not False
        or chat.get('type') != 'private' or str(chat.get('id')) != config['chat_id']):
        _answer(adapter, query, 'Эта кнопка доступна только владельцу заказа.')
        return
    data = query.get('data', '')
    match = re.fullmatch(r'(c:([a-f0-9]{32}):([1-9][0-9]{0,8})):([A-Za-z0-9_-]{16})', data) if isinstance(data, str) else None
    if not match or not config.get('action_secret') or not hmac.compare_digest(match[4], _signature(config, match[1])):
        _answer(adapter, query, 'Кнопка устарела. Откройте заказ в кабинете.')
        return
    from scena_shop import _connect, _order, _now, _t
    with _connect(db) as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT payload FROM shop_telegram_connection WHERE id=1').fetchone()
        active = json.loads(_cipher().decrypt(row[0].encode())) if row else {}
        # Recheck the binding inside the same writer transaction as the order.
        if any(active.get(key) != config.get(key) for key in ('token','chat_id','username','action_secret','webhook_secret')):
            raise PermissionError('Telegram binding changed')
        order = _order(con, str(UUID(match[2])))
        if not order or order['telegram_message_id'] != str(message.get('message_id')):
            order = None
        elif order['status'] == 'new' and order['revision'] == int(match[3]):
            con.execute("UPDATE shop_orders SET status='contacted',revision=revision+1,updated_at=? WHERE id=? AND revision=? AND status='new'",
                (_now(), order['id'], int(match[3])))
            order = _order(con, order['id'])
    if not order:
        _answer(adapter, query, 'Заказ недоступен. Откройте кабинет.')
        return
    # Commit first. An edit timeout must never undo the saved order status.
    # Keep the callback on edit failure so another tap can retry message sync.
    updated = True
    try:
        adapter._call('editMessageText', {'chat_id':config['chat_id'], 'message_id':message['message_id'],
            'text':lead_text(order), 'link_preview_options':{'is_disabled':True}, **lead_buttons(db, order, config)})
    except Exception:
        updated = False
    text = 'Статус: ' + _t(order['status'], 'ru')
    if not updated:
        text += '. В SCENA сохранён; сообщение обновится при повторном нажатии.'
    _answer(adapter, query, text)


def _answer(adapter, query, text):
    try:
        adapter._call('answerCallbackQuery', {'callback_query_id':query['id'], 'text':text, 'show_alert':False})
    except Exception:
        pass  # Old/repeated callbacks may already have expired on Telegram.


def dispatch(db, *, order_id=None, now=None, adapter=None):
    """Claim one durable lead; never roll back a committed customer order.

Retry pending leads through the owner's explicit Retry action.
Telegram has no idempotency key: an ambiguous transport timeout can produce a
duplicate message on retry; the stable order reference identifies the same lead.
"""
    from scena_shop import _connect, _order
    now = time.time() if now is None else now
    try:
        config = {}
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
            result = adapter._call('sendMessage', {'chat_id':adapter.admin_chat_id, 'text':lead_text(order), 'link_preview_options':{'is_disabled':True}, **lead_buttons(db, order, config)})
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
            if status.get('actions_ready'):
                st.caption('В новых лидах доступны кнопки «Открыть заказ» и «Связались».')
            elif os.environ.get('SCENA_NATIVE_WEB') == '1' and st.button('Включить кнопки в Telegram'):
                enable_actions(db)
                st.rerun()
        else:
            st.info('Подключите личный Telegram, указанный в «Моя сцена», чтобы получать заказы из маркета.')
        st.caption('Если бот уже создан, используйте его токен из @BotFather. Новый бот нужен только при отсутствии собственного бота. Токен вставьте только сюда.')
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
            st.caption('Код действует 10 минут. Отправьте его своему боту, затем нажмите кнопку ниже.')
            if st.button('Код отправлен — подключить Telegram'):
                try:
                    confirm_connection(db)
                    if os.environ.get('SCENA_NATIVE_WEB') == '1' and public_origin(db):
                        enable_actions(db)
                    st.rerun()
                except ConnectionError as error:
                    st.warning(str(error))
            if st.button('Получить новый код без повторного ввода токена'):
                refresh_code(db)
                st.rerun()
        if status['connected'] and st.button('Повторить отправку ожидающего заказа'):
            result = dispatch(db)
            st.success('Уведомление отправлено.' if result == 'sent' else 'Нет заказов, готовых к повторной отправке.') if result in ('sent','idle') else st.warning('Telegram пока недоступен. Заказ остаётся в очереди.')
    except ConnectionError as error:
        st.warning(str(error))
