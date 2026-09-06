"""Durable local publications. No network effects occur in storage operations."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import sqlite3
import uuid
import warnings
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit


class PublicationValidationError(ValueError):
    """An actionable publication validation error."""


TEXT_FIELDS = ("title_ru", "title_ro", "title_en", "body_ru", "body_ro", "body_en", "image_url", "link_url",
               "original_image_path", "price_text", "cta_label_ru", "cta_label_ro", "cta_label_en", "cta_url",
               "frame_style", "frame_format")
BOOL_FIELDS = ("translations_approved", "show_scene", "show_professional", "show_model")
POST_FIELDS = ("title_ru", "title_ro", "body_ru", "body_ro", "image_url", "link_url", *BOOL_FIELDS)
DESTINATIONS = {"scene": "show_scene", "professional": "show_professional", "model": "show_model"}
FRAME_STYLES = {"auto", "ivory", "noir", "sand", "mist"}
FRAME_FORMATS = {"portrait": (1080, 1350), "tall": (1080, 1440), "square": (1080, 1080), "story": (1080, 1920)}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _defaults():
    return {**dict.fromkeys(TEXT_FIELDS, ""), **dict.fromkeys(BOOL_FIELDS, False), "show_scene": True,
            "kind": "story", "frame_style": "auto", "frame_format": "portrait"}


def initialize_publications(connection):
    """Additive, idempotent migration; caller owns the encompassing transaction."""
    for key in ("installation_id", "owner_id"):
        connection.execute("INSERT OR IGNORE INTO app_meta(key,value) VALUES (?,?)", (key, str(uuid.uuid4())))
    connection.execute("INSERT OR IGNORE INTO app_meta(key,value) VALUES ('publications_schema_version','1')")
    connection.execute("""CREATE TABLE IF NOT EXISTS publication_records (
        post_id INTEGER PRIMARY KEY REFERENCES posts(id), public_id TEXT NOT NULL UNIQUE,
        revision INTEGER NOT NULL, public_revision INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL, draft_json TEXT NOT NULL, published_json TEXT,
        updated_at TEXT NOT NULL)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS publication_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL REFERENCES posts(id),
        revision INTEGER NOT NULL, snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(post_id,revision))""")
    connection.execute("""CREATE TABLE IF NOT EXISTS publication_channel_drafts (
        post_id INTEGER NOT NULL REFERENCES posts(id), channel TEXT NOT NULL,
        data_json TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(post_id,channel))""")
    connection.execute("""CREATE TABLE IF NOT EXISTS publication_deliveries (
        id TEXT PRIMARY KEY, post_id INTEGER NOT NULL REFERENCES posts(id),
        channel TEXT NOT NULL, snapshot_json TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
        status TEXT NOT NULL, result_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(post_id,channel,snapshot_hash))""")
    cursor = connection.execute("SELECT p.* FROM posts p LEFT JOIN publication_records r ON r.post_id=p.id WHERE r.post_id IS NULL")
    names = [x[0] for x in cursor.description]
    for values in cursor.fetchall():
        row = dict(zip(names, values))
        snapshot = _defaults()
        snapshot.update({k: row[k] for k in POST_FIELDS})
        public = bool(row["active"])
        connection.execute("INSERT INTO publication_records VALUES (?,?,?,?,?,?,?,?)", (
            row["id"], str(uuid.uuid4()), 1, 1 if public else 0,
            "published" if public else "draft", _json(snapshot), _json(snapshot) if public else None, _now()))
        connection.execute("INSERT INTO publication_versions(post_id,revision,snapshot_json,created_at) VALUES (?,?,?,?)", (row["id"], 1, _json(snapshot), _now()))


@contextmanager
def _db(db_path):
    connection = sqlite3.connect(str(db_path), timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            initialize_publications(connection)
        yield connection
    finally:
        connection.close()


def get_installation_identity(db_path):
    with _db(db_path) as connection:
        values = dict(connection.execute("SELECT key,value FROM app_meta WHERE key IN ('installation_id','owner_id','publications_schema_version')"))
    return {**values, "schema_version": 1}


def _record(connection, post_id):
    record = connection.execute("SELECT * FROM publication_records WHERE post_id=?", (int(post_id),)).fetchone()
    if record is None:
        raise PublicationValidationError("Публикация не найдена.")
    return record


def _editable(record):
    snapshot = json.loads(record["draft_json"])
    return {**_defaults(), **snapshot, "id": record["post_id"], "post_id": record["post_id"],
            "needs_frame_refresh": bool(snapshot.get("original_image_path")) and "frame_style" not in snapshot,
            "public_id": record["public_id"], "revision": record["revision"],
            "public_revision": record["public_revision"], "status": record["status"],
            "updated_at": record["updated_at"], "has_unpublished_changes": record["revision"] != record["public_revision"]}


def save_draft(db_path, post_id=None, **fields):
    """Merge editable fields and persist a new immutable revision; never publish."""
    unexpected = set(fields) - set(TEXT_FIELDS) - set(BOOL_FIELDS) - {"kind", "expected_revision"}
    if unexpected:
        raise PublicationValidationError("Неизвестное поле публикации: " + ", ".join(sorted(unexpected)))
    with _db(db_path) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        record = _record(connection, post_id) if post_id is not None else None
        if record and fields.get("expected_revision") is not None and int(fields["expected_revision"]) != record["revision"]:
            raise PublicationValidationError("Черновик изменён. Откройте свежую версию.")
        snapshot = {**_defaults(), **json.loads(record["draft_json"])} if record else _defaults()
        for key in TEXT_FIELDS:
            if key in fields:
                snapshot[key] = str(fields[key] or "").strip()
        for key in BOOL_FIELDS:
            if key in fields:
                snapshot[key] = bool(fields[key])
        if "kind" in fields:
            snapshot["kind"] = str(fields["kind"])
        if snapshot["kind"] not in {"story", "offer"}:
            raise PublicationValidationError("Выберите историю или предложение.")
        if snapshot["frame_style"] not in FRAME_STYLES or snapshot["frame_format"] not in FRAME_FORMATS:
            raise PublicationValidationError("Выберите оформление и формат публикации.")
        if record and any(key in fields and snapshot[key] != json.loads(record["draft_json"]).get(key) for key in ("body_ru", "body_ro", "body_en", "title_ru", "title_ro", "title_en", "cta_label_ru", "cta_label_ro", "cta_label_en")) and "translations_approved" not in fields:
            snapshot["translations_approved"] = False
        stamp = _now()
        if record:
            revision = record["revision"] + 1
            connection.execute("UPDATE publication_records SET revision=?,draft_json=?,updated_at=? WHERE post_id=?", (revision, _json(snapshot), stamp, post_id))
        else:
            cursor = connection.execute("INSERT INTO posts(created_at) VALUES (?)", (stamp,))
            post_id = cursor.lastrowid
            revision = 1
            connection.execute("INSERT INTO publication_records VALUES (?,?,?,?,?,?,?,?)", (post_id, str(uuid.uuid4()), revision, 0, "draft", _json(snapshot), None, stamp))
        connection.execute("INSERT INTO publication_versions(post_id,revision,snapshot_json,created_at) VALUES (?,?,?,?)", (post_id, revision, _json(snapshot), stamp))
        return _editable(_record(connection, post_id))


def get_draft(db_path, post_id):
    with _db(db_path) as connection:
        return _editable(_record(connection, post_id))


def get_private_export_source(db_path, post_id):
    """Owner workspace only: exact published image/original even with a newer draft.

    Do not use this on public routes. Public get_publication() hides originals.
    """
    with _db(db_path) as connection:
        record = _record(connection, post_id)
        snapshot = record["published_json"] if record["status"] == "published" else record["draft_json"]
        return {**_defaults(), **json.loads(snapshot), "public_id": record["public_id"], "status": record["status"]}


def list_publications(db_path, destination=None, include_archived=True):
    if destination is not None and destination not in DESTINATIONS:
        raise PublicationValidationError("Неизвестное место публикации.")
    with _db(db_path) as connection:
        records = [_editable(row) for row in connection.execute("SELECT * FROM publication_records ORDER BY updated_at DESC,post_id DESC")]
    return [row for row in records if (include_archived or row["status"] != "archived") and (destination is None or row[DESTINATIONS[destination]])]


def publish_local(db_path, post_id, expected_revision, *, media_root=None):
    with _db(db_path) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        record = _record(connection, post_id)
        if record["revision"] != int(expected_revision):
            raise PublicationValidationError("Предпросмотр устарел. Проверьте свежую версию.")
        snapshot = json.loads(record["draft_json"])
        if not (snapshot["body_ru"] and snapshot["body_ro"] and snapshot["translations_approved"]):
            raise PublicationValidationError("Перед публикацией заполните и подтвердите версии RU и RO.")
        if (snapshot.get("title_en") or snapshot.get("cta_label_en")) and not snapshot.get("body_en"):
            raise PublicationValidationError("Добавьте текст EN или очистите английские поля, чтобы сохранить только RU и RO.")
        if snapshot["kind"] == "offer" and not snapshot["price_text"]:
            raise PublicationValidationError("Укажите актуальную цену предложения.")
        if not any(snapshot[key] for key in DESTINATIONS.values()):
            raise PublicationValidationError("Выберите, где показать публикацию.")
        _validate_publication_image(snapshot, Path(media_root) if media_root else Path(db_path).resolve().parent)
        connection.execute("UPDATE posts SET " + ",".join(key + "=?" for key in POST_FIELDS) + ",active=1 WHERE id=?", [snapshot[key] for key in POST_FIELDS] + [post_id])
        connection.execute("UPDATE publication_records SET public_revision=revision,status='published',published_json=draft_json,updated_at=? WHERE post_id=?", (_now(), post_id))
        return _editable(_record(connection, post_id))


def get_publication(db_path, public_id, include_private=False):
    with _db(db_path) as connection:
        record = connection.execute("SELECT * FROM publication_records WHERE public_id=?", (str(public_id),)).fetchone()
        if record is None:
            return None
        if include_private:
            return _editable(record)
        if record["status"] == "draft" or record["public_revision"] == 0:
            return None
        author = connection.execute("SELECT value FROM profile_settings WHERE key='master_name'").fetchone()
        created = connection.execute("SELECT created_at FROM posts WHERE id=?", (record["post_id"],)).fetchone()
        result = {"id": record["post_id"], "post_id": record["post_id"], "public_id": record["public_id"], "status": record["status"], "author_name": author[0] if author else "", "public_revision": record["public_revision"], "created_at": created[0], "updated_at": record["updated_at"]}
        if record["status"] == "published":
            snapshot = json.loads(record["published_json"])
            snapshot.pop("original_image_path", None)
            result.update(snapshot)
        return result


def archive_publication(db_path, post_id):
    with _db(db_path) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        _record(connection, post_id)
        connection.execute("UPDATE publication_records SET status='archived',updated_at=? WHERE post_id=?", (_now(), post_id))
        connection.execute("UPDATE posts SET active=0 WHERE id=?", (post_id,))
        return _editable(_record(connection, post_id))


def list_versions(db_path, post_id):
    with _db(db_path) as connection:
        _record(connection, post_id)
        return [{"id": row["id"], "revision": row["revision"], "created_at": row["created_at"], "snapshot": json.loads(row["snapshot_json"])}
                for row in connection.execute("SELECT * FROM publication_versions WHERE post_id=? ORDER BY revision DESC", (post_id,))]


def restore_version(db_path, post_id, revision):
    with _db(db_path) as connection:
        row = connection.execute("SELECT snapshot_json FROM publication_versions WHERE post_id=? AND revision=?", (post_id, revision)).fetchone()
        if row is None:
            raise PublicationValidationError("Версия не найдена.")
        snapshot = json.loads(row[0])
    # Restoring never changes the existing public revision or archive status.
    snapshot["translations_approved"] = False
    return save_draft(db_path, post_id, **snapshot)


def _open_original(data):
    """Validate/normalize the working copy; the stored original stays byte exact."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not isinstance(data, bytes) or not data or len(data) > 20 * 1024 * 1024:
        raise PublicationValidationError("Добавьте JPG, PNG или WEBP размером до 20 МБ.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as opened:
                image_format = opened.format
                if image_format not in {"JPEG", "PNG", "WEBP"}:
                    raise PublicationValidationError("Поддерживаются JPG, PNG и WEBP.")
                if getattr(opened, "n_frames", 1) != 1:
                    raise PublicationValidationError("Для публикации выберите одну неподвижную фотографию.")
                if opened.width * opened.height > 40_000_000:
                    raise PublicationValidationError("Фотография слишком велика: максимум 40 мегапикселей.")
                opened.load()
                normalized = ImageOps.exif_transpose(opened).convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise PublicationValidationError("Файл не удалось прочитать как безопасную фотографию.") from error
    return normalized, image_format


def _frame_background(image, style):
    """Quiet, neutral surfaces; auto follows the photo's edge luminance."""
    palette = {"ivory": (250, 248, 243), "noir": (23, 23, 22),
               "sand": (231, 216, 192), "mist": (226, 232, 229)}
    if style != "auto":
        return palette[style]
    sample = image.convert("RGB").resize((32, 32))
    edge = [sample.getpixel((x, y)) for y in range(32) for x in range(32)
            if x < 3 or x > 28 or y < 3 or y > 28]
    median = tuple(sorted(pixel[c] for pixel in edge)[len(edge)//2] for c in range(3))
    luminance = sum(a*b for a,b in zip(median, (.2126, .7152, .0722)))
    base = (27, 27, 25) if luminance < 76 else (247, 244, 237)
    return tuple(round(.86*base[c] + .14*median[c]) for c in range(3))


def render_publication_image(app_dir, data, *, frame_style="auto", frame_format="portrait"):
    """Deterministic layout, no retouching/cropping: only a SCENA label on photo.

    Feed 4:5, native Instagram 3:4, square, and Story 9:16 are separate exports.
    The caption contains the person's name, text, price and post URL.
    """
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    if frame_style not in FRAME_STYLES or frame_format not in FRAME_FORMATS:
        raise PublicationValidationError("Выберите оформление и формат публикации.")
    normalized, _ = _open_original(data)
    width, height = FRAME_FORMATS[frame_format]
    surface = _frame_background(normalized, frame_style)
    canvas = Image.new("RGB", (width, height), surface)
    margin = 24
    # Story chrome occupies top/bottom on the destination app. Keep photo/mark
    # within the generous central area, without claiming any text is clickable.
    vertical_margin = 180 if frame_format == "story" else margin
    fitted = ImageOps.contain(normalized, (width-2*margin, height-2*vertical_margin), Image.Resampling.LANCZOS)
    photo_x, photo_y = (width-fitted.width)//2, (height-fitted.height)//2
    canvas.paste(fitted, (photo_x, photo_y), fitted)
    # Visible editorial signature near the photo's top edge, never a funeral-like footer.
    overlay = Image.new("RGBA", canvas.size)
    draw = ImageDraw.Draw(overlay)
    font_path = Path(app_dir) / "media/model-slider/P052-Roman.otf"
    try:
        font = ImageFont.truetype(str(font_path), 34)
    except OSError:
        font = ImageFont.load_default(size=34)
    label_x, label_y = photo_x+24, photo_y+24
    # Contrasting opaque-enough capsule makes SCENA readable on light/dark photos.
    dark = sum(surface) < 220
    bg = (23, 23, 22, 228) if dark else (253, 251, 246, 236)
    fg = (249, 246, 236, 255) if dark else (38, 35, 30, 255)
    text_width = draw.textlength("S C E N A", font=font)
    box_width = int(text_width)+38
    draw.rounded_rectangle((label_x, label_y, label_x+box_width, label_y+62), radius=9, fill=bg)
    draw.text((label_x+19, label_y+31), "S C E N A", font=font, anchor="lm", fill=fg)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    output = BytesIO()
    canvas.save(output, format="JPEG", quality=94, optimize=True, subsampling=0)
    return output.getvalue()


def _publication_folder(app_dir):
    base = Path(app_dir).resolve()
    media = base / "media"
    root = media / "publications"
    if media.is_symlink() or root.is_symlink():
        raise PublicationValidationError("Выберите медиатеку этой установки.")
    root.mkdir(parents=True, exist_ok=True)
    if not root.resolve().is_relative_to(base):
        raise PublicationValidationError("Выберите медиатеку этой установки.")
    folder = root / str(uuid.uuid4())
    folder.mkdir(exist_ok=False)
    return base, folder


def store_publication_image(app_dir, data, filename, *, frame_style="auto", frame_format="portrait"):
    """Keep exact original bytes plus a unique photo-first labelled derivative."""
    normalized, image_format = _open_original(data)
    rendered = render_publication_image(app_dir, data, frame_style=frame_style, frame_format=frame_format)
    width, height = normalized.size
    problems = ["Малая сторона меньше 600 px: замените фотографию перед публикацией."] if min(width, height) < 600 else []
    base, folder = _publication_folder(app_dir)
    suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image_format]
    original = folder / ("original"+suffix)
    derivative = folder / "scena-publication.jpg"
    with original.open("xb") as output:
        output.write(data)
    with derivative.open("xb") as output:
        output.write(rendered)
    return {"original_path": str(original), "image_path": str(derivative),
            "original_url": original.relative_to(base).as_posix(),
            "image_url": derivative.relative_to(base).as_posix(),
            "original_image_path": original.relative_to(base).as_posix(),
            "width": width, "height": height, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "warnings": problems,
            "frame_style": frame_style, "frame_format": frame_format,
            "publication_allowed": not problems}


def managed_original(app_dir, relative):
    """Only local raster originals from this publication archive are accepted."""
    base = Path(app_dir).resolve()
    original = (base/str(relative)).resolve()
    root = base/"media"/"publications"
    if root.is_symlink() or not original.is_relative_to(root) or not original.is_file() or original.name not in {"original.jpg", "original.png", "original.webp"}:
        raise PublicationValidationError("Оригинал фотографии удалён. Загрузите фотографию заново.")
    if original.stat().st_size > 20*1024*1024:
        raise PublicationValidationError("Оригинал превышает 20 МБ.")
    return original


def restyle_publication_image(app_dir, original_image_path, *, frame_style="auto", frame_format="portrait"):
    """New immutable derivative; old post, history and original are untouched."""
    original = managed_original(app_dir, original_image_path)
    rendered = render_publication_image(app_dir, original.read_bytes(), frame_style=frame_style, frame_format=frame_format)
    base, folder = _publication_folder(app_dir)
    derivative = folder/"scena-publication.jpg"
    with derivative.open("xb") as output:
        output.write(rendered)
    return {"image_url": derivative.relative_to(base).as_posix(), "original_image_path": original.relative_to(base).as_posix(),
            "frame_style": frame_style, "frame_format": frame_format}


def _validate_publication_image(snapshot, media_root):
    """Enforce quality for new managed uploads; retain legacy external media."""
    if not snapshot.get("original_image_path"):
        return
    from PIL import Image, UnidentifiedImageError

    base = Path(media_root).resolve()
    original = (base / snapshot["original_image_path"]).resolve()
    derivative = (base / snapshot["image_url"]).resolve()
    if not original.is_relative_to(base / "media") or not derivative.is_relative_to(base / "media"):
        raise PublicationValidationError("Фотография должна находиться в медиатеке этой установки.")
    if not original.is_file() or not derivative.is_file():
        raise PublicationValidationError("Фотография удалена. Выберите замену перед публикацией.")
    try:
        with Image.open(original) as image:
            if min(image.size) < 600:
                raise PublicationValidationError("Малая сторона оригинала меньше 600 px. Замените фотографию; оригинал сохранён.")
        with Image.open(derivative) as image:
            if image.size != FRAME_FORMATS.get(snapshot.get("frame_format", "portrait")):
                raise PublicationValidationError("Размер фотографии не совпадает с выбранным форматом. Сохраните оформление заново.")
    except (OSError, UnidentifiedImageError) as error:
        raise PublicationValidationError("Оригинал фотографии не читается. Выберите замену.") from error


def _channel(channel):
    if channel not in {"facebook", "instagram"}:
        raise PublicationValidationError("Доступны только Facebook и Instagram.")
    return channel


def _public_https(value):
    clean = str(value or "").strip()
    try:
        parsed = urlsplit(clean)
        host = (parsed.hostname or "").lower()
        if (parsed.scheme != "https" or not host or parsed.username or parsed.password
                or host == "localhost" or host.endswith((".localhost", ".local", ".internal"))
                or "." not in host or parsed.port not in (None, 443)
                or re.search(r"(?i)(token|secret|password|api_key)=", parsed.query)):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError()
        if any(ord(char) < 32 for char in clean):
            raise ValueError()
    except (ValueError, TypeError) as error:
        raise PublicationValidationError("Нужна публичная HTTPS-ссылка без пароля и токенов.") from error
    return clean


def save_channel_draft(db_path, post_id, channel, caption, locale="ru", image_url="", return_url="", account_id=""):
    _channel(channel)
    if locale not in {"ru", "ro", "en"}:
        raise PublicationValidationError("Выберите язык RU, RO или EN.")
    data = {"post_id": int(post_id), "channel": channel, "caption": str(caption or "").strip(),
            "locale": locale, "image_url": _public_https(image_url) if image_url else "",
            "return_url": _public_https(return_url) if return_url else "", "account_id": str(account_id or "").strip()}
    if data["account_id"] and not re.fullmatch(r"[0-9]{1,40}", data["account_id"]):
        raise PublicationValidationError("Нужен идентификатор аккаунта, не токен доступа.")
    with _db(db_path) as connection, connection:
        _record(connection, post_id)
        connection.execute("INSERT INTO publication_channel_drafts VALUES (?,?,?,?) ON CONFLICT(post_id,channel) DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at", (post_id, channel, _json(data), _now()))
    return data


def get_channel_draft(db_path, post_id, channel):
    _channel(channel)
    with _db(db_path) as connection:
        row = connection.execute("SELECT data_json,updated_at FROM publication_channel_drafts WHERE post_id=? AND channel=?", (post_id, channel)).fetchone()
    return {**json.loads(row[0]), "updated_at": row[1]} if row else None


def list_channel_drafts(db_path, post_id):
    with _db(db_path) as connection:
        return [{**json.loads(row[0]), "updated_at": row[1]} for row in connection.execute("SELECT data_json,updated_at FROM publication_channel_drafts WHERE post_id=? ORDER BY channel", (post_id,))]


def _delivery(row):
    if row is None:
        raise PublicationValidationError("Подготовленная отправка не найдена.")
    return {"id": row["id"], "post_id": row["post_id"], "channel": row["channel"],
            **json.loads(row["result_json"]), "status": row["status"],
            "snapshot": json.loads(row["snapshot_json"]), "snapshot_hash": row["snapshot_hash"],
            "expected_hash": row["snapshot_hash"], "created_at": row["created_at"], "updated_at": row["updated_at"]}


def get_delivery(db_path, delivery_id):
    with _db(db_path) as connection:
        return _delivery(connection.execute("SELECT * FROM publication_deliveries WHERE id=?", (str(delivery_id),)).fetchone())


def list_deliveries(db_path, post_id=None):
    with _db(db_path) as connection:
        query = "SELECT * FROM publication_deliveries"
        args = ()
        if post_id is not None:
            query += " WHERE post_id=?"
            args = (int(post_id),)
        return [_delivery(row) for row in connection.execute(query + " ORDER BY created_at DESC", args)]


def prepare_delivery(db_path, post_id, channel, caption, image_url, return_url, account_id, configuration_fingerprint=""):
    """Persist the exact preview. Preparation never contacts a social network."""
    _channel(channel)
    image_url, return_url = _public_https(image_url), _public_https(return_url)
    if not urlsplit(image_url).path.lower().endswith((".jpg", ".jpeg")):
        raise PublicationValidationError("Для соцсети нужна публичная JPEG-версия с лейблом SCENA.")
    if not re.fullmatch(r"[0-9]{1,40}", str(account_id)):
        raise PublicationValidationError("Укажите подключённую страницу или аккаунт.")
    caption = str(caption or "").strip()
    if not caption:
        raise PublicationValidationError("Подготовьте подпись публикации.")
    if return_url not in caption:
        caption += "\n\n" + return_url
    if channel == "instagram" and len(caption) > 2200:
        raise PublicationValidationError("Для Instagram подпись со ссылкой должна быть не длиннее 2200 символов.")
    if configuration_fingerprint and not re.fullmatch(r"[a-f0-9]{64}", str(configuration_fingerprint)):
        raise PublicationValidationError("Конфигурация подключения изменилась. Обновите предпросмотр.")
    with _db(db_path) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        record = _record(connection, post_id)
        if record["status"] != "published":
            raise PublicationValidationError("Сначала опубликуйте материал в своей Сцене.")
        identity = dict(connection.execute("SELECT key,value FROM app_meta WHERE key IN ('owner_id','installation_id')"))
        snapshot = {"post_id": post_id, "public_id": record["public_id"], "public_revision": record["public_revision"],
                    "publication": json.loads(record["published_json"]), "channel": channel, "account_id": str(account_id),
                    "caption": caption, "image_url": image_url, "media_url": image_url, "return_url": return_url,
                    "configuration_fingerprint": configuration_fingerprint, **identity}
        # A deliberate new preparation can follow a definitive failure. Keep the
        # failed receipt immutable; bind the new attempt to it in the preview hash.
        # Uncertain and successful attempts are never turned into retryable ones.
        for previous in connection.execute("SELECT * FROM publication_deliveries WHERE post_id=? AND channel=? ORDER BY created_at DESC,id DESC", (post_id, channel)):
            previous_snapshot = json.loads(previous["snapshot_json"])
            content = {key: value for key, value in previous_snapshot.items() if key not in {"attempt", "previous_delivery_id"}}
            if content != snapshot:
                continue
            if previous["status"] != "failed":
                return _delivery(previous)
            snapshot.update({"attempt": int(previous_snapshot.get("attempt", 1)) + 1,
                             "previous_delivery_id": previous["id"]})
            break
        snapshot_hash = hashlib.sha256(_json(snapshot).encode()).hexdigest()
        connection.execute("INSERT OR IGNORE INTO publication_deliveries(id,post_id,channel,snapshot_json,snapshot_hash,status,created_at,updated_at) VALUES (?,?,?,?,?,'prepared',?,?)", (str(uuid.uuid4()), post_id, channel, _json(snapshot), snapshot_hash, _now(), _now()))
        return _delivery(connection.execute("SELECT * FROM publication_deliveries WHERE post_id=? AND channel=? AND snapshot_hash=?", (post_id, channel, snapshot_hash)).fetchone())


def _check_adapter(adapter, snapshot):
    if adapter.channel != snapshot["channel"] or str(adapter.account_id) != snapshot["account_id"]:
        raise PublicationValidationError("Получатель изменился. Подготовьте новый предпросмотр.")
    fingerprint = snapshot.get("configuration_fingerprint")
    if fingerprint:
        config = getattr(adapter, "configuration_status", {})
        config = config() if callable(config) else config
        if config.get("fingerprint") != fingerprint:
            raise PublicationValidationError("Подключение изменилось. Подготовьте новый предпросмотр.")


def _adapter_fingerprint(adapter):
    config = getattr(adapter, "configuration_status", {})
    config = config() if callable(config) else config
    fingerprint = str(config.get("fingerprint", ""))
    return fingerprint if re.fullmatch(r"[a-f0-9]{64}", fingerprint) else ""


def _safe_result(result):
    # Never retain raw remote error bodies, exception strings or arbitrary fields.
    status = result.get("status") if isinstance(result, dict) else "unknown"
    if status not in {"sent", "processing", "failed", "unknown"}:
        status = "unknown"
    safe = {"status": status, "publish_attempted": bool(result.get("publish_attempted", True)) if isinstance(result, dict) else True}
    for key in ("external_id", "container_id"):
        value = str(result.get(key, "")) if isinstance(result, dict) else ""
        if re.fullmatch(r"[A-Za-z0-9_:-]{1,128}", value):
            safe[key] = value
    if isinstance(result, dict) and result.get("url"):
        try:
            safe["url"] = _public_https(result["url"])
        except PublicationValidationError:
            pass
    if status in {"failed", "unknown"}:
        safe["message"] = ("Отправка не выполнена. Проверьте подключение и подготовьте новую отправку." if status == "failed" else "Результат отправки неизвестен. Проверьте площадку перед повторной публикацией.")
    return safe


def dispatch_delivery(db_path, delivery_id, adapter, expected_hash, confirmed=False):
    if not confirmed:
        raise PublicationValidationError("Подтвердите точный материал и аккаунт перед отправкой.")
    with _db(db_path) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        delivery = _delivery(connection.execute("SELECT * FROM publication_deliveries WHERE id=?", (delivery_id,)).fetchone())
        if delivery["snapshot_hash"] != expected_hash:
            raise PublicationValidationError("Предпросмотр изменился. Проверьте материал снова.")
        _check_adapter(adapter, delivery["snapshot"])
        if delivery["status"] not in {"prepared", "not_configured"}:
            return delivery
        record = _record(connection, delivery["post_id"])
        if record["status"] != "published" or record["public_revision"] != delivery["snapshot"]["public_revision"]:
            raise PublicationValidationError("Публикация изменилась. Подготовьте новый предпросмотр.")
        if not adapter.configured:
            connection.execute("UPDATE publication_deliveries SET status='not_configured',updated_at=? WHERE id=?", (_now(), delivery_id))
            return _delivery(connection.execute("SELECT * FROM publication_deliveries WHERE id=?", (delivery_id,)).fetchone())
        connection.execute("UPDATE publication_deliveries SET status='sending',updated_at=? WHERE id=?", (_now(), delivery_id))
    try:
        result = _safe_result(adapter.publish(delivery["snapshot"]))
    except Exception:
        result = _safe_result({"status": "unknown"})
    result.update({"channel": delivery["channel"], "account_id": delivery["snapshot"]["account_id"],
                   "configuration_fingerprint": delivery["snapshot"].get("configuration_fingerprint") or _adapter_fingerprint(adapter)})
    with _db(db_path) as connection, connection:
        connection.execute("UPDATE publication_deliveries SET status=?,result_json=?,updated_at=? WHERE id=?", (result["status"], _json(result), _now(), delivery_id))
    return get_delivery(db_path, delivery_id)


def refresh_delivery(db_path, delivery_id, adapter, expected_hash, confirmed=False):
    """Explicit continuation using the existing remote container, never re-upload."""
    if not confirmed:
        raise PublicationValidationError("Подтвердите проверку и продолжение этой отправки.")
    with _db(db_path) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        delivery = _delivery(connection.execute("SELECT * FROM publication_deliveries WHERE id=?", (delivery_id,)).fetchone())
        if delivery["snapshot_hash"] != expected_hash:
            raise PublicationValidationError("Предпросмотр изменился. Проверьте материал снова.")
        _check_adapter(adapter, {**delivery["snapshot"], "configuration_fingerprint": delivery.get("configuration_fingerprint") or delivery["snapshot"].get("configuration_fingerprint", "")})
        if delivery["status"] not in {"processing", "unknown"} or not delivery.get("container_id"):
            return delivery
        if not adapter.configured:
            return delivery
        if delivery["status"] == "processing" and not delivery.get("publish_attempted", True):
            record = _record(connection, delivery["post_id"])
            if record["status"] != "published" or record["public_revision"] != delivery["snapshot"]["public_revision"]:
                raise PublicationValidationError("Публикация изменилась. Продолжение отправки отменено.")
        connection.execute("UPDATE publication_deliveries SET status='checking',updated_at=? WHERE id=?", (_now(), delivery_id))
    try:
        result = _safe_result(adapter.check_status(delivery))
    except Exception:
        result = _safe_result({"status": "unknown"})
    result.setdefault("container_id", delivery["container_id"])
    result.update({"channel": delivery["channel"], "account_id": delivery["snapshot"]["account_id"],
                   "configuration_fingerprint": delivery.get("configuration_fingerprint") or delivery["snapshot"].get("configuration_fingerprint") or _adapter_fingerprint(adapter)})
    with _db(db_path) as connection, connection:
        connection.execute("UPDATE publication_deliveries SET status=?,result_json=?,updated_at=? WHERE id=?", (result["status"], _json(result), _now(), delivery_id))
    return get_delivery(db_path, delivery_id)
