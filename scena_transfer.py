"""Portable, private local backups. Public interchange is deliberately separate.

An archive is an owner-controlled data backup, never an executable installer.
Checksums detect damage, not an untrusted sender. No network calls or credentials.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import stat
import tempfile
import time
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from scena_model_intro import DEFAULT_INTRO_SETTINGS


MAX_FILES = 5000
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
SCHEMA = "scena.portable"
SCHEMA_VERSION = 1
BACKUP_TABLES = {
    "sqlite_sequence", "profile_settings", "services", "requests", "bookings",
    "app_meta", "service_groups", "schedule_exceptions", "sms_outbox", "members",
    "posts", "post_likes", "pro_applications", "pro_subscriptions", "support_threads",
    "support_messages", "integration_outbox", "integration_outbox_claims", "integration_state",
    "publication_records", "publication_versions", "publication_channel_drafts", "publication_deliveries",
    "shop_products", "shop_orders", "shop_order_items", "prompt_projects", "prompt_versions",
    "pro_code_redemptions", "support_reply_preferences", "model_designs",
}


class TransferValidationError(ValueError):
    """User-visible rejection without altering the existing installation."""


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def _safe_path(value):
    if not isinstance(value, str) or not value or len(value) > 512:
        raise TransferValidationError("Некорректное имя файла в архиве.")
    path = PurePosixPath(value)
    parts = value.split("/")
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if (path.is_absolute() or "\\" in value or any(ord(c) < 32 for c in value)
            or any(c in value for c in ':<>"|?*')
            or any(p in ("", ".", "..") or p.endswith((" ", "."))
                   or p.split(".")[0].casefold() in reserved for p in parts)):
        raise TransferValidationError("Архив содержит небезопасный путь файла.")
    return value


def _identity(connection):
    exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_meta'").fetchone()
    values = dict(connection.execute("SELECT key,value FROM app_meta WHERE key IN ('installation_id','owner_id')")) if exists else {}
    result = {}
    for key in ("installation_id", "owner_id"):
        value = values.get(key)
        if value:
            try:
                result[key] = str(uuid.UUID(value))
            except (TypeError, ValueError) as exc:
                raise TransferValidationError("Повреждён постоянный идентификатор установки.") from exc
        else:
            result[key] = None
    return result


@contextmanager
def _snapshot(db_path):
    path = Path(db_path)
    if not path.is_file() or path.is_symlink():
        raise TransferValidationError("Выберите существующую базу SCENA.")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise TransferValidationError("База превышает лимит переносимого пакета 128 МБ.")
    with tempfile.TemporaryDirectory(prefix="scena-snapshot-") as temp:
        snapshot_path = Path(temp) / "scena_master.db"
        try:
            source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            target = sqlite3.connect(snapshot_path)
            try:
                deadline = time.monotonic() + 15

                def progress(_status, _remaining, _total):
                    if time.monotonic() > deadline:
                        raise TransferValidationError("База занята. Завершите сохранение и повторите резервное копирование.")

                source.backup(target, pages=256, progress=progress, sleep=0.05)
                target.row_factory = sqlite3.Row
                yield target, snapshot_path.read_bytes()
            finally:
                source.close()
                target.close()
        except sqlite3.Error as exc:
            raise TransferValidationError("Не удалось прочитать согласованную копию базы SCENA.") from exc


def _read_media(media_dir):
    root = Path(media_dir)
    if root.is_symlink() or not root.is_dir():
        raise TransferValidationError("Папка media не найдена или является ссылкой.")
    payloads = {}
    total = 0
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            path = Path(current) / name
            if path.is_symlink():
                raise TransferValidationError("В media обнаружена ссылка. Для резервной копии нужны обычные файлы.")
        for name in sorted(files):
            path = Path(current) / name
            if not path.is_file():
                raise TransferValidationError("В media обнаружен специальный файл.")
            archive_path = _safe_path("media/" + path.relative_to(root).as_posix())
            size = path.stat().st_size
            total += size
            if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES or len(payloads) >= MAX_FILES - 2:
                raise TransferValidationError("Материалы превышают лимиты переносимого пакета.")
            payloads[archive_path] = path.read_bytes()
    return payloads


def _pack(payloads, *, kind, identity, warnings=()):
    if len(payloads) > MAX_FILES or sum(len(v) for v in payloads.values()) > MAX_TOTAL_BYTES:
        raise TransferValidationError("Пакет превышает лимит 512 МБ или 5000 файлов.")
    manifest = {
        "schema": SCHEMA, "schema_version": SCHEMA_VERSION,
        "kind": kind, "created_at": datetime.now(timezone.utc).isoformat(),
        "contains_private_data": kind == "private_backup", "identity": identity,
        "platform_connection": "not_implemented", "warnings": list(warnings),
        "files": [{"path": key, "size": len(value), "sha256": hashlib.sha256(value).hexdigest()}
                  for key, value in sorted(payloads.items())],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        for key, value in sorted(payloads.items()):
            _safe_path(key)
            if len(value) > MAX_FILE_BYTES:
                raise TransferValidationError("Файл превышает лимит 128 МБ.")
            archive.writestr(key, value)
    data = buffer.getvalue()
    _validate_zip(data)
    return data


def build_backup(db_path, media_dir) -> bytes:
    """Copy a consistent SQLite snapshot and all local media, including private data."""
    with _snapshot(db_path) as (connection, database):
        identity = _identity(connection)
        content = _public_content(connection, media_dir)
    payloads = _read_media(media_dir)
    payloads["scena_master.db"] = database
    payloads["public-content.json"] = _json_bytes(content)
    warnings = ["Личная резервная копия содержит клиентские данные, черновики и переписку. Храните её приватно."]
    if not all(identity.values()):
        warnings.append("Установка ещё не получила идентификаторы V1.5; откройте её в V1.5 перед переносом на платформу.")
    return _pack(payloads, kind="private_backup", identity=identity, warnings=warnings)


def _public_intro_ready(settings, media_dir):
    """Only a reviewed bilingual card with a real local photo is public."""
    from PIL import Image

    if (media_dir is None or settings.get("model_intro_enabled") != "1"
            or settings.get("model_intro_translations_approved") != "1"):
        return False
    if any(not str(settings.get(f"model_intro_{field}_{language}", "")).strip()
           for field in ("title", "text", "alt") for language in ("ru", "ro")):
        return False
    if (bool(str(settings.get("model_intro_details_ru", "")).strip())
            != bool(str(settings.get("model_intro_details_ro", "")).strip())):
        return False
    reference = settings.get("model_intro_image", "")
    try:
        _safe_path(reference)
        if not reference.startswith("media/"):
            return False
        root = Path(media_dir).absolute()
        path = root / reference[len("media/"):]
        if (not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}
                or any(part.is_symlink() for part in (path, *path.parents))
                or path.stat().st_size > 20 * 1024 * 1024):
            return False
        path.resolve().relative_to(root.resolve())
        with Image.open(path) as photo:
            if photo.format not in {"JPEG", "PNG", "WEBP"} or getattr(photo, "is_animated", False):
                return False
            photo.verify()
    except (OSError, ValueError, Image.DecompressionBombError):
        return False
    return True


def _public_content(connection, media_dir=None):
    """Explicit field allowlists; never serialize settings, rows or draft JSON wholesale."""
    identity = _identity(connection)
    settings = dict(connection.execute("SELECT key,value FROM profile_settings"))
    visible = {key: settings.get(key + "_published", "0") == "1"
               for key in ("profile", "professional", "model")}
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    content = {"schema": "scena.public-content", "schema_version": 1,
               "status": "draft_interchange_schema_not_platform_sync", "identity": identity,
               "owner": {"id": identity["owner_id"], "name": settings.get("master_name", "") if any(visible.values()) else ""},
               "profile": {}, "services": [], "service_groups": [], "posts": [],
               "object_mappings": [], "external_media_not_included": []}
    if visible["profile"]:
        for key in ("master_name", "master_name_ru", "master_name_ro", "master_name_en", "booking_cta_ru", "booking_cta_ro", "booking_cta_en", "profile_slug", "location", "bio", "bio_ro", "bio_en", "avatar_url", "scene_hero_image", "instagram_url", "telegram_url", "default_locale", "currency"):
            if key in settings:
                content["profile"][key] = settings[key]
        for key in ("professional_in_scene", "model_in_scene"):
            if key in settings:
                content["profile"][key] = settings[key]
    for role, prefix in (("professional", "beauty"), ("model", "model")):
        if not visible[role]:
            continue
        fields = [prefix + suffix for suffix in ("_title", "_title_ro", "_title_en", "_desc", "_desc_ro", "_desc_en", "_portfolio_customized")]
        fields.extend(f"{prefix}_image_{index}" for index in range(1, 13))
        if role == "professional":
            fields.append("professional_hero_image")
            fields.extend("booking_"+kind+"_"+lang for kind in ("title","description") for lang in ("ru","ro","en"))
        else:
            fields.extend(("model_slider_enabled", "model_slider_autoplay", "model_slider_first", "model_design_json"))
            if _public_intro_ready(settings, media_dir):
                fields.extend(DEFAULT_INTRO_SETTINGS)
            for index in range(1, 6):
                slide = f"model_slide_{index}"
                if (settings.get(slide + "_visible") != "1"
                        or settings.get(slide + "_translations_approved") != "1"
                        or any(not str(settings.get(slide + suffix, "")).strip()
                               for suffix in ("_image", "_manifesto_ru", "_manifesto_ro", "_alt_ru", "_alt_ro"))):
                    continue
                fields.extend(slide + suffix for suffix in ("_image", "_manifesto_ru", "_manifesto_ro", "_manifesto_en", "_alt_ru", "_alt_ro", "_alt_en", "_order", "_visible", "_translations_approved", "_duration_seconds", "_desktop_x", "_desktop_y", "_mobile_x", "_mobile_y"))
        content["profile"][role] = {key: settings[key] for key in fields if key in settings}
    namespace = uuid.UUID(identity["installation_id"]) if identity["installation_id"] else None

    def identifier(entity, local_id, public_id=None):
        stable = public_id or (str(uuid.uuid5(namespace, f"{entity}:{local_id}")) if namespace else None)
        content["object_mappings"].append({"entity": entity, "local_id": str(local_id), "id": stable})
        return stable

    group_ids = set()
    if "services" in tables:
        allowed = ("category", "kind", "name", "name_ro", "name_en", "description_ru", "description_ro", "description_en", "price", "duration", "sort_order")
        service_query = (
            "SELECT s.* FROM services AS s LEFT JOIN service_groups AS sg ON sg.id=s.group_id "
            "WHERE (sg.id IS NULL OR sg.active=1) ORDER BY s.id"
            if "service_groups" in tables else "SELECT * FROM services ORDER BY id"
        )
        for row in connection.execute(service_query):
            row = dict(row)
            role = "model" if row.get("category") == "Model" else "professional"
            if not visible[role] or not row.get("active") or row.get("archived"):
                continue
            record = {key: row[key] for key in allowed if key in row}
            record["id"] = identifier("service", row["id"])
            if row.get("group_id"):
                group_ids.add(row["group_id"])
                record["group_id"] = str(uuid.uuid5(namespace, f"service_group:{row['group_id']}")) if namespace else None
            content["services"].append(record)
    if "service_groups" in tables:
        for row in connection.execute("SELECT * FROM service_groups ORDER BY id"):
            row = dict(row)
            if row["id"] not in group_ids:
                continue
            record = {key: row[key] for key in ("category", "name_ru", "name_ro", "name_en", "description_ru", "description_ro", "description_en", "sort_order") if key in row}
            record["id"] = identifier("service_group", row["id"])
            content["service_groups"].append(record)
    if visible["profile"] and "publication_records" in tables:
        allowed = ("title_ru", "title_ro", "body_ru", "body_ro", "image_url", "link_url", "show_scene", "show_professional", "show_model", "kind", "price_text", "cta_label_ru", "cta_label_ro", "cta_label_en", "cta_url", "title_en", "body_en", "frame_style", "frame_format")
        records = connection.execute("SELECT post_id,public_id,public_revision,status,published_json FROM publication_records WHERE status='published' ORDER BY post_id")
        for row in records:
            snapshot = json.loads(row["published_json"])
            if not isinstance(snapshot, dict):
                raise TransferValidationError("Повреждена опубликованная версия материала.")
            destinations = {"show_scene": visible["profile"], "show_professional": visible["professional"], "show_model": visible["model"]}
            if not any(snapshot.get(key) and value for key, value in destinations.items()):
                continue
            record = {key: snapshot[key] for key in allowed if key in snapshot}
            record.update({"id": identifier("post", row["post_id"], row["public_id"]), "public_revision": row["public_revision"], "status": "published"})
            content["posts"].append(record)
        if visible["profile"]:
            for row in connection.execute("SELECT post_id,public_id,public_revision FROM publication_records WHERE status='archived' AND public_revision>0 ORDER BY post_id"):
                content["posts"].append({"id": identifier("post", row["post_id"], row["public_id"]),
                                         "public_revision": row["public_revision"], "status": "archived"})
    elif visible["profile"] and "posts" in tables:
        # Compatibility for pre-V1.5 backups. Drafts are never included.
        for row in connection.execute("SELECT * FROM posts WHERE active=1 ORDER BY id"):
            row = dict(row)
            if not any(row.get(key) and value for key, value in (("show_scene", visible["profile"]), ("show_professional", visible["professional"]), ("show_model", visible["model"]))):
                continue
            record = {key: row[key] for key in ("title_ru", "title_ro", "body_ru", "body_ro", "image_url", "link_url", "show_scene", "show_professional", "show_model", "created_at")}
            record.update({"id": identifier("post", row["id"]), "status": "published"})
            content["posts"].append(record)
    if "shop_products" in tables and settings.get("shop_enabled", "0") == "1":
        from scena_shop import public_shop_data
        content["shop"] = public_shop_data(connection)
    return content


def _public_media_refs(value):
    references = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("image", "image_url", "avatar_url", "scene_hero_image", "professional_hero_image") or key.endswith("_image") or re.fullmatch(r"(?:beauty|model)_image_(?:[1-9]|1[0-2])", key):
                if isinstance(item, str) and item:
                    references.add(item)
            elif isinstance(item, (dict, list)):
                references.update(_public_media_refs(item))
    elif isinstance(value, list):
        for item in value:
            references.update(_public_media_refs(item))
    return references


def build_platform_export(db_path, media_dir) -> bytes:
    """Public-only draft interchange; no customers, private originals, history or tokens."""
    with _snapshot(db_path) as (connection, _):
        content = _public_content(connection, media_dir)
    if not all(content["identity"].values()):
        raise TransferValidationError("Сначала откройте установку в V1.5 для создания постоянных идентификаторов.")
    root = Path(media_dir).absolute()
    if root.is_symlink() or not root.is_dir():
        raise TransferValidationError("Для экспорта нужна обычная папка media.")
    payloads, missing = {}, []
    for reference in sorted(_public_media_refs(content)):
        if reference.startswith(("https://", "http://")):
            content["external_media_not_included"].append(reference)
            continue
        _safe_path(reference)
        if not reference.startswith("media/"):
            missing.append(reference)
            continue
        path = root / reference[len("media/"):]
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise TransferValidationError("Опубликованное изображение является ссылкой на другой файл.")
        if not path.is_file():
            missing.append(reference)
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            raise TransferValidationError("Опубликованный файл превышает лимит 128 МБ.")
        payloads[reference] = path.read_bytes()
        if sum(map(len, payloads.values())) > MAX_TOTAL_BYTES:
            raise TransferValidationError("Публичные изображения превышают лимит пакета.")
    content["missing_local_media"] = missing
    payloads["public-content.json"] = _json_bytes(content)
    warnings = ["Только публичные материалы. Импорт и связывание владельца будущая платформа ещё должна реализовать и проверить."]
    if missing:
        warnings.append(f"Не найдены локальные изображения: {len(missing)}. Перечень есть в public-content.json.")
    if content["external_media_not_included"]:
        warnings.append("Внешние изображения оставлены ссылками; скачивание не выполнялось.")
    return _pack(payloads, kind="public_interchange_draft", identity=content["identity"], warnings=warnings)


def _validate_zip(data):
    if not isinstance(data, bytes) or not data or len(data) > MAX_TOTAL_BYTES + MAX_MANIFEST_BYTES:
        raise TransferValidationError("Пустой или слишком большой архив.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES + 1:
                raise TransferValidationError("Слишком много файлов в архиве.")
            names = set()
            total = 0
            for info in entries:
                name = _safe_path(info.filename)
                if name.casefold() in names:
                    raise TransferValidationError("В архиве есть повторяющиеся имена файлов.")
                names.add(name.casefold())
                mode = info.external_attr >> 16
                if info.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)) or info.flag_bits & 1:
                    raise TransferValidationError("Архив содержит ссылку, специальный или зашифрованный файл.")
                if name != "manifest.json" and name != "scena_master.db" and name != "public-content.json" and not name.startswith("media/"):
                    raise TransferValidationError("Архив содержит неожиданный файл.")
                cap = MAX_MANIFEST_BYTES if name == "manifest.json" else MAX_FILE_BYTES
                total += info.file_size
                if info.file_size > cap or total > MAX_TOTAL_BYTES + MAX_MANIFEST_BYTES:
                    raise TransferValidationError("Распакованные данные превышают лимит.")
                if info.file_size > 1024 * 1024 and info.file_size / max(info.compress_size, 1) > 1000:
                    raise TransferValidationError("Архив содержит чрезмерно сжатые данные.")
            if "manifest.json" not in names:
                raise TransferValidationError("В архиве нет манифеста SCENA.")
            manifest = json.loads(archive.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA or type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != SCHEMA_VERSION:
                raise TransferValidationError("Неподдерживаемая версия переносимого пакета.")
            identity = manifest.get("identity")
            if not isinstance(identity, dict) or set(identity) != {"owner_id", "installation_id"}:
                raise TransferValidationError("В архиве отсутствует описание владельца и установки.")
            for value in identity.values():
                if value is not None:
                    try:
                        uuid.UUID(value)
                    except (ValueError, TypeError, AttributeError) as exc:
                        raise TransferValidationError("Неверный идентификатор в манифесте.") from exc
            kind = manifest.get("kind")
            if kind not in ("private_backup", "public_interchange_draft") or manifest.get("contains_private_data") is not (kind == "private_backup"):
                raise TransferValidationError("Неизвестный тип переносимого пакета.")
            file_list = manifest.get("files")
            if not isinstance(file_list, list) or len(file_list) > MAX_FILES:
                raise TransferValidationError("Некорректный список файлов манифеста.")
            payloads = {}
            for entry in file_list:
                if not isinstance(entry, dict):
                    raise TransferValidationError("Некорректная запись манифеста.")
                name = _safe_path(entry.get("path"))
                size, checksum = entry.get("size"), entry.get("sha256")
                if name == "manifest.json" or name in payloads or type(size) is not int or size < 0 or not isinstance(checksum, str) or not re.fullmatch(r"[a-f0-9]{64}", checksum):
                    raise TransferValidationError("Некорректные контрольные данные манифеста.")
                raw = archive.read(name)
                if len(raw) != size or hashlib.sha256(raw).hexdigest() != checksum:
                    raise TransferValidationError("Контрольная сумма файла не совпадает. Архив повреждён.")
                payloads[name] = raw
            if {"manifest.json", *payloads} != {i.filename for i in entries}:
                raise TransferValidationError("Файлы архива не совпадают с манифестом.")
            if kind == "private_backup" and "scena_master.db" not in payloads:
                raise TransferValidationError("В резервной копии нет базы SCENA.")
            if kind == "public_interchange_draft" and ("scena_master.db" in payloads or "public-content.json" not in payloads):
                raise TransferValidationError("Публичный пакет содержит недопустимые данные.")
            return manifest, payloads
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError, OSError, RecursionError, NotImplementedError) as exc:
        raise TransferValidationError("Не удалось проверить архив SCENA.") from exc


def inspect_backup(data) -> dict:
    """Validate checksums and SQLite before offering restoration; no destination writes."""
    manifest, payloads = _validate_zip(data)
    owner_name = ""
    if manifest["kind"] == "private_backup":
        with tempfile.TemporaryDirectory(prefix="scena-inspect-") as temp:
            path = Path(temp) / "snapshot.db"
            path.write_bytes(payloads["scena_master.db"])
            try:
                with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
                    connection.execute("PRAGMA trusted_schema=OFF")
                    schema = connection.execute("SELECT type,name,sql FROM sqlite_master").fetchall()
                    for object_type, object_name, sql in schema:
                        if object_type in ("trigger", "view") or (object_type == "table" and (object_name not in BACKUP_TABLES or "VIRTUAL TABLE" in (sql or "").upper())):
                            raise TransferValidationError("База содержит неподдерживаемую таблицу, представление или триггер. Такой архив нельзя восстановить автоматически.")
                    for table, required in {"profile_settings": {"key", "value"}, "app_meta": {"key", "value"}, "services": {"id", "category", "name", "active"}, "requests": {"id", "status"}}.items():
                        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                        if not required.issubset(columns):
                            raise TransferValidationError("Архив не содержит поддерживаемую структуру базы SCENA.")
                    if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                        raise TransferValidationError("База в архиве повреждена.")
                    if _identity(connection) != manifest.get("identity"):
                        raise TransferValidationError("Идентификаторы базы и манифеста не совпадают.")
                    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='profile_settings'").fetchone():
                        raise TransferValidationError("В архиве не найдена база SCENA.")
                    name = connection.execute("SELECT value FROM profile_settings WHERE key='master_name'").fetchone()
                    owner_name = str(name[0]) if name else ""
            except sqlite3.Error as exc:
                raise TransferValidationError("В архиве повреждённая база SQLite.") from exc
    return {**manifest, "file_count": len(payloads), "total_bytes": sum(map(len, payloads.values())),
            "media_count": sum(name.startswith("media/") for name in payloads), "owner_name": owner_name}


def restore_backup(data, destination) -> dict:
    """Restore to a new/empty directory only, after full validation; never overwrite."""
    summary = inspect_backup(data)
    if summary["kind"] != "private_backup":
        raise TransferValidationError("Публичный пакет не является полной резервной копией.")
    _, payloads = _validate_zip(data)
    target = Path(destination).absolute()
    if any(parent.is_symlink() for parent in (target, *target.parents)):
        raise TransferValidationError("Папка восстановления не может находиться за символической ссылкой.")
    if not target.parent.is_dir() or (target.exists() and (not target.is_dir() or any(target.iterdir()))):
        raise TransferValidationError("Выберите новую или пустую папку. Существующие файлы не заменяются.")
    with tempfile.TemporaryDirectory(prefix="scena-restore-", dir=target.parent) as temp:
        staged = Path(temp) / "installation"
        staged.mkdir()
        for name, value in payloads.items():
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(value)
        (staged / "media").mkdir(exist_ok=True)
        if any(parent.is_symlink() for parent in (target, *target.parents)):
            raise TransferValidationError("Папка восстановления изменилась во время проверки.")
        removed_empty = False
        if target.exists():
            if not target.is_dir() or any(target.iterdir()):
                raise TransferValidationError("Папка больше не пуста. Восстановление остановлено.")
            target.rmdir()  # Empty directory only; no existing owner data is removed.
            removed_empty = True
        try:
            staged.rename(target)
        except OSError as exc:
            if removed_empty and not target.exists():
                target.mkdir()
            raise TransferValidationError("Не удалось перенести проверенные файлы в новую папку.") from exc
    return {"destination": str(target), "db_path": str(target / "scena_master.db"),
            "media_dir": str(target / "media"), "identity": summary["identity"],
            "file_count": summary["file_count"], "contains_private_data": True}
