"""Personal recommendations, real orders, and portable original product photos.

The owner controls availability and fulfils orders personally. This module never
charges a card or claims that a payment, stock reservation or delivery happened.
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import uuid
import warnings
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

LOCALES = ('ru', 'ro', 'en')
SHOP_TABLES = ('shop_products', 'shop_orders', 'shop_order_items')
SHOP_DEFAULT_SETTINGS = {
    'shop_enabled': '1',
    'shop_title_ru': 'Выбор мастера', 'shop_title_ro': 'Alegerea specialistului', 'shop_title_en': 'The expert’s edit',
    'shop_description_ru': 'Средства и инструменты, которые я выбираю для работы и рекомендую вам. У каждого — своя задача и мой личный комментарий.',
    'shop_description_ro': 'Produse și instrumente pe care le aleg pentru lucru și vi le recomand. Fiecare are un scop și recomandarea mea personală.',
    'shop_description_en': 'Products and tools I choose for my work and recommend to you. Each has a purpose and my personal recommendation.',
}
PRODUCT_FIELDS = tuple(f'{field}_{lang}' for field in ('name', 'description', 'recommendation', 'category') for lang in LOCALES)
PRODUCT_STATES = ('draft', 'published', 'hidden', 'archived')
ORDER_STATES = ('new', 'contacted', 'confirmed', 'fulfilled', 'cancelled')


class ShopError(ValueError):
    """Stable error codes are translated only at the presentation boundary."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _connect(db):
    con = sqlite3.connect(Path(db), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA busy_timeout=15000')
    return con


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def init_shop(db_or_connection):
    """Additive migration. A supplied connection remains owned by the caller."""
    own = not isinstance(db_or_connection, sqlite3.Connection)
    con = _connect(db_or_connection) if own else db_or_connection
    try:
        text_columns = ','.join(f'{field} TEXT NOT NULL DEFAULT \'\'' for field in PRODUCT_FIELDS)
        con.execute(f'''CREATE TABLE IF NOT EXISTS shop_products (
            id TEXT PRIMARY KEY, {text_columns},
            price_cents INTEGER NOT NULL CHECK(price_cents > 0 AND price_cents <= 100000000),
            currency TEXT NOT NULL DEFAULT 'MDL' CHECK(currency='MDL'),
            image TEXT NOT NULL DEFAULT '', photo_history TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','hidden','archived')),
            revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        if 'photo_history' not in {row[1] for row in con.execute('PRAGMA table_info(shop_products)')}:
            con.execute("ALTER TABLE shop_products ADD COLUMN photo_history TEXT NOT NULL DEFAULT '[]'")
        con.execute('''CREATE TABLE IF NOT EXISTS shop_orders (
            id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE,
            request_key TEXT NOT NULL UNIQUE, request_hash TEXT NOT NULL,
            customer_name TEXT NOT NULL, phone TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',
            telegram TEXT NOT NULL DEFAULT '', preferred_contact TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '', locale TEXT NOT NULL,
            total_cents INTEGER NOT NULL CHECK(total_cents > 0), currency TEXT NOT NULL DEFAULT 'MDL',
            status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','contacted','confirmed','fulfilled','cancelled')),
            revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        con.execute('''CREATE TABLE IF NOT EXISTS shop_order_items (
            order_id TEXT NOT NULL REFERENCES shop_orders(id) ON DELETE CASCADE,
            product_id TEXT NOT NULL REFERENCES shop_products(id),
            quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 99),
            unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents > 0),
            name_ru TEXT NOT NULL, name_ro TEXT NOT NULL, name_en TEXT NOT NULL,
            recommendation_ru TEXT NOT NULL, recommendation_ro TEXT NOT NULL, recommendation_en TEXT NOT NULL,
            product_revision INTEGER NOT NULL, PRIMARY KEY(order_id,product_id))''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_shop_products_status ON shop_products(status,updated_at)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_shop_orders_status ON shop_orders(status,created_at)')
        if own:
            con.commit()
    finally:
        if own:
            con.close()


def price_to_cents(value):
    if isinstance(value, bool):
        raise ShopError('price')
    try:
        amount = Decimal(str(value).strip().replace(',', '.'))
        if not amount.is_finite() or amount <= 0 or amount > Decimal('1000000') or amount != amount.quantize(Decimal('0.01')):
            raise ShopError('price')
        return int(amount * 100)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ShopError('price') from exc


def money(cents):
    return f'{int(cents) // 100:,}'.replace(',', ' ') + (f',{int(cents) % 100:02d}' if int(cents) % 100 else '') + ' MDL'


def _is_pro(db):
    from scena_cabinet import get_pro_status
    return get_pro_status(db)['is_active']


def local_photo(app_dir, value):
    try:
        root = Path(app_dir).resolve()
        source = root / str(value)
        target = source.resolve()
        target.relative_to((root / 'media').resolve())
        target.relative_to(root)
        if target.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp') or not target.is_file() or source.is_symlink():
            return None
        return target
    except (ValueError, OSError):
        return None


def _photo_extension(data):
    from PIL import Image, UnidentifiedImageError
    if not data or len(data) > 20 * 1024 * 1024:
        raise ShopError('photo_size')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as photo:
                extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(photo.format)
                if not extension or getattr(photo, 'is_animated', False):
                    raise ShopError('photo_format')
                if min(photo.size) < 400:
                    raise ShopError('photo_quality')
                photo.verify()
        return extension
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ShopError('photo_format') from exc


def get_product(db, product_id, *, public=False):
    with _connect(db) as con:
        row = con.execute('SELECT * FROM shop_products WHERE id=?' + (" AND status='published'" if public else ''), (str(product_id),)).fetchone()
    return dict(row) if row else None


def product_photo_history(app_dir, product):
    try:
        values = json.loads(product.get('photo_history', '[]'))
    except (TypeError, ValueError):
        return []
    return [value for value in values if isinstance(value, str) and local_photo(app_dir, value)] if isinstance(values, list) else []


def list_products(db, *, public=False):
    with _connect(db) as con:
        rows = con.execute('SELECT * FROM shop_products' + (" WHERE status='published'" if public else '') + ' ORDER BY updated_at DESC,id').fetchall()
    return [dict(row) for row in rows]


def save_product(db, app_dir, values, *, product_id=None, expected_revision=None, upload=None):
    """Save with compare-and-swap; failed edits cannot leave replacement photos."""
    previous = get_product(db, product_id) if product_id else None
    if product_id and previous is None:
        raise ShopError('missing')
    merged = {**{field: '' for field in PRODUCT_FIELDS}, **(previous or {}), **values}
    allowed = set(PRODUCT_FIELDS) | {'price', 'status', 'image'}
    if any(key not in allowed for key in values):
        raise ShopError('fields')
    status = str(merged.get('status', 'draft'))
    if status not in PRODUCT_STATES or status == 'archived':
        raise ShopError('state')
    # Publishing/expanding the shop is a PRO tool. Existing published products
    # remain available after expiry and their owner can edit personal content.
    needs_pro = not previous or (status == 'published' and previous['status'] != 'published')
    if needs_pro and not _is_pro(db):
        raise ShopError('pro')
    price_cents = price_to_cents(merged['price']) if 'price' in merged else int(merged.get('price_cents', 0))
    if not 0 < price_cents <= 100000000:
        raise ShopError('price')
    clean = {}
    for field in PRODUCT_FIELDS:
        clean[field] = str(merged[field]).strip()
        limit = 160 if field.startswith(('name_', 'category_')) else 2400
        if len(clean[field]) > limit:
            raise ShopError('length')
    if not any(clean[f'name_{locale}'] for locale in LOCALES):
        raise ShopError('name')
    if status == 'published' and any(not clean[field] for field in PRODUCT_FIELDS):
        raise ShopError('translations')
    image = str(merged.get('image', '')).strip()
    extension = _photo_extension(upload) if upload is not None else None
    if upload is None and image and not local_photo(app_dir, image):
        raise ShopError('photo_missing')
    if status == 'published' and not (image or upload):
        raise ShopError('photo_missing')
    destination = temporary = None
    product_id = str(product_id or uuid.uuid4())
    try:
        with _connect(db) as con:
            con.execute('BEGIN IMMEDIATE')
            actual = con.execute('SELECT revision,status FROM shop_products WHERE id=?', (product_id,)).fetchone()
            if previous and (actual is None or expected_revision != actual['revision']):
                raise ShopError('stale')
            if needs_pro:
                # Recheck subscription inside the writer transaction. get_pro_status
                # may persist expiry, so use the already normalized source row here.
                membership = con.execute("SELECT status,expires_at FROM pro_subscriptions WHERE owner_key='master'").fetchone()
                if not membership or membership['status'] not in ('trial', 'active') or datetime.fromisoformat(membership['expires_at']) <= datetime.now(timezone.utc):
                    raise ShopError('pro')
            if upload is not None:
                root = Path(app_dir).resolve()
                folder = (root / 'media' / 'shop').resolve()
                folder.relative_to(root)
                folder.relative_to((root / 'media').resolve())
                folder.mkdir(parents=True, exist_ok=True)
                descriptor, filename = tempfile.mkstemp(prefix='.upload-', dir=folder)
                temporary = Path(filename)
                with os.fdopen(descriptor, 'wb') as handle:
                    handle.write(upload)
                    handle.flush()
                    os.fsync(handle.fileno())
                destination = folder / f'{uuid.uuid4().hex}.{extension}'
                os.replace(temporary, destination)
                image = destination.relative_to(root).as_posix()
            history = product_photo_history(app_dir, previous or {})
            if previous and previous.get('image') and previous['image'] != image and local_photo(app_dir, previous['image']):
                history = [previous['image']] + [value for value in history if value != previous['image']]
            history = [value for value in history if value != image]
            fields = list(PRODUCT_FIELDS) + ['price_cents', 'image', 'photo_history', 'status', 'updated_at']
            data = [clean[field] for field in PRODUCT_FIELDS] + [price_cents, image, json.dumps(history), status, _now()]
            if previous:
                con.execute('UPDATE shop_products SET ' + ','.join(f'{field}=?' for field in fields) + ',revision=revision+1 WHERE id=?', data + [product_id])
            else:
                fields += ['id', 'created_at']
                con.execute('INSERT INTO shop_products (' + ','.join(fields) + ') VALUES (' + ','.join('?' for _ in fields) + ')', data + [product_id, _now()])
    except Exception:
        if temporary:
            temporary.unlink(missing_ok=True)
        if destination:
            destination.unlink(missing_ok=True)
        raise
    return get_product(db, product_id)


def archive_product(db, product_id, *, expected_revision, confirmed=False):
    if confirmed is not True:
        raise ShopError('confirmation')
    with _connect(db) as con:
        con.execute('BEGIN IMMEDIATE')
        changed = con.execute("UPDATE shop_products SET status='archived',revision=revision+1,updated_at=? WHERE id=? AND revision=?", (_now(), str(product_id), expected_revision)).rowcount
        if changed != 1:
            raise ShopError('stale')


def _cart(cart):
    if not isinstance(cart, dict) or not 1 <= len(cart) <= 20:
        raise ShopError('cart')
    result = {}
    for key, quantity in cart.items():
        if not isinstance(key, str) or len(key) > 64 or isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 99:
            raise ShopError('cart')
        result[key] = quantity
    if sum(result.values()) > 100:
        raise ShopError('cart')
    return dict(sorted(result.items()))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _quote(con, cart):
    visible = con.execute("SELECT value FROM profile_settings WHERE key='shop_enabled'").fetchone()
    if visible and visible[0] != '1':
        raise ShopError('closed')
    items = []
    for key, quantity in _cart(cart).items():
        product = con.execute("SELECT * FROM shop_products WHERE id=? AND status='published'", (key,)).fetchone()
        if product is None:
            raise ShopError('unavailable')
        item = {field: product[field] for field in ('id', 'revision', 'price_cents') + tuple(f'{field}_{locale}' for field in ('name', 'recommendation') for locale in LOCALES)}
        item['quantity'] = quantity
        items.append(item)
    return {'items': items, 'total_cents': sum(item['quantity'] * item['price_cents'] for item in items), 'currency': 'MDL', 'fingerprint': _digest(items)}


def quote_cart(db, cart):
    with _connect(db) as con:
        return _quote(con, cart)


def _contacts(values):
    limits = {'name': 160, 'phone': 40, 'email': 254, 'telegram': 40, 'note': 2000, 'preferred_contact': 12}
    data = {field: str(values.get(field, '')).strip() for field in limits}
    if any(len(data[field]) > limit or any(ord(c) < 32 and c not in '\n\t' for c in data[field]) for field, limit in limits.items()):
        raise ShopError('contacts')
    if len(data['name']) < 2 or not re.fullmatch(r'\+?[\d ()-]{7,40}', data['phone']) or not 7 <= len(re.sub(r'\D', '', data['phone'])) <= 15:
        raise ShopError('contacts')
    if data['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', data['email']):
        raise ShopError('email')
    if data['telegram'] and not re.fullmatch(r'@?[A-Za-z][A-Za-z0-9_]{4,31}', data['telegram']):
        raise ShopError('telegram')
    if data['preferred_contact'] not in ('phone', 'email', 'telegram'):
        raise ShopError('contact_channel')
    if data['preferred_contact'] in ('email', 'telegram') and not data[data['preferred_contact']]:
        raise ShopError('contact_channel')
    if values.get('consent') is not True:
        raise ShopError('consent')
    return data


def create_order(db, cart, contacts, *, reviewed_quote, request_key, locale='ru'):
    """Client prices are never accepted; revision and actual prices are snapshotted."""
    items = _cart(cart)
    person = _contacts(contacts)
    if locale not in LOCALES:
        raise ShopError('locale')
    if not isinstance(request_key, str) or not re.fullmatch(r'[a-zA-Z0-9-]{20,80}', request_key):
        raise ShopError('request_key')
    request_hash = _digest({'cart': items, 'person': person, 'locale': locale})
    with _connect(db) as con:
        con.execute('BEGIN IMMEDIATE')
        previous = con.execute('SELECT id,request_hash FROM shop_orders WHERE request_key=?', (request_key,)).fetchone()
        if previous:
            if previous['request_hash'] != request_hash:
                raise ShopError('duplicate_conflict')
            return _order(con, previous['id'])
        quote = _quote(con, items)
        if not isinstance(reviewed_quote, str) or quote['fingerprint'] != reviewed_quote:
            raise ShopError('changed')
        order_id = str(uuid.uuid4())
        reference = 'SC-' + uuid.uuid4().hex[:10].upper()
        stamp = _now()
        con.execute('''INSERT INTO shop_orders (id,reference,request_key,request_hash,customer_name,phone,email,telegram,preferred_contact,note,locale,total_cents,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (order_id, reference, request_key, request_hash, person['name'], person['phone'], person['email'], person['telegram'], person['preferred_contact'], person['note'], locale, quote['total_cents'], stamp, stamp))
        for item in quote['items']:
            con.execute('''INSERT INTO shop_order_items (order_id,product_id,quantity,unit_price_cents,name_ru,name_ro,name_en,recommendation_ru,recommendation_ro,recommendation_en,product_revision)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (order_id, item['id'], item['quantity'], item['price_cents'], *(item[f'{field}_{lang}'] for field in ('name', 'recommendation') for lang in LOCALES), item['revision']))
        return _order(con, order_id)


def _order(con, order_id):
    row = con.execute('SELECT * FROM shop_orders WHERE id=?', (order_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result['items'] = [dict(item) for item in con.execute('SELECT * FROM shop_order_items WHERE order_id=? ORDER BY product_id', (order_id,))]
    return result


def list_orders(db):
    with _connect(db) as con:
        ids = [row[0] for row in con.execute('SELECT id FROM shop_orders ORDER BY created_at DESC,id DESC')]
        return [_order(con, order_id) for order_id in ids]


def update_order_status(db, order_id, status, *, expected_revision):
    if status not in ORDER_STATES:
        raise ShopError('state')
    with _connect(db) as con:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('UPDATE shop_orders SET status=?,revision=revision+1,updated_at=? WHERE id=? AND revision=?', (status, _now(), order_id, expected_revision)).rowcount != 1:
            raise ShopError('stale')


def public_shop_data(connection):
    """Explicit public-only interchange. Private orders never enter this result."""
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='shop_products'").fetchone():
        return []
    settings = dict(connection.execute('SELECT key,value FROM profile_settings'))
    if settings.get('shop_enabled', '1') != '1':
        return []
    columns = ('id',) + PRODUCT_FIELDS + ('price_cents', 'currency', 'image', 'updated_at')
    cursor = connection.execute('SELECT ' + ','.join(columns) + " FROM shop_products WHERE status='published' ORDER BY id")
    return [dict(zip(columns, row)) for row in cursor]


_TEXT = {
    'title': ('Личный Market', 'Market personal', 'Personal Market'),
    'owner_edit': ('Вещи, которым я доверяю', 'Lucruri în care am încredere', 'Things I believe in'),
    'owner_note': ('Личный выбор специалиста', 'Selecția personală a specialistului', 'Personally chosen by your expert'),
    'empty': ('Моя подборка начинается с личного выбора. Возвращайтесь за рекомендациями — каждый товар появится здесь с ценой и моим комментарием.', 'Selecția mea începe cu o alegere personală. Reveniți pentru recomandări: fiecare produs va apărea cu prețul și comentariul meu.', 'My collection begins with a personal choice. Come back for recommendations: every product will include a price and my own notes.'),
    'closed': ('Эта подборка сейчас закрыта. Познакомьтесь с автором на её Сцене.', 'Această selecție este închisă. Descoperiți autoarea pe Scena ei.', 'This collection is private. Meet its author on her Scene.'),
    'scene': ('Открыть её Сцену', 'Deschide Scena ei', 'Visit her Scene'),
    'search': ('Найти в подборке', 'Caută în selecție', 'Search the collection'),
    'categories': ('Категории', 'Categorii', 'Categories'),
    'all': ('Вся подборка', 'Toată selecția', 'All products'),
    'none': ('В этой подборке ничего не нашлось. Попробуйте другое название или категорию.', 'Nu am găsit produse. Încercați alt nume sau altă categorie.', 'No matching products. Try another name or category.'),
    'details': ('Подробнее', 'Detalii', 'Discover'),
    'add': ('В корзину', 'Adaugă în coș', 'Add to bag'),
    'added': ('Добавлено в корзину.', 'Adăugat în coș.', 'Added to your bag.'),
    'back': ('← К подборке', '← Înapoi la selecție', '← Back to the collection'),
    'why': ('Почему я рекомендую', 'De ce recomand', 'Why I recommend it'),
    'about': ('О товаре', 'Despre produs', 'About the product'),
    'bag': ('Ваша корзина', 'Coșul dvs.', 'Your bag'),
    'units': ('Количество', 'Cantitate', 'Quantity'),
    'remove': ('Убрать', 'Elimină', 'Remove'),
    'total': ('Итого', 'Total', 'Total'),
    'checkout': ('Перейти к оформлению', 'Continuă comanda', 'Continue to checkout'),
    'contact_title': ('Как с вами связаться?', 'Cum vă putem contacta?', 'How can we reach you?'),
    'name_label': ('Ваше имя', 'Numele dvs.', 'Your name'),
    'phone_label': ('Телефон', 'Telefon', 'Phone'),
    'email_label': ('Email — необязательно', 'Email — opțional', 'Email — optional'),
    'telegram_label': ('Telegram — необязательно', 'Telegram — opțional', 'Telegram — optional'),
    'preferred': ('Где вам удобнее получить ответ?', 'Unde preferați răspunsul?', 'Where would you prefer a reply?'),
    'phone': ('По телефону', 'La telefon', 'By phone'),
    'email': ('По email', 'Prin email', 'By email'),
    'telegram': ('В Telegram', 'În Telegram', 'On Telegram'),
    'note': ('Пожелания к заказу — необязательно', 'Preferințe pentru comandă — opțional', 'Order notes — optional'),
    'consent_label': ('Согласна на обработку контактов для этого заказа', 'Sunt de acord cu prelucrarea datelor de contact pentru această comandă', 'I agree to the use of my contact details for this order'),
    'review': ('Проверить заказ', 'Verifică comanda', 'Review your order'),
    'review_title': ('Всё верно? Подтвердите заказ', 'Totul este corect? Confirmați comanda', 'All correct? Confirm your order'),
    'terms': ('Вы оставляете заказ мастеру. Наличие, способ получения и оплату вы согласуете лично. Сейчас деньги не списываются.', 'Trimiteți comanda specialistului. Disponibilitatea, livrarea și plata se stabilesc personal. Nu se retrag bani acum.', 'You are placing an order with your expert. Availability, delivery and payment will be agreed personally. No payment is taken now.'),
    'final': ('Подтвердить заказ', 'Confirmă comanda', 'Confirm order'),
    'change': ('Изменить заказ', 'Modifică comanda', 'Edit order'),
    'success': ('Заказ принят', 'Comanda a fost primită', 'Order received'),
    'success_note': ('Мастер получил заказ в своём рабочем пространстве и свяжется с вами выбранным способом, чтобы согласовать наличие, получение и оплату.', 'Specialistul a primit comanda în spațiul său de lucru și vă va contacta prin metoda aleasă pentru a stabili disponibilitatea, livrarea și plata.', 'Your expert has received the order in their workspace and will contact you through your preferred channel to agree availability, delivery and payment.'),
    'continue': ('Вернуться к подборке', 'Înapoi la selecție', 'Back to the collection'),
    'admin_intro': ('Ваши рекомендации становятся личной подборкой. Покажите товар, объясните свой выбор и принимайте заказы.', 'Recomandările dvs. devin o selecție personală. Prezentați produsul, explicați alegerea și primiți comenzi.', 'Turn your recommendations into a personal collection. Show each product, explain your choice and receive orders.'),
    'products_tab': ('Товары', 'Produse', 'Products'),
    'orders_tab': ('Заказы', 'Comenzi', 'Orders'),
    'settings_tab': ('Витрина', 'Vitrină', 'Storefront'),
    'new_product': ('＋ Добавить товар', '＋ Adaugă produs', '＋ Add product'),
    'pick': ('Какой товар редактируем?', 'Ce produs edităm?', 'Which product are we editing?'),
    'draft': ('Черновик', 'Ciornă', 'Draft'),
    'published': ('Опубликован', 'Publicat', 'Published'),
    'hidden': ('Скрыт', 'Ascuns', 'Hidden'),
    'archived': ('В архиве', 'În arhivă', 'Archived'),
    'new': ('Новый', 'Nouă', 'New'),
    'contacted': ('Связались', 'Contactat', 'Contacted'),
    'confirmed': ('Подтверждён', 'Confirmată', 'Confirmed'),
    'fulfilled': ('Завершён', 'Finalizată', 'Fulfilled'),
    'cancelled': ('Отменён', 'Anulată', 'Cancelled'),
    'photo_label': ('Фотография товара', 'Fotografia produsului', 'Product photo'),
    'photo_restore': ('Вернуть сохранённую фотографию', 'Revino la o fotografie salvată', 'Restore a saved photo'),
    'photo_current': ('Оставить текущую фотографию', 'Păstrează fotografia actuală', 'Keep the current photo'),
    'photo_version': ('Предыдущая фотография', 'Fotografie anterioară', 'Previous photo'),
    'photo_hint': ('JPG, PNG или WebP · до 20 МБ · обе стороны от 400 px. Оригинал сохраняется; замена не удаляет предыдущий файл.', 'JPG, PNG sau WebP · până la 20 MB · ambele laturi de minimum 400 px. Originalul se păstrează; înlocuirea nu șterge fișierul anterior.', 'JPG, PNG or WebP · up to 20 MB · both sides at least 400 px. Originals are kept; replacement does not delete the previous file.'),
    'product_name': ('Название', 'Denumire', 'Name'),
    'category': ('Категория', 'Categorie', 'Category'),
    'description': ('Описание', 'Descriere', 'Description'),
    'recommendation': ('Моя рекомендация: кому и зачем подойдёт', 'Recomandarea mea: pentru cine și pentru ce', 'My recommendation: who it suits and why'),
    'price_label': ('Цена, MDL', 'Preț, MDL', 'Price, MDL'),
    'visibility': ('Показывать товар', 'Vizibilitatea produsului', 'Product visibility'),
    'translations_check': ('Проверены RU, RO и EN', 'Am verificat RU, RO și EN', 'RU, RO and EN have been reviewed'),
    'save': ('Сохранить товар', 'Salvează produsul', 'Save product'),
    'saved': ('Товар сохранён.', 'Produsul a fost salvat.', 'Product saved.'),
    'archive_title': ('Убрать товар в архив', 'Arhivează produsul', 'Archive product'),
    'archive_note': ('Товар исчезнет из витрины. Его данные и существующие заказы сохранятся.', 'Produsul va dispărea din vitrină. Datele și comenzile existente se păstrează.', 'The product will leave the storefront. Its details and existing orders will remain.'),
    'archive_check': ('Подтверждаю перенос в архив', 'Confirm arhivarea', 'I confirm archiving this product'),
    'archive_action': ('Перенести в архив', 'Arhivează', 'Archive product'),
    'pro_note': ('Новые товары и публикации открывает PRO. Ваши опубликованные товары, фотографии и работа с заказами сохраняются.', 'PRO permite produse noi și publicarea lor. Produsele publicate, fotografiile și gestionarea comenzilor se păstrează.', 'PRO unlocks new products and publishing. Your published products, photos and order management remain yours.'),
    'no_orders': ('Заказы появятся здесь после подтверждения покупателем. В каждой карточке — состав, сумма и удобный покупателю способ связи.', 'Comenzile vor apărea după confirmarea cumpărătorului. Fiecare card include produsele, suma și metoda de contact preferată.', 'Orders appear here after the customer confirms. Each card includes the items, total and preferred contact method.'),
    'order_status': ('Статус заказа', 'Starea comenzii', 'Order status'),
    'status_save': ('Сохранить статус', 'Salvează starea', 'Save status'),
    'status_saved': ('Статус сохранён.', 'Starea a fost salvată.', 'Status saved.'),
    'shop_visible': ('Показывать мой Market', 'Afișează Market-ul meu', 'Show my Market'),
    'shop_name': ('Заголовок витрины', 'Titlul vitrinei', 'Storefront title'),
    'shop_description': ('О моей подборке', 'Despre selecția mea', 'About my collection'),
    'shop_save': ('Сохранить витрину', 'Salvează vitrina', 'Save storefront'),
    'shop_saved': ('Витрина сохранена.', 'Vitrina a fost salvată.', 'Storefront saved.'),
    'preview': ('Открыть мой Market', 'Deschide Market-ul meu', 'Open my Market'),
}

_ERRORS = {
    'price': ('Укажите цену от 0,01 до 1 000 000 MDL, не более двух знаков после запятой.', 'Introduceți un preț între 0,01 și 1 000 000 MDL, cu maximum două zecimale.', 'Enter a price from 0.01 to 1,000,000 MDL, with at most two decimal places.'),
    'name': ('Добавьте название товара.', 'Adăugați denumirea produsului.', 'Add a product name.'),
    'translations': ('Для публикации заполните все поля RU, RO и EN и проверьте переводы.', 'Pentru publicare, completați toate câmpurile RU, RO și EN și verificați traducerile.', 'To publish, complete all RU, RO and EN fields and review the translations.'),
    'photo_size': ('Выберите фотографию до 20 МБ.', 'Alegeți o fotografie de până la 20 MB.', 'Choose a photo up to 20 MB.'),
    'photo_format': ('Нужна корректная неподвижная фотография JPG, PNG или WebP.', 'Este necesară o fotografie statică validă JPG, PNG sau WebP.', 'Choose a valid still JPG, PNG or WebP photo.'),
    'photo_quality': ('Обе стороны фотографии должны быть не меньше 400 px.', 'Ambele laturi trebuie să aibă cel puțin 400 px.', 'Both photo dimensions must be at least 400 px.'),
    'photo_missing': ('Добавьте фотографию товара перед публикацией.', 'Adăugați fotografia produsului înainte de publicare.', 'Add a product photo before publishing.'),
    'stale': ('Данные изменены в другом окне. Обновите страницу перед сохранением.', 'Datele au fost modificate în altă fereastră. Actualizați pagina înainte de salvare.', 'These details changed in another window. Refresh before saving.'),
    'pro': ('Для добавления и публикации нового товара нужен действующий PRO.', 'Aveți nevoie de PRO activ pentru a adăuga și publica un produs nou.', 'Active PRO is required to add and publish a new product.'),
    'unavailable': ('Один из товаров больше не доступен. Уберите его из корзины и проверьте заказ ещё раз.', 'Un produs nu mai este disponibil. Eliminați-l din coș și verificați comanda.', 'An item is no longer available. Remove it from your bag and review the order.'),
    'changed': ('Товар или цена изменились. Проверьте актуальный заказ и подтвердите его ещё раз.', 'Produsul sau prețul s-a schimbat. Verificați comanda actualizată și confirmați din nou.', 'An item or its price changed. Review the updated order before confirming again.'),
    'contacts': ('Укажите имя и корректный номер телефона.', 'Introduceți numele și un număr de telefon valid.', 'Enter your name and a valid phone number.'),
    'email': ('Проверьте email.', 'Verificați adresa de email.', 'Check the email address.'),
    'telegram': ('Укажите имя Telegram в формате @username.', 'Introduceți numele Telegram în format @username.', 'Enter your Telegram username as @username.'),
    'contact_channel': ('Заполните контакт для выбранного способа связи.', 'Completați datele pentru metoda de contact aleasă.', 'Add your details for the selected contact method.'),
    'consent': ('Подтвердите согласие на использование контактов для заказа.', 'Confirmați acordul pentru utilizarea datelor de contact în această comandă.', 'Please agree to the use of your contact details for this order.'),
    'cart': ('Проверьте корзину: до 20 товаров, не больше 100 единиц всего.', 'Verificați coșul: până la 20 de produse, maximum 100 de unități în total.', 'Check your bag: up to 20 different products and 100 units in total.'),
    'closed': ('Мастер закрыл приём заказов в этой подборке.', 'Specialistul a închis comenzile pentru această selecție.', 'Your expert has closed orders for this collection.'),
    'confirmation': ('Подтвердите действие.', 'Confirmați acțiunea.', 'Confirm this action.'),
    'generic': ('Проверьте заполненные поля и повторите действие.', 'Verificați câmpurile și încercați din nou.', 'Check the completed fields and try again.'),
}


def _t(key, locale='ru'):
    return _TEXT.get(key, (key, key, key))[LOCALES.index(locale if locale in LOCALES else 'ru')]


def _error(exc, locale):
    return _ERRORS.get(exc.code, _ERRORS['generic'])[LOCALES.index(locale if locale in LOCALES else 'ru')]


def _owner(settings, locale):
    from scena_i18n import localized_name
    return localized_name(settings, locale)


def _shop_style():
    import streamlit as st
    st.markdown('''<style>
    .shop-intro{padding:clamp(26px,5vw,64px);border-radius:26px;background:radial-gradient(ellipse at 94% 8%,#c6ae7540 0,transparent 47%),linear-gradient(115deg,#211e19,#373027);color:#faf7f0;margin:12px 0 26px;position:relative;overflow:hidden}
    .shop-intro::after{content:"";position:absolute;width:260px;height:260px;border:1px solid #cfb16e30;border-radius:50%;right:-70px;bottom:-150px;pointer-events:none}
    .shop-kicker{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#ccb17c;font-weight:600}
    .shop-intro h1{font-family:Georgia,serif!important;font-size:clamp(34px,5vw,62px)!important;line-height:1.12!important;color:#fffaf0!important;margin:20px 0!important;font-weight:400!important;max-width:850px;overflow-wrap:anywhere}
    .shop-intro p{color:#e0d7c9;font-size:17px;max-width:760px;line-height:1.65;white-space:pre-line}
    .shop-intro .shop-owner{font-size:14px;color:#c8b38e;margin-top:24px;border-top:1px solid #d5c19235;padding-top:20px}
    div[class*="st-key-shop_card_"]{background:radial-gradient(ellipse at 100% 0,#cbb88818,transparent 65%),#fffdf8;border:1px solid #deceb2;border-radius:22px;padding:20px;height:100%}
    div[class*="st-key-shop_card_"] [data-testid="stImage"]{width:100%!important}
    div[class*="st-key-shop_card_"] [data-testid="stImage"] img{height:270px!important;object-fit:contain;width:100%!important;border-radius:14px;background:#f1ede4}
    div[class*="st-key-shop_card_"] h3{font-family:Georgia,serif!important;font-weight:400!important;font-size:25px!important;overflow-wrap:anywhere}
    .shop-price{font-size:21px;font-weight:650;color:#32291c;margin:10px 0}
    .shop-recommendation{background:linear-gradient(130deg,#d5c19629,#e9e4d31a);border-left:3px solid #ad8a46;border-radius:0 18px 18px 0;padding:22px 25px;margin:20px 0;white-space:pre-line;line-height:1.65;overflow-wrap:anywhere}
    .shop-review{padding:22px;background:linear-gradient(130deg,#e5d9bd60,#fffaf3);border:1px solid #d4be90;border-radius:20px;margin:12px 0}
    .shop-review p{overflow-wrap:anywhere;white-space:pre-line}
    .shop-order-note{border-left:3px solid #ad8a46;background:#e7dcc347;padding:16px 20px;border-radius:0 14px 14px 0;line-height:1.65;margin:14px 0 20px;color:#63543a;font-size:16px}
    div[class*="st-key-shop_"] button{min-height:48px!important}
    div[class*="st-key-shop_"] button p{font-size:16px!important}
    [data-testid="stTabs"]:has([class*="st-key-shop_admin_"]) button[role="tab"]{min-height:48px;padding:10px 18px}
    [data-testid="stTabs"]:has([class*="st-key-shop_admin_"]) button[role="tab"] p{font-size:16px!important}
    div[class*="st-key-shop_"] input,div[class*="st-key-shop_"] textarea{font-size:16px!important}
    @media(max-width:600px){.shop-intro{border-radius:18px}.shop-intro p{font-size:16px}div[class*="st-key-shop_card_"]{padding:16px}div[class*="st-key-shop_card_"] [data-testid="stImage"] img{height:260px!important}.shop-review{padding:18px}}
    </style>''', unsafe_allow_html=True)


def _reset_checkout(st):
    for key in ('shop_review', 'shop_contact', 'shop_request'):
        st.session_state.pop(key, None)


def _render_bag(db, locale):
    import streamlit as st
    cart = st.session_state.setdefault('shop_cart', {})
    if not cart:
        return
    st.divider()
    st.subheader(_t('bag', locale))
    for product_id, quantity in list(cart.items()):
        product = get_product(db, product_id, public=True)
        with st.container(key='shop_bag_' + product_id, border=True):
            name = product[f'name_{locale}'] if product else _ERRORS['unavailable'][LOCALES.index(locale)]
            st.write(name)
            left, right = st.columns([2, 1], vertical_alignment='bottom')
            with left:
                selected = st.number_input(_t('units', locale), min_value=1, max_value=99, value=quantity, step=1, key='shop_qty_' + product_id)
                if selected != quantity:
                    cart[product_id] = selected
                    _reset_checkout(st)
                    st.rerun()
                if product:
                    st.caption(f'{money(product["price_cents"])} × {quantity}')
            with right:
                if st.button(_t('remove', locale), key='shop_remove_' + product_id, width='stretch'):
                    del cart[product_id]
                    _reset_checkout(st)
                    st.rerun()
    try:
        quote = quote_cart(db, cart)
    except ShopError as exc:
        st.error(_error(exc, locale))
        return
    st.markdown(f'<p class="shop-price">{html.escape(_t("total",locale))}: {money(quote["total_cents"])}</p>', unsafe_allow_html=True)
    if not st.session_state.get('shop_checkout'):
        if st.button(_t('checkout', locale), key='shop_checkout_start', type='primary', width='stretch'):
            st.session_state['shop_checkout'] = True
            st.rerun()
        return
    review = st.session_state.get('shop_review')
    if review:
        if review['fingerprint'] != quote['fingerprint']:
            _reset_checkout(st)
            st.warning(_error(ShopError('changed'), locale))
            review = None
    if not review:
        st.subheader(_t('contact_title', locale))
        with st.form('shop_contacts'):
            first, second = st.columns(2)
            person = {}
            with first:
                person['name'] = st.text_input(_t('name_label', locale), max_chars=160)
                person['email'] = st.text_input(_t('email_label', locale), max_chars=254)
            with second:
                person['phone'] = st.text_input(_t('phone_label', locale), max_chars=40, placeholder='+373 …')
                person['telegram'] = st.text_input(_t('telegram_label', locale), max_chars=40, placeholder='@username')
            person['preferred_contact'] = st.radio(_t('preferred', locale), ('phone', 'telegram', 'email'), format_func=lambda key: _t(key, locale), horizontal=True)
            person['note'] = st.text_area(_t('note', locale), max_chars=2000, height=80)
            person['consent'] = st.checkbox(_t('consent_label', locale))
            if st.form_submit_button(_t('review', locale), type='primary', width='stretch'):
                try:
                    _contacts(person)
                    st.session_state['shop_review'] = quote_cart(db, cart)
                    st.session_state['shop_contact'] = person
                    st.session_state['shop_request'] = str(uuid.uuid4())
                    st.rerun()
                except ShopError as exc:
                    st.error(_error(exc, locale))
        return
    person = st.session_state['shop_contact']
    st.subheader(_t('review_title', locale))
    lines = ''.join(f'<p>{html.escape(item[f"name_{locale}"])} · {item["quantity"]} × {money(item["price_cents"])}</p>' for item in review['items'])
    contact = person['phone'] if person['preferred_contact'] == 'phone' else person[person['preferred_contact']]
    st.markdown(f'<div class="shop-review">{lines}<p><strong>{html.escape(_t("total",locale))}: {money(review["total_cents"])}</strong></p><p>{html.escape(person["name"])} · {html.escape(contact)}</p></div>', unsafe_allow_html=True)
    if person['note']:
        st.write(person['note'])
    st.markdown(f'<div class="shop-order-note">{html.escape(_t("terms",locale))}</div>', unsafe_allow_html=True)
    if st.button(_t('final', locale), type='primary', width='stretch', key='shop_final_confirm'):
        try:
            order = create_order(db, dict(cart), person, reviewed_quote=review['fingerprint'], request_key=st.session_state['shop_request'], locale=locale)
            st.session_state['shop_receipt'] = {'reference': order['reference'], 'total_cents': order['total_cents']}
            st.session_state['shop_cart'] = {}
            st.session_state.pop('shop_checkout', None)
            _reset_checkout(st)
            st.rerun()
        except ShopError as exc:
            st.error(_error(exc, locale))
            if exc.code == 'changed':
                _reset_checkout(st)
    if st.button(_t('change', locale), key='shop_change_order'):
        _reset_checkout(st)
        st.rerun()


def render_shop(db_path, app_dir, settings, locale='ru'):
    import streamlit as st
    locale = locale if locale in LOCALES else 'ru'
    app_dir = Path(app_dir)
    _shop_style()
    if settings.get('shop_enabled', '1') != '1':
        st.info(_t('closed', locale))
        st.link_button(_t('scene', locale), f'?page=scene&lang={locale}')
        return
    with st.container(key='shop_public'):
        title = settings.get(f'shop_title_{locale}') or SHOP_DEFAULT_SETTINGS[f'shop_title_{locale}']
        description = settings.get(f'shop_description_{locale}') or SHOP_DEFAULT_SETTINGS[f'shop_description_{locale}']
        st.markdown(f'<section class="shop-intro"><div class="shop-kicker">SCENA · MARKET</div><h1>{html.escape(title)}</h1><p>{html.escape(description)}</p><div class="shop-owner">{html.escape(_owner(settings,locale))} · {html.escape(_t("owner_note",locale))}</div></section>', unsafe_allow_html=True)
        receipt = st.session_state.get('shop_receipt')
        if receipt:
            st.success(f'{_t("success",locale)} · {receipt["reference"]}')
            st.write(_t('success_note', locale))
            st.write(money(receipt['total_cents']))
            if st.button(_t('continue', locale), key='shop_finish_receipt'):
                del st.session_state['shop_receipt']
                st.session_state.pop('shop_product', None)
                st.rerun()
            return
        products = list_products(db_path, public=True)
        if not products:
            left, right = st.columns([1, 1.6], vertical_alignment='center')
            with left:
                candidate = settings.get('scene_hero_image') or settings.get('profile_image') or 'media/scena-v13/professional-portrait.webp'
                if path := local_photo(app_dir, candidate):
                    st.image(str(path), width='stretch')
            with right:
                st.subheader(_t('owner_edit', locale))
                st.write(_t('empty', locale))
                st.link_button(_t('scene', locale), f'?page=scene&lang={locale}')
            return
        product_id = st.session_state.get('shop_product')
        detail = next((p for p in products if p['id'] == product_id), None)
        if detail:
            if st.button(_t('back', locale), key='shop_back_catalog'):
                st.session_state.pop('shop_product', None)
                st.rerun()
            photo_column, text_column = st.columns([1.05, 1], gap='large')
            with photo_column:
                if path := local_photo(app_dir, detail['image']):
                    st.image(str(path), width='stretch')
            with text_column:
                st.caption(detail[f'category_{locale}'])
                st.subheader(detail[f'name_{locale}'])
                st.markdown(f'<p class="shop-price">{money(detail["price_cents"])}</p>', unsafe_allow_html=True)
                st.write(detail[f'description_{locale}'])
                st.markdown(f'<div class="shop-recommendation"><strong>{html.escape(_t("why",locale))}</strong><br>{html.escape(detail[f"recommendation_{locale}"])}</div>', unsafe_allow_html=True)
                if st.button(_t('add', locale), type='primary', width='stretch', key='shop_add_detail'):
                    _add_to_bag(st, detail['id'], locale)
        else:
            query = st.text_input(_t('search', locale), key='shop_search')
            categories = sorted({product[f'category_{locale}'] for product in products})
            category = st.pills(_t('categories', locale), [''] + categories, default='', format_func=lambda value: value or _t('all', locale), key=f'shop_categories_{locale}')
            filtered = [product for product in products if (not category or product[f'category_{locale}'] == category) and (not query.strip() or query.casefold().strip() in (product[f'name_{locale}'] + ' ' + product[f'description_{locale}'] + ' ' + product[f'category_{locale}']).casefold())]
            if not filtered:
                st.info(_t('none', locale))
            for offset in range(0, len(filtered), 2):
                cols = st.columns(2, gap='medium')
                for col, product in zip(cols, filtered[offset:offset + 2]):
                    with col, st.container(key='shop_card_' + product['id']):
                        if path := local_photo(app_dir, product['image']):
                            st.image(str(path), width='stretch')
                        st.caption(product[f'category_{locale}'])
                        st.subheader(product[f'name_{locale}'])
                        st.write(product[f'recommendation_{locale}'][:220] + ('…' if len(product[f'recommendation_{locale}']) > 220 else ''))
                        st.markdown(f'<p class="shop-price">{money(product["price_cents"])}</p>', unsafe_allow_html=True)
                        if st.button(_t('details', locale), key='shop_open_' + product['id'], width='stretch'):
                            st.session_state['shop_product'] = product['id']
                            st.rerun()
                        if st.button(_t('add', locale), key='shop_add_' + product['id'], type='primary', width='stretch'):
                            _add_to_bag(st, product['id'], locale)
        _render_bag(db_path, locale)


def _add_to_bag(st, product_id, locale):
    cart = dict(st.session_state.setdefault('shop_cart', {}))
    cart[product_id] = cart.get(product_id, 0) + 1
    try:
        _cart(cart)
        st.session_state['shop_cart'] = cart
        _reset_checkout(st)
        st.toast(_t('added', locale))
    except ShopError as exc:
        st.error(_error(exc, locale))


def render_shop_admin(db_path, app_dir, settings, locale='ru'):
    import streamlit as st
    locale = locale if locale in LOCALES else 'ru'
    app_dir = Path(app_dir)
    _shop_style()
    st.subheader(_t('title', locale))
    st.write(_t('admin_intro', locale))
    if message := st.session_state.pop('shop_admin_notice', None):
        st.success(message)
    product_tab, order_tab, settings_tab = st.tabs([_t(key, locale) for key in ('products_tab', 'orders_tab', 'settings_tab')])
    with product_tab, st.container(key='shop_admin_products'):
        active = _is_pro(db_path)
        if not active:
            st.info(_t('pro_note', locale))
        products = list_products(db_path)
        by_id = {product['id']: product for product in products}
        options = ([''] if active else []) + list(by_id)
        if options:
            next_selection = st.session_state.pop('shop_admin_select_next', None)
            if next_selection in options:
                st.session_state['shop_admin_product_select'] = next_selection
            selected = st.selectbox(_t('pick', locale), options, format_func=lambda value: _t('new_product', locale) if not value else f'{by_id[value][f"name_{locale}"] or by_id[value]["name_ru"]} · {_t(by_id[value]["status"],locale)}', key='shop_admin_product_select')
            source_key = 'shop_admin_source_' + (selected or 'new')
            if source_key not in st.session_state:
                st.session_state[source_key] = dict(by_id[selected]) if selected else {field: '' for field in PRODUCT_FIELDS}
            source = st.session_state[source_key]
            rev = source.get('revision', 0)
            if source.get('image') and (path := local_photo(app_dir, source['image'])):
                st.image(str(path), width=240)
            with st.form(f'shop_product_editor_{selected or "new"}_{rev}'):
                upload = st.file_uploader(_t('photo_label', locale), type=['jpg', 'jpeg', 'png', 'webp'])
                st.caption(_t('photo_hint', locale))
                values = {}
                history = product_photo_history(app_dir, source)
                if history:
                    restore = st.selectbox(_t('photo_restore', locale), [''] + history, format_func=lambda value: _t('photo_current',locale) if not value else f'{_t("photo_version",locale)} {history.index(value) + 1}')
                    if restore:
                        values['image'] = restore
                        if old_photo := local_photo(app_dir, restore):
                            st.image(str(old_photo), width=180)
                lang_tabs = st.tabs(['RU', 'RO', 'EN'])
                for language, lang_tab in zip(LOCALES, lang_tabs):
                    with lang_tab:
                        for field in ('name', 'category'):
                            values[f'{field}_{language}'] = st.text_input(f'{_t("product_name" if field == "name" else field,locale)} {language.upper()}', value=source.get(f'{field}_{language}', ''), max_chars=160)
                        for field in ('description', 'recommendation'):
                            values[f'{field}_{language}'] = st.text_area(f'{_t(field,locale)} {language.upper()}', value=source.get(f'{field}_{language}', ''), max_chars=2400, height=110)
                first, second = st.columns(2)
                with first:
                    values['price'] = st.text_input(_t('price_label', locale), value=f'{source["price_cents"] / 100:.2f}' if 'price_cents' in source else '', placeholder='250,00')
                with second:
                    states = ['draft', 'published', 'hidden']
                    if not active and source.get('status') != 'published':
                        states.remove('published')
                    current_state = source.get('status', 'draft')
                    values['status'] = st.selectbox(_t('visibility', locale), states, index=states.index(current_state) if current_state in states else 0, format_func=lambda value: _t(value, locale))
                reviewed = st.checkbox(_t('translations_check', locale), value=source.get('status') == 'published')
                if st.form_submit_button(_t('save', locale), type='primary', width='stretch'):
                    try:
                        if values['status'] == 'published' and not reviewed:
                            raise ShopError('translations')
                        saved = save_product(db_path, app_dir, values, product_id=selected or None, expected_revision=source.get('revision'), upload=upload.getvalue() if upload else None)
                        st.session_state.pop(source_key, None)
                        st.session_state['shop_admin_select_next'] = saved['id']
                        st.session_state['shop_admin_notice'] = _t('saved', locale)
                        st.rerun()
                    except ShopError as exc:
                        st.error(_error(exc, locale))
            if selected and source.get('status') != 'archived':
                with st.expander(_t('archive_title', locale)):
                    st.write(_t('archive_note', locale))
                    checked = st.checkbox(_t('archive_check', locale), key='shop_archive_check_' + selected)
                    if st.button(_t('archive_action', locale), key='shop_archive_' + selected, disabled=not checked):
                        try:
                            archive_product(db_path, selected, expected_revision=source['revision'], confirmed=checked)
                            st.session_state.pop(source_key, None)
                            st.session_state['shop_admin_notice'] = _t('archived', locale)
                            st.rerun()
                        except ShopError as exc:
                            st.error(_error(exc, locale))
    with order_tab, st.container(key='shop_admin_orders'):
        orders = list_orders(db_path)
        if not orders:
            st.info(_t('no_orders', locale))
        for order in orders:
            with st.expander(f'{order["reference"]} · {order["customer_name"]} · {money(order["total_cents"])} · {_t(order["status"],locale)}', expanded=order['status'] == 'new'):
                st.caption(datetime.fromisoformat(order['created_at']).astimezone(ZoneInfo('Europe/Chisinau')).strftime('%d.%m.%Y · %H:%M'))
                for item in order['items']:
                    st.write(f'{item[f"name_{locale}"]} · {item["quantity"]} × {money(item["unit_price_cents"])}')
                st.write(f'{_t("phone_label",locale)}: {order["phone"]}')
                for field in ('email', 'telegram'):
                    if order[field]:
                        st.write(f'{field.title()}: {order[field]}')
                st.write(f'{_t("preferred",locale)} {_t(order["preferred_contact"],locale)}')
                if order['note']:
                    st.write(order['note'])
                with st.form('shop_order_status_' + order['id'] + '_' + str(order['revision'])):
                    status = st.selectbox(_t('order_status', locale), ORDER_STATES, index=ORDER_STATES.index(order['status']), format_func=lambda value: _t(value, locale))
                    if st.form_submit_button(_t('status_save', locale)):
                        try:
                            update_order_status(db_path, order['id'], status, expected_revision=order['revision'])
                            st.session_state['shop_admin_notice'] = _t('status_saved', locale)
                            st.rerun()
                        except ShopError as exc:
                            st.error(_error(exc, locale))
    with settings_tab, st.container(key='shop_admin_storefront'):
        with st.form('shop_storefront_settings'):
            updates = {'shop_enabled': '1' if st.checkbox(_t('shop_visible', locale), value=settings.get('shop_enabled', '1') == '1') else '0'}
            for language, tab in zip(LOCALES, st.tabs(['RU', 'RO', 'EN'])):
                with tab:
                    for field in ('title', 'description'):
                        key = f'shop_{field}_{language}'
                        label = _t('shop_name' if field == 'title' else 'shop_description', locale) + ' ' + language.upper()
                        if field == 'title':
                            updates[key] = st.text_input(label, value=settings.get(key, SHOP_DEFAULT_SETTINGS[key]), max_chars=160)
                        else:
                            updates[key] = st.text_area(label, value=settings.get(key, SHOP_DEFAULT_SETTINGS[key]), max_chars=1600, height=100)
            if st.form_submit_button(_t('shop_save', locale), type='primary', width='stretch'):
                from scena_core import save_settings
                save_settings(db_path, updates)
                st.session_state['shop_admin_notice'] = _t('shop_saved', locale)
                st.rerun()
        st.link_button(_t('preview', locale), f'?page=shop&lang={locale}')
