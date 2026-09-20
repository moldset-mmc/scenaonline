"""Independent public-card content, edited through the existing owner cabinet."""
from __future__ import annotations

import base64
from functools import lru_cache
import io
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote, urlsplit
import uuid

from scena_database import connect

CARD_URL = 'https://mbstudio.scena.life/card/'
ROOT = Path(__file__).resolve().parent
DEFAULT_CARD = {
    'first_name': 'Маша',
    'last_name': 'Бараночникова',
    'profession': 'Model & Makeup Artist',
    'tagline': 'Красота. Характер. Движение.',
    'photo': '',
    'primary_label': 'Запись и услуги',
    'primary_url': 'https://mbstudio.scena.life/ru/zapis/',
    'site_url': 'https://mbstudio.scena.life/ru/',
    'instagram_url': 'https://www.instagram.com/masha_cravcenco/',
    'telegram_url': '',
    'phone': '',
    'email': '',
}
LIMITS = {'first_name': 60, 'last_name': 80, 'profession': 80, 'tagline': 160,
          'primary_label': 50, 'phone': 40, 'email': 254, 'photo': 300}


def initialize_card(connection):
    connection.execute('CREATE TABLE IF NOT EXISTS business_card_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    # Seed once from the approved card, never from the changing main profile.
    connection.executemany('INSERT OR IGNORE INTO business_card_settings(key,value) VALUES(?,?)', DEFAULT_CARD.items())


def _read(connection):
    stored = dict(connection.execute('SELECT key,value FROM business_card_settings').fetchall())
    return {key: stored.get(key, default) for key, default in DEFAULT_CARD.items()}


def get_card(db_path):
    with connect(db_path) as connection:
        return _read(connection)


def validate_card(values):
    card = {key: str(values.get(key, default)).strip() for key, default in DEFAULT_CARD.items()}
    for key, value in card.items():
        if len(value) > LIMITS.get(key, 2048) or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError('Проверьте длину полей. Каждое поле должно занимать одну строку.')
    if not card['first_name']:
        raise ValueError('Укажите имя для визитки.')
    if bool(card['primary_label']) != bool(card['primary_url']):
        raise ValueError('Для основной кнопки заполните название и ссылку или очистите оба поля.')
    for key in ('primary_url', 'site_url', 'instagram_url', 'telegram_url'):
        value = card[key]
        if not value:
            continue
        try:
            url = urlsplit(value)
            valid = url.scheme == 'https' and url.hostname and not url.username and not url.password and url.port in (None, 443)
        except ValueError:
            valid = False
        if not valid or re.search(r'[\s<>"\\]', value):
            raise ValueError('Укажите полную ссылку, начинающуюся с https://.')
    if card['phone'] and (not re.fullmatch(r'\+?[0-9 ()-]+', card['phone']) or not 7 <= len(re.sub(r'\D', '', card['phone'])) <= 15):
        raise ValueError('Укажите телефон с кодом страны: от 7 до 15 цифр.')
    if card['email'] and not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", card['email']):
        raise ValueError('Проверьте адрес электронной почты.')
    return card


def save_card(db_path, app_dir, values, *, expected, upload=None):
    """Compare and save all fields together; main profile is never written."""
    from scena_model_intro import _original
    from scena_media import persist, publish_reference
    from scena_photo_library import original_path, photo_id
    updates = {key: value for key, value in values.items() if key in DEFAULT_CARD}
    card = validate_card({**expected, **updates})
    extension = _original(upload) if upload is not None else None
    destination = None
    root = Path(app_dir).resolve()
    try:
        with connect(db_path, timeout=15) as connection:
            connection.execute('BEGIN IMMEDIATE')
            actual = _read(connection)
            if actual != expected:
                raise ValueError('Визитка уже изменена в другом окне. Обновите редактор перед сохранением.')
            if upload is not None:
                folder = (root / 'media' / 'business-card').resolve()
                if not folder.is_relative_to(root / 'media') or not folder.is_relative_to(root):
                    raise ValueError('Не удалось сохранить фотографию.')
                folder.mkdir(parents=True, exist_ok=True)
                destination = folder / (uuid.uuid4().hex + '.' + extension)
                destination.write_bytes(upload)
                persist(destination, root, public=True, connection=connection)
                card['photo'] = destination.relative_to(root).as_posix()
            elif card['photo'] and card['photo'] != actual['photo']:
                trashed = connection.execute('SELECT value FROM profile_settings WHERE key=?', ('photo_trash:' + photo_id(card['photo']),)).fetchone()
                if trashed and trashed[0]:
                    raise ValueError('Фото в корзине. Сначала восстановите его в разделе «Фото».')
                _original(original_path(db_path, root, card['photo']).read_bytes())
                publish_reference(root, card['photo'], connection=connection)
            connection.executemany('INSERT INTO business_card_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', card.items())
    except Exception:
        if destination:
            destination.unlink(missing_ok=True)
        raise
    return card


def photo_source(db_path, app_dir, card):
    """Only the selected published rendition may be exposed by the public card."""
    from scena_database import cloud_database
    if not card['photo']:
        return ROOT / 'public/card/assets/portrait.webp'
    root = Path(app_dir).resolve()
    path = (root / card['photo']).resolve()
    if not path.is_relative_to(root / 'media') or path.is_symlink():
        raise ValueError('Invalid card photo')
    if cloud_database(db_path):
        with connect(db_path) as connection:
            row = connection.execute('SELECT public_url FROM scena_media_files WHERE path=?', (card['photo'],)).fetchone()
        url = urlsplit(row[0]) if row and row[0] else None
        if not url or url.scheme != 'https' or not (url.hostname or '').endswith('.public.blob.vercel-storage.com'):
            raise OSError('Published card photo unavailable')
        return row[0]
    return path


def portrait_bytes(source):
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(source) if isinstance(source, bytes) else source) as original:
        photo = ImageOps.exif_transpose(original).convert('RGB')
        photo.thumbnail((1200, 1500))
        output = io.BytesIO()
        photo.save(output, 'WEBP', quality=88, method=4)
        return output.getvalue()


def full_name(card):
    return ' '.join(card[key] for key in ('first_name', 'last_name') if card[key])


def vcard(card):
    def escape(value):
        return value.replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')
    lines = ['BEGIN:VCARD', 'VERSION:3.0', 'N:' + escape(card['last_name']) + ';' + escape(card['first_name']) + ';;;',
             'FN:' + escape(full_name(card)), 'ORG:MBStudio']
    for key, prefix in [('profession', 'TITLE:'), ('site_url', 'URL:'), ('phone', 'TEL;TYPE=CELL:'),
                        ('email', 'EMAIL;TYPE=INTERNET:'), ('instagram_url', 'X-SOCIALPROFILE;TYPE=instagram:'),
                        ('telegram_url', 'X-SOCIALPROFILE;TYPE=telegram:'), ('tagline', 'NOTE:')]:
        if card[key]:
            lines.append(prefix + escape(card[key]))
    lines.extend(['URL:' + CARD_URL, 'END:VCARD'])
    # Fold by UTF-8 octets, never split a Cyrillic character (vCard 3.0).
    folded = []
    for line in lines:
        part = ''
        for char in line:
            if len((part + char).encode('utf-8')) > 75:
                folded.append(part)
                part = ' '
            part += char
        folded.append(part)
    return ('\r\n'.join(folded) + '\r\n').encode('utf-8')


@lru_cache(maxsize=1)
def _template():
    from tornado.template import Template
    return Template((ROOT / 'scena_web/templates/business_card.html').read_text(), autoescape='xhtml_escape')


def render_card(card, *, preview=False, photo_url=None):
    from scena_photo_library import photo_id
    photo_url = photo_url or '/card/portrait.webp?v=' + photo_id(card['photo'])
    return _template().generate(
        card=card, name=full_name(card), description=' · '.join(filter(None, (full_name(card), card['profession'], card['tagline']))),
        card_url=CARD_URL, photo_url=photo_url, preview=preview,
        phone_href='tel:' + re.sub(r'[^+0-9]', '', card['phone']),
        email_href='mailto:' + quote(card['email'], safe='@.'),
        contact_url=('data:text/vcard;charset=utf-8;base64,' + base64.b64encode(vcard(card)).decode()) if preview else '/card/mbstudio.vcf',
    ).decode('utf-8')
