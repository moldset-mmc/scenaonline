"""Service booking leads and signed actions using the existing owner's bot."""
from __future__ import annotations

from datetime import datetime
import hmac
import json
import re
import time
from urllib.parse import quote, urlencode, urlsplit

import scena_shop_telegram as tg

CHANNELS = ('phone', 'telegram', 'sms', 'email')
CHANNEL_LABELS = {
    'ru':dict(zip(CHANNELS, ('Звонок', 'Telegram', 'SMS', 'Email'))),
    'ro':dict(zip(CHANNELS, ('Apel telefonic', 'Telegram', 'SMS', 'Email'))),
    'en':dict(zip(CHANNELS, ('Phone call', 'Telegram', 'SMS', 'Email'))),
}


def initialize(con):
    columns = {row[1] for row in con.execute('PRAGMA table_info(requests)')}
    for name, definition in {
        'revision':'INTEGER NOT NULL DEFAULT 1',
        'contact_telegram':"TEXT NOT NULL DEFAULT ''",
        'telegram_status':"TEXT NOT NULL DEFAULT 'skipped'",
        'telegram_attempts':'INTEGER NOT NULL DEFAULT 0',
        'telegram_retry_at':'REAL NOT NULL DEFAULT 0',
        'telegram_message_id':"TEXT NOT NULL DEFAULT ''",
    }.items():
        if name not in columns:
            con.execute(f'ALTER TABLE requests ADD COLUMN {name} {definition}')


def validate_reply_contact(channel, telegram, email):
    from scena_core import RequestValidationError
    if channel not in CHANNELS:
        raise RequestValidationError('Выберите способ связи.')
    value = str(telegram or '').strip()
    if value.startswith(('https://','http://','t.me/')):
        parsed = urlsplit(value if '://' in value else 'https://'+value)
        value = parsed.path.strip('/') if parsed.hostname == 't.me' and not parsed.query and not parsed.fragment else ''
    value = value.lstrip('@')
    if value and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', value):
        raise RequestValidationError('Укажите Telegram в формате @username.')
    if channel == 'telegram' and not value:
        raise RequestValidationError('Для ответа в Telegram укажите ваш @username.')
    if channel == 'email' and not email:
        raise RequestValidationError('Для ответа по email укажите адрес электронной почты.')
    return '@'+value.lower() if value else ''


def request_path(request_id, locale='ru'):
    return '/?' + urlencode({'page':'admin','lang':locale if locale in ('ru','ro','en') else 'ru',
        'section':'work','view':'requests','request':int(request_id)})


def reply_link(row):
    """Device links only; never send a customer message on GET or on status change."""
    from scena_shop import dial_number
    channel = row.get('contact_channel', 'sms')
    phone = dial_number(row['phone'])
    if channel == 'telegram':
        value = row.get('contact_telegram','').lstrip('@')
        return 'https://t.me/'+value if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', value) else ''
    if channel == 'email':
        return ''
    if channel in ('sms','phone') and phone:
        return ('sms:' if channel == 'sms' else 'tel:') + phone
    return ''


def reply_label(row, locale='ru'):
    labels = {
        'ru':{'phone':'Позвонить клиенту','telegram':'Ответить в Telegram','sms':'Ответить по SMS','email':'Ответить по email'},
        'ro':{'phone':'Sună clientul','telegram':'Răspunde în Telegram','sms':'Răspunde prin SMS','email':'Răspunde prin email'},
        'en':{'phone':'Call client','telegram':'Reply in Telegram','sms':'Reply by SMS','email':'Reply by email'},
    }
    return labels.get(locale, labels['ru']).get(row.get('contact_channel','sms'), 'Ответить клиенту')


def lead_text(row):
    from scena_shop import dial_number
    day = datetime.fromisoformat(row['preferred_date']).strftime('%d.%m.%Y')
    lines = [f"Запись №{row['id']} · {row['service']}", 'Статус: '+row['status'],
        'Запись: '+day+' · '+row['preferred_time']+' (Кишинёв)', '',
        row['name'], 'Телефон: '+(dial_number(row['phone']) or row['phone'])]
    channel = row['contact_channel']
    if channel == 'telegram' and row.get('contact_telegram'):
        lines.append('Ответить в Telegram: '+row['contact_telegram'])
    elif channel == 'email' and row.get('email'):
        lines.append('Ответить по email: '+row['email'])
    elif channel == 'sms':
        lines.append('Ответить по SMS')
    if row['status'] in ('Ожидает подтверждения','Связались') and row['hold_expires_at']:
        from scena_core import CHISINAU
        until = datetime.fromisoformat(row['hold_expires_at']).astimezone(CHISINAU).strftime('%d.%m.%Y %H:%M')
        lines.append('Подтвердить до: '+until)
    if row['message']:
        lines += ['', 'Пожелания: '+row['message'][:700]]
    return '\n'.join(lines).encode('utf-16-le')[:7800].decode('utf-16-le', errors='ignore')


def lead_buttons(db, row, config, *, menu=False):
    from scena_core import REQUEST_STATUSES
    origin = tg.public_origin(db)
    if not origin:
        return {}
    destination = origin + request_path(row['id'], row['locale'])
    buttons = [[{'text':'Открыть заявку','url':destination}]]
    link = reply_link(row)
    if link and row['contact_channel'] != 'phone':
        # Bot inline buttons accept HTTP/tg URLs, not tel/mailto/sms schemes.
        buttons.append([{'text':reply_label(row), 'url':link if row['contact_channel']=='telegram' else destination+'#request-contact'}])
    if config.get('webhook_ready') and config.get('action_secret'):
        prefix = f"r:{row['id']}:{row['revision']}:"
        if menu:
            buttons = [[tg.action_button(config, prefix+str(i), ('✓ ' if status == row['status'] else '')
                +status+(' · авто' if status == 'Срок подтверждения истёк' else ''))]
                for i,status in enumerate(REQUEST_STATUSES)]
            buttons.append([tg.action_button(config,prefix+'b','Назад')])
        else:
            buttons.append([tg.action_button(config,prefix+'m','Сменить статус')])
    return {'reply_markup':{'inline_keyboard':buttons}}


def dispatch(db, *, request_id=None, now=None, adapter=None):
    """Lease one committed service lead. Historical requests stay skipped."""
    from scena_core import _connect
    now = time.time() if now is None else now
    try:
        config = {}
        if adapter is None:
            config = tg._load(db)
            if not config.get('chat_id') or config.get('username') != tg.owner_username(db):
                return 'unconfigured'
            adapter = tg._adapter(config)
        if not adapter.configured:
            return 'unconfigured'
        with _connect(db) as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute("SELECT * FROM requests WHERE request_type='service_request' AND telegram_status IN ('queued','retry','sending') AND telegram_retry_at<=?"
                + (' AND id=?' if request_id else '') + ' ORDER BY id LIMIT 1', (now,request_id) if request_id else (now,)).fetchone()
            if not row:
                return 'idle'
            row = dict(row)
            con.execute("UPDATE requests SET telegram_status='sending',telegram_attempts=telegram_attempts+1,telegram_retry_at=? WHERE id=?", (now+60,row['id']))
        try:
            result = adapter._call('sendMessage', {'chat_id':adapter.admin_chat_id,'text':lead_text(row),
                'link_preview_options':{'is_disabled':True}, **lead_buttons(db,row,config)})
            if not isinstance(result,dict) or result.get('message_id') is None:
                raise ValueError()
        except Exception:
            with _connect(db) as con:
                con.execute("UPDATE requests SET telegram_status='retry',telegram_retry_at=? WHERE id=?", (now+min(3600,30*2**min(row['telegram_attempts']+1,6)),row['id']))
            return 'retry'
        with _connect(db) as con:
            con.execute("UPDATE requests SET telegram_status='sent',telegram_message_id=?,telegram_retry_at=0 WHERE id=?", (str(result['message_id']),row['id']))
        return 'sent'
    except Exception:
        return 'retry'


def receive_callback(db, query, config, now):
    """Called only after shared webhook and owner/chat validation."""
    adapter = tg._adapter(config)
    data = query.get('data','')
    match = re.fullmatch(r'([sr]:([1-9][0-9]{0,18}):([1-9][0-9]{0,8}):([cfmb0-7])):([A-Za-z0-9_-]{16})', data)
    if (not match or not config.get('action_secret') or not hmac.compare_digest(match[5],tg._signature(config,match[1]))
        or (data.startswith('s:') != (match[4] in ('c','f')))):
        tg._answer(adapter,query,'Кнопка устарела. Откройте заявку в кабинете.')
        return
    from scena_core import _connect, _expire_pending, _change_request_status, CHISINAU, RequestValidationError, REQUEST_STATUSES
    moment = datetime.fromtimestamp(now, CHISINAU)
    action = match[4]
    menu, notice = action == 'm', ''
    with _connect(db) as con:
        con.execute('BEGIN IMMEDIATE')
        stored = con.execute('SELECT payload FROM shop_telegram_connection WHERE id=1').fetchone()
        active = json.loads(tg._cipher().decrypt(stored[0].encode())) if stored else {}
        if any(active.get(key)!=config.get(key) for key in ('token','chat_id','username','action_secret','webhook_secret')):
            raise PermissionError('Telegram binding changed')
        row = con.execute("SELECT * FROM requests WHERE id=? AND request_type='service_request'", (int(match[2]),)).fetchone()
        if not row or row['telegram_message_id'] != str(query['message'].get('message_id')):
            row = None
        else:
            _expire_pending(con, moment)
            row = dict(con.execute('SELECT * FROM requests WHERE id=?', (row['id'],)).fetchone())
            if action == '7':
                menu, notice = True, 'Этот статус устанавливается автоматически, когда истекает срок подтверждения.'
            elif action not in ('m','b'):
                status = {'c':'Связались','f':'Подтверждена'}.get(action) or REQUEST_STATUSES[int(action)]
                allowed = not data.startswith('s:') or row['status']=='Ожидает подтверждения' or (row['status']=='Связались' and status=='Подтверждена')
                if row['revision'] != int(match[3]):
                    menu, notice = True, 'Заявка изменилась. Выберите статус заново.'
                elif allowed:
                    try:
                        _change_request_status(con,row,status,moment)
                    except RequestValidationError as error:
                        menu, notice = True, str(error)
            row = dict(con.execute('SELECT * FROM requests WHERE id=?', (row['id'],)).fetchone())
    if not row:
        tg._answer(adapter,query,'Заявка недоступна. Откройте кабинет.')
        return
    try:
        adapter._call('editMessageText', {'chat_id':config['chat_id'],'message_id':query['message']['message_id'],
            'text':lead_text(row),'link_preview_options':{'is_disabled':True}, **lead_buttons(db,row,config,menu=menu)})
    except Exception:
        notice = notice or 'Статус в SCENA: '+row['status']+'. Повторите нажатие для обновления сообщения.'
    tg._answer(adapter,query,notice or ('Выберите статус' if menu else 'Статус: '+row['status']))
