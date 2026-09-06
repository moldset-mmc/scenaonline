"""Business rules and SQLite persistence for the focused SCENA Pilot V1.4."""

from __future__ import annotations

import hmac
import os
import re
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Mapping
from zoneinfo import ZoneInfo
from scena_model_intro import DEFAULT_INTRO_SETTINGS
from scena_i18n import DEFAULT_I18N_SETTINGS, normalize_locale, translate_literaltext
from scena_shop import SHOP_DEFAULT_SETTINGS


CHISINAU = ZoneInfo("Europe/Chisinau")

REQUEST_TYPES = {
    "service_request": "Запись на услугу",
    "course_preregistration": "Предзапись на курс",
    "model_invitation": "Приглашение модели",
    "model_application": "Хочу стать моделью",
}

REQUEST_STATUSES = (
    "Новая",
    "Ожидает подтверждения",
    "Связались",
    "Подтверждена",
    "Завершена",
    "Отклонена",
    "Отменена",
    "Срок подтверждения истёк",
)

BLOCKING_STATUSES = {
    "Ожидает подтверждения",
    "Связались",
    "Подтверждена",
}

SERVICE_CATEGORIES = {
    "Professional": "Услуги и курсы",
    "Model": "Модельные форматы",
}

SERVICE_KINDS = {
    "appointment": "Запись по времени",
    "course": "Курс — предварительная запись",
    "inquiry": "Обращение без календаря",
}

DEFAULT_SETTINGS = {
    "master_name": "Мария Бараночникова",
    "profile_slug": "my-scena",
    "location": "Кишинёв",
    "bio": "Я соединяю красоту, характер и движение — от точного макияжа до яркого выхода на сцену.",
    "bio_ro": "Unesc frumusețea, caracterul și mișcarea — de la machiajul precis la o apariție memorabilă pe scenă.",
    "bio_translation_approved": "1",
    "beauty_title": "M | B Makeup Studio",
    "beauty_title_ro": "M | B Makeup Studio",
    "beauty_desc": "Премиальный макияж для событий, съёмок и выразительных персональных образов.",
    "beauty_desc_ro": "Machiaj premium pentru evenimente, ședințe foto și imagini personale expresive.",
    "model_title": "Модель",
    "model_title_ro": "Model",
    "model_desc": "Портфолио и предложения для брендов, фотографов и творческих команд.",
    "model_desc_ro": "Portofoliu și oferte pentru branduri, fotografi și echipe creative.",
    "avatar_url": "",
    "scene_hero_image": "media/scena-v13/my-scena-hero.webp",
    "professional_hero_image": "media/scena-v13/professional-portrait.webp",
    "beauty_image_1": "",
    "beauty_image_2": "",
    "beauty_image_3": "",
    "model_image_1": "",
    "model_image_2": "",
    "model_image_3": "",
    "instagram_url": "",
    "telegram_url": "",
    "currency": "MDL",
    "pilot_notice": "1",
    "profile_published": "1",
    "profile_indexed": "1",
    "professional_published": "1",
    "professional_indexed": "1",
    "professional_translation_approved": "1",
    "professional_in_scene": "1",
    "model_published": "1",
    "model_indexed": "1",
    "model_translation_approved": "1",
    "model_in_scene": "1",
    "default_locale": "ro",
    "schedule_weekdays": "0,1,2,3,4",
    "schedule_start": "09:00",
    "schedule_end": "18:00",
    "schedule_break_start": "13:00",
    "schedule_break_end": "14:00",
    "slot_interval_minutes": "10",
    "default_buffer_minutes": "10",
    "minimum_lead_hours": "2",
    "booking_horizon_days": "90",
    "pending_hold_hours": "24",
    "public_base_url": "http://localhost:8501",
    "model_slider_enabled": "1",
    "model_slider_autoplay": "1",
    "model_slider_first": "1",
}

DEFAULT_SETTINGS.update(DEFAULT_INTRO_SETTINGS)
DEFAULT_SETTINGS["model_design_json"] = ""
DEFAULT_SETTINGS.update(DEFAULT_I18N_SETTINGS)
DEFAULT_SETTINGS.update(SHOP_DEFAULT_SETTINGS)

# Additive portfolio capacity: keep every existing uploaded photo unchanged.
for _portfolio_prefix in ("beauty", "model"):
    DEFAULT_SETTINGS[f"{_portfolio_prefix}_portfolio_customized"] = "0"
    for _portfolio_slot in range(4, 13):
        DEFAULT_SETTINGS[f"{_portfolio_prefix}_image_{_portfolio_slot}"] = ""

MODEL_SLIDE_DEFAULTS = (
    {
        "image": "media/model-slider/01-black-halo.webp",
        "manifesto_ru": "Быть собой — мой самый смелый образ.",
        "manifesto_ro": "Să fiu eu însămi este cea mai curajoasă imagine a mea.",
        "alt_ru": "Модель в чёрном архитектурном образе на подиуме с сияющим кругом",
        "alt_ro": "Model într-o ținută arhitecturală neagră, pe podium, într-un cerc de lumină",
        "mobile_x": "72",
    },
    {
        "image": "media/model-slider/02-black-portrait.webp",
        "manifesto_ru": "Красота начинается со взгляда, который не просит разрешения.",
        "manifesto_ro": "Frumusețea începe cu o privire care nu cere permisiune.",
        "alt_ru": "Крупный портрет модели среди зеркальных панелей и света софитов",
        "alt_ro": "Portret apropiat al modelului printre panouri de oglindă și lumini de podium",
        "mobile_x": "0",
    },
    {
        "image": "media/model-slider/03-white-couture.webp",
        "manifesto_ru": "Женственность — это сила, которой не нужно ничего доказывать.",
        "manifesto_ro": "Feminitatea este o forță care nu trebuie să demonstreze nimic.",
        "alt_ru": "Модель в белом скульптурном couture-платье на чёрном подиуме",
        "alt_ro": "Model într-o rochie couture albă, sculpturală, pe podiumul negru",
        "mobile_x": "52",
    },
    {
        "image": "media/model-slider/04-white-motion.webp",
        "manifesto_ru": "Я выбираю движение, свет и свободу.",
        "manifesto_ro": "Aleg mișcarea, lumina și libertatea.",
        "alt_ru": "Модель в летящем белом платье на глянцевом подиуме",
        "alt_ro": "Model într-o rochie albă fluidă, pe un podium lucios",
        "mobile_x": "74",
    },
    {
        "image": "media/model-slider/05-tan-white-wings.webp",
        "manifesto_ru": "Мой свет не просит сцены. Он создаёт её.",
        "manifesto_ro": "Lumina mea nu cere o scenă. O creează.",
        "alt_ru": "Модель в телесном couture-комбинезоне с белой бахромой и крыльями",
        "alt_ro": "Model într-o salopetă couture nude, cu franjuri și aripi albe",
        "mobile_x": "72",
    },
)

for _slide_index, _slide in enumerate(MODEL_SLIDE_DEFAULTS, start=1):
    _prefix = f"model_slide_{_slide_index}"
    DEFAULT_SETTINGS.update({
        f"{_prefix}_image": _slide["image"],
        f"{_prefix}_manifesto_ru": _slide["manifesto_ru"],
        f"{_prefix}_manifesto_ro": _slide["manifesto_ro"],
        f"{_prefix}_alt_ru": _slide["alt_ru"],
        f"{_prefix}_alt_ro": _slide["alt_ro"],
        f"{_prefix}_order": str(_slide_index),
        f"{_prefix}_visible": "1",
        f"{_prefix}_translations_approved": "1",
        f"{_prefix}_duration_seconds": "7",
        f"{_prefix}_desktop_x": "50",
        f"{_prefix}_desktop_y": "50",
        f"{_prefix}_mobile_x": _slide["mobile_x"],
        f"{_prefix}_mobile_y": "50",
    })

LEGACY_DEFAULT_SERVICES = {
    ("Beauty", "Дневной макияж", 800.0, 60),
    ("Beauty", "Вечерний макияж", 1200.0, 90),
    ("Model", "Каталожная съёмка", 0.0, 120),
    ("Model", "Имиджевая съёмка", 0.0, 180),
}

LEGACY_DEMO_SERVICES = {
    ("Beauty", "Фэшн-макияж (Glowing Nude)", 4500.0, 45),
    ("Beauty", "Креативный макияж (Graphic Line)", 6000.0, 60),
    ("Beauty", "Полный образ (Макияж + Укладка волос Lebel)", 9000.0, 90),
    ("Model", "Съемка каталога (IDOL/12 STOREEZ)", 5000.0, 60),
    ("Model", "Участие в фэшн-дефиле SCENA Backstage", 15000.0, 120),
    ("Model", "Тестовая примерка новых коллекций (Digital Try-On)", 3500.0, 60),
}

DEFAULT_SERVICES = (
    (
        "Professional", "appointment", "Персональная консультация",
        "Consultație personală", "Индивидуальная встреча со специалистом.",
        "Întâlnire individuală cu specialistul.", 900.0, 60, 10,
    ),
    (
        "Professional", "appointment", "Индивидуальная услуга",
        "Serviciu individual",
        "Формат и результат согласовываются перед подтверждением записи.",
        "Formatul și rezultatul se stabilesc înainte de confirmarea programării.",
        1200.0, 90, 10,
    ),
    (
        "Professional", "course", "Авторский курс", "Curs de autor",
        "Предварительная запись без автоматического подтверждения места.",
        "Preînscriere fără confirmarea automată a locului.", 0.0, 60, 0,
    ),
    (
        "Model", "inquiry", "Модельный проект", "Proiect de modeling",
        "Формат, сроки, цена и права согласовываются отдельно.",
        "Formatul, termenii, prețul și drepturile se stabilesc separat.",
        0.0, 120, 0,
    ),
)

DEFAULT_SERVICE_GROUPS = (
    (
        "Professional", "Индивидуальная работа", "Servicii individuale",
        "Персональные услуги и консультации.",
        "Servicii și consultații individuale.", 10,
    ),
    (
        "Professional", "Обучение", "Cursuri",
        "Курсы, практикумы и обучение.",
        "Cursuri, ateliere și instruire.", 20,
    ),
    (
        "Model", "Модельные проекты", "Proiecte de modeling",
        "Съёмки, показы и предложения брендов.",
        "Ședințe foto, prezentări și propuneri de la branduri.", 10,
    ),
)

LEGACY_STATUS_MAP = {
    "Новый": "Новая",
    "Подтвержден": "Подтверждена",
    "Выполнен": "Завершена",
    "Отменен": "Отменена",
}

LEGACY_DEMO_SETTING_VALUES = {
    "master_name": {"Мария Барановская", "Имя мастера", "Имя"},
    "location": {"Ваш город", "Город"},
    "bio": {
        "Я верю, что современная индустрия красоты неотделима от высокой моды. Как профессиональный визажист, я создаю законченные образы на бэкстейджах. Как модель, я умею транслировать ДНК премиальных брендов.",
        "Персональная страница визажиста и модели. Замените этот текст, имя, контакты и фотографии в кабинете мастера.",
        "Личное пространство, где человек рассказывает о себе и открывает разные стороны своей Сцены.",
    },
    "bio_ro": {
        "Spațiul personal în care omul vorbește despre sine și își deschide diferitele laturi ale Scenei.",
    },
    "beauty_title": {"Makeup Artist (Визажист)", "Визажист", "Профессиональное направление"},
    "beauty_title_ro": {"Direcție profesională"},
    "beauty_desc": {
        "Специализируюсь на создании сияющей кожи, графичных стрелок и образов для фэшн-показов. Работаю исключительно на премиальных брендах косметики (Lebel, Keune).",
        "Макияж для событий, съёмок и персональных образов.",
        "Услуги, консультации, обучение и другие профессиональные предложения.",
    },
    "beauty_desc_ro": {
        "Servicii, consultații, instruire și alte oferte profesionale.",
    },
    "model_title": {"Professional Model"},
    "model_desc": {
        "Официальная модель бэкстейджей SCENA. Имею опыт работы с брендами тихой роскоши (12 STOREEZ, IDOL, YuliaWave). Мое лицо верифицировано в ИИ-галерее Face ID.",
    },
    "avatar_url": {
        "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=600"
    },
}


class RequestValidationError(ValueError):
    """Raised when public input does not satisfy the pilot contract."""


def _db_path(db_path: str | Path) -> Path:
    resolved = Path(db_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path(db_path), timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}


def _table_sql(connection: sqlite3.Connection, table: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return str(row["sql"] or "") if row else ""


def _now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(CHISINAU)
    if value.tzinfo is None:
        return value.replace(tzinfo=CHISINAU)
    return value.astimezone(CHISINAU)


def _create_services_table(connection: sqlite3.Connection, name: str = "services") -> None:
    connection.execute(
        f"""
        CREATE TABLE {name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL CHECK (category IN ('Professional', 'Model')),
            kind TEXT NOT NULL DEFAULT 'appointment'
                CHECK (kind IN ('appointment', 'course', 'inquiry')),
            name TEXT NOT NULL,
            name_ro TEXT NOT NULL DEFAULT '',
            name_en TEXT NOT NULL DEFAULT '',
            description_ru TEXT NOT NULL DEFAULT '',
            description_ro TEXT NOT NULL DEFAULT '',
            description_en TEXT NOT NULL DEFAULT '',
            translations_approved INTEGER NOT NULL DEFAULT 0
                CHECK (translations_approved IN (0, 1)),
            price REAL NOT NULL CHECK (price >= 0),
            duration INTEGER NOT NULL CHECK (duration >= 5),
            buffer_minutes INTEGER NOT NULL DEFAULT 10 CHECK (buffer_minutes >= 0),
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            group_id INTEGER,
            sort_order INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1))
        )
        """
    )


def _migrate_services(connection: sqlite3.Connection) -> set[tuple[str, str, float, int]]:
    if not _table_exists(connection, "services"):
        _create_services_table(connection)
        return set()
    columns = _column_names(connection, "services")
    fields = [
        field for field in (
            "id", "category", "kind", "name", "name_ro", "description_ru",
            "description_ro", "translations_approved", "price", "duration",
            "buffer_minutes", "active",
        ) if field in columns
    ]
    rows = connection.execute(
        f"SELECT {', '.join(fields)} FROM services ORDER BY id"
    ).fetchall()
    signatures = {
        (row["category"], row["name"], float(row["price"]), int(row["duration"]))
        for row in rows
    }
    required = {
        "kind", "name_ro", "description_ru", "description_ro",
        "translations_approved", "buffer_minutes",
    }
    if "'Professional'" in _table_sql(connection, "services") and required.issubset(columns):
        return signatures
    connection.execute("DROP TABLE IF EXISTS services_v11")
    _create_services_table(connection, "services_v11")
    for row in rows:
        values = dict(row)
        category = "Professional" if values["category"] == "Beauty" else values["category"]
        kind = values.get("kind", "inquiry" if category == "Model" else "appointment")
        connection.execute(
            """
            INSERT INTO services_v11 (
                id, category, kind, name, name_ro, description_ru,
                description_ro, translations_approved, price, duration,
                buffer_minutes, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["id"], category, kind, values["name"], values.get("name_ro", ""),
                values.get("description_ru", ""), values.get("description_ro", ""),
                int(values.get("translations_approved", 0)), float(values["price"]),
                int(values["duration"]), int(values.get("buffer_minutes", 10)),
                int(values.get("active", 1)),
            ),
        )
    connection.execute("DROP TABLE services")
    connection.execute("ALTER TABLE services_v11 RENAME TO services")
    return signatures


def _create_requests_table(connection: sqlite3.Connection, name: str = "requests") -> None:
    connection.execute(
        f"""
        CREATE TABLE {name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_type TEXT NOT NULL CHECK (
                request_type IN ('service_request', 'course_preregistration',
                                 'model_invitation', 'model_application')
            ),
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL DEFAULT '',
            organization TEXT NOT NULL DEFAULT '',
            service_id INTEGER,
            service TEXT NOT NULL DEFAULT '',
            preferred_date TEXT NOT NULL DEFAULT '',
            preferred_time TEXT NOT NULL DEFAULT '',
            slot_start TEXT NOT NULL DEFAULT '',
            slot_end TEXT NOT NULL DEFAULT '',
            slot_block_end TEXT NOT NULL DEFAULT '',
            hold_expires_at TEXT NOT NULL DEFAULT '',
            locale TEXT NOT NULL DEFAULT 'ro' CHECK (locale IN ('ru', 'ro', 'en')),
            contact_channel TEXT NOT NULL DEFAULT 'sms',
            city TEXT NOT NULL DEFAULT '',
            experience TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            consent INTEGER NOT NULL CHECK (consent IN (0, 1)),
            status TEXT NOT NULL DEFAULT 'Новая',
            created_at TEXT NOT NULL,
            legacy_booking_id INTEGER,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE SET NULL
        )
        """
    )


def _migrate_requests(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "requests"):
        _create_requests_table(connection)
        return
    columns = _column_names(connection, "requests")
    required = {
        "service_id", "slot_start", "slot_end", "slot_block_end",
        "hold_expires_at", "locale", "contact_channel",
    }
    if "service_request" in _table_sql(connection, "requests") and required.issubset(columns):
        return
    rows = connection.execute("SELECT * FROM requests ORDER BY id").fetchall()
    connection.execute("DROP TABLE IF EXISTS requests_v11")
    _create_requests_table(connection, "requests_v11")
    for row in rows:
        values = dict(row)
        request_type = values.get("request_type", "")
        if request_type == "beauty_booking":
            request_type = "service_request"
        if request_type not in REQUEST_TYPES:
            continue
        status = LEGACY_STATUS_MAP.get(values.get("status", ""), values.get("status", "Новая"))
        if status not in REQUEST_STATUSES:
            status = "Новая"
        connection.execute(
            """
            INSERT INTO requests_v11 (
                id, request_type, name, phone, email, organization, service_id,
                service, preferred_date, preferred_time, slot_start, slot_end,
                slot_block_end, hold_expires_at, locale, contact_channel, city,
                experience, message, consent, status, created_at, legacy_booking_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values.get("id"), request_type, values.get("name", ""),
                values.get("phone", ""), values.get("email", ""),
                values.get("organization", ""), values.get("service_id"),
                values.get("service", ""), values.get("preferred_date", ""),
                values.get("preferred_time", ""), values.get("slot_start", ""),
                values.get("slot_end", ""), values.get("slot_block_end", ""),
                values.get("hold_expires_at", ""),
                normalize_locale(values.get("locale", "ru")),
                values.get("contact_channel", "sms"), values.get("city", ""),
                values.get("experience", ""), values.get("message", ""),
                int(values.get("consent", 0)), status,
                values.get("created_at", _now().isoformat(timespec="seconds")),
                values.get("legacy_booking_id"),
            ),
        )
    connection.execute("DROP TABLE requests")
    connection.execute("ALTER TABLE requests_v11 RENAME TO requests")


def _create_support_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS service_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL CHECK (category IN ('Professional', 'Model')),
            name_ru TEXT NOT NULL,
            name_ro TEXT NOT NULL DEFAULT '',
            name_en TEXT NOT NULL DEFAULT '',
            description_ru TEXT NOT NULL DEFAULT '',
            description_ro TEXT NOT NULL DEFAULT '',
            description_en TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_exceptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exception_date TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('closed', 'extra')),
            start_time TEXT NOT NULL DEFAULT '',
            end_time TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sms_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            recipient TEXT NOT NULL,
            locale TEXT NOT NULL CHECK (locale IN ('ru', 'ro', 'en')),
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            created_at TEXT NOT NULL,
            sent_at TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL UNIQUE,
            public_name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            phone_verified INTEGER NOT NULL DEFAULT 0 CHECK (phone_verified IN (0, 1)),
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title_ru TEXT NOT NULL DEFAULT '',
            title_ro TEXT NOT NULL DEFAULT '',
            body_ru TEXT NOT NULL DEFAULT '',
            body_ro TEXT NOT NULL DEFAULT '',
            image_url TEXT NOT NULL DEFAULT '',
            link_url TEXT NOT NULL DEFAULT '',
            translations_approved INTEGER NOT NULL DEFAULT 0 CHECK (translations_approved IN (0, 1)),
            show_scene INTEGER NOT NULL DEFAULT 1 CHECK (show_scene IN (0, 1)),
            show_professional INTEGER NOT NULL DEFAULT 0 CHECK (show_professional IN (0, 1)),
            show_model INTEGER NOT NULL DEFAULT 0 CHECK (show_model IN (0, 1)),
            active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS post_likes (
            post_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, member_id),
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY(member_id) REFERENCES members(id) ON DELETE CASCADE
        )
        """
    )


def _apply_legacy_demo_settings_once(connection: sqlite3.Connection) -> None:
    migration_key = "legacy_demo_settings_replaced"
    completed = connection.execute(
        "SELECT value FROM app_meta WHERE key = ?", (migration_key,)
    ).fetchone()
    if completed:
        return
    for key, legacy_values in LEGACY_DEMO_SETTING_VALUES.items():
        current = connection.execute(
            "SELECT value FROM profile_settings WHERE key = ?", (key,)
        ).fetchone()
        if current and current["value"] in legacy_values:
            connection.execute(
                "UPDATE profile_settings SET value = ? WHERE key = ?",
                (DEFAULT_SETTINGS[key], key),
            )
    connection.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?)",
        (migration_key, "1"),
    )


def _ensure_service_organization(connection: sqlite3.Connection) -> None:
    """Add V1.3 grouping/archive fields and place legacy rows into safe groups."""

    columns = _column_names(connection, "services")
    if "group_id" not in columns:
        connection.execute("ALTER TABLE services ADD COLUMN group_id INTEGER")
    if "sort_order" not in columns:
        connection.execute(
            "ALTER TABLE services ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
        )
    if "archived" not in columns:
        connection.execute(
            "ALTER TABLE services ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 "
            "CHECK (archived IN (0, 1))"
        )

    for category, name_ru, name_ro, description_ru, description_ro, sort_order in DEFAULT_SERVICE_GROUPS:
        exists = connection.execute(
            "SELECT id FROM service_groups WHERE category = ? AND name_ru = ?",
            (category, name_ru),
        ).fetchone()
        if not exists:
            connection.execute(
                """
                INSERT INTO service_groups (
                    category, name_ru, name_ro, description_ru, description_ro,
                    sort_order, active
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    category, name_ru, name_ro, description_ru, description_ro,
                    sort_order,
                ),
            )

    group_ids = {
        (row["category"], row["name_ru"]): int(row["id"])
        for row in connection.execute(
            "SELECT id, category, name_ru FROM service_groups"
        )
    }
    individual_group = group_ids[("Professional", "Индивидуальная работа")]
    learning_group = group_ids[("Professional", "Обучение")]
    model_group = group_ids[("Model", "Модельные проекты")]
    connection.execute(
        """
        UPDATE services
        SET group_id = CASE
            WHEN category = 'Model' THEN ?
            WHEN kind = 'course' THEN ?
            ELSE ?
        END
        WHERE group_id IS NULL
        """,
        (model_group, learning_group, individual_group),
    )
    connection.execute(
        "UPDATE services SET sort_order = id * 10 WHERE sort_order = 0"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_services_group_order "
        "ON services(group_id, archived, sort_order, id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_service_groups_order "
        "ON service_groups(category, active, sort_order, id)"
    )


def _migrate_locale_checks(connection: sqlite3.Connection) -> None:
    """Widen legacy locale checks atomically, retaining rows and dependencies.

    SQLite cannot alter CHECK constraints. Recreate only these two known tables
    before the regular initialization transaction, with foreign keys disabled
    for the table swap. All indexes, triggers and AUTOINCREMENT state survive.
    """
    changes = []
    pattern = r"CHECK\s*\(\s*locale\s+IN\s*\(\s*'ru'\s*,\s*'ro'\s*\)\s*\)"
    for table in ("requests", "sms_outbox"):
        original = _table_sql(connection, table)
        widened, count = re.subn(pattern, "CHECK (locale IN ('ru', 'ro', 'en'))", original, flags=re.I)
        if count:
            changes.append((table, widened))
    if not changes:
        return
    if connection.in_transaction:
        raise RuntimeError("Locale migration must run before database initialization.")
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        for table, widened in changes:
            temporary = f"scena_v17_locale_{table}"
            if _table_exists(connection, temporary):
                raise RuntimeError("Unexpected table blocks locale migration.")
            indexes = connection.execute(
                "SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type IN ('index', 'trigger') AND sql IS NOT NULL",
                (table,),
            ).fetchall()
            sequence = connection.execute("SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)).fetchone() if _table_exists(connection, "sqlite_sequence") else None
            create_sql, replaced = re.subn(
                r'^(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)(?:"' + table + r'"|`' + table + r'`|\[' + table + r'\]|' + table + r')(?=\s|\()',
                lambda match: match.group(1) + temporary,
                widened, count=1, flags=re.I,
            )
            if replaced != 1:
                raise RuntimeError("Unrecognized locale table definition.")
            connection.execute(create_sql)
            columns = [str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")]
            quoted = ", ".join('"' + column.replace('"', '""') + '"' for column in columns)
            connection.execute(f"INSERT INTO {temporary} ({quoted}) SELECT {quoted} FROM {table}")
            connection.execute(f"DROP TABLE {table}")
            connection.execute(f"ALTER TABLE {temporary} RENAME TO {table}")
            if sequence:
                connection.execute("UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = ?", (int(sequence["seq"]), table))
            for row in indexes:
                connection.execute(row["sql"])
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Foreign key verification failed during locale migration.")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def _ensure_english_content_columns(connection: sqlite3.Connection) -> None:
    for table in ("services", "service_groups"):
        columns = _column_names(connection, table)
        for column in ("name_en", "description_en"):
            if column not in columns:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")


def init_db(db_path: str | Path, *, now: datetime | None = None) -> None:
    """Create/migrate the local database without discarding existing user data."""

    with _connect(db_path) as connection:
        _migrate_locale_checks(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS profile_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        previous_signatures = _migrate_services(connection)
        _migrate_requests(connection)
        _create_support_tables(connection)
        _ensure_english_content_columns(connection)
        from scena_publications import initialize_publications

        initialize_publications(connection)
        from scena_cabinet import initialize_cabinet_features

        initialize_cabinet_features(connection, now=_now(now))
        from scena_shop import init_shop
        from scena_prompts import initialize_prompts
        from scena_licensing import initialize_licensing
        init_shop(connection)
        initialize_prompts(connection)
        initialize_licensing(connection)
        if not connection.execute("SELECT 1 FROM app_meta WHERE key='v17_intro_default_migrated'").fetchone():
            connection.execute("UPDATE profile_settings SET value='media/qr-scenes/model.png' WHERE key='model_intro_image' AND value='media/scena-v13/professional-portrait.webp'")
            connection.execute("INSERT INTO app_meta(key,value) VALUES('v17_intro_default_migrated','1')")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_legacy_booking_id
            ON requests(legacy_booking_id)
            WHERE legacy_booking_id IS NOT NULL
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_requests_active_slots
            ON requests(status, slot_start, slot_block_end)
            """
        )
        connection.executemany(
            "INSERT OR IGNORE INTO profile_settings (key, value) VALUES (?, ?)",
            DEFAULT_SETTINGS.items(),
        )
        _apply_legacy_demo_settings_once(connection)

        if (
            previous_signatures == LEGACY_DEFAULT_SERVICES
            or previous_signatures == LEGACY_DEMO_SERVICES
        ):
            connection.execute("DELETE FROM services")
        if connection.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
            connection.executemany(
                """
                INSERT INTO services (
                    category, kind, name, name_ro, description_ru,
                    description_ro, translations_approved, price, duration,
                    buffer_minutes, active
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 1)
                """,
                DEFAULT_SERVICES,
            )

        _ensure_service_organization(connection)

        if _table_exists(connection, "bookings"):
            legacy_rows = connection.execute(
                """
                SELECT id, client_name, client_phone, role_booked, service,
                       booking_date, booking_time, status, created_at
                FROM bookings ORDER BY id
                """
            ).fetchall()
            for row in legacy_rows:
                request_type = (
                    "model_invitation"
                    if "модел" in row["role_booked"].lower()
                    else "service_request"
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO requests (
                        request_type, name, phone, service, preferred_date,
                        preferred_time, consent, status, created_at,
                        legacy_booking_id
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        request_type, row["client_name"], row["client_phone"],
                        row["service"], row["booking_date"], row["booking_time"],
                        LEGACY_STATUS_MAP.get(row["status"], "Новая"),
                        row["created_at"], row["id"],
                    ),
                )


def get_settings(db_path: str | Path) -> dict[str, str]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT key, value FROM profile_settings ORDER BY key"
        ).fetchall()
    settings = {row["key"]: row["value"] for row in rows}
    # A local port fallback must also update QR/caption links for this process.
    # A configured public domain remains the owner's chosen address.
    runtime = os.environ.get("SCENA_LOCAL_BASE_URL", "").strip()
    try:
        current, actual = urlparse(settings.get("public_base_url", "")), urlparse(runtime)
        if current.hostname in {"localhost", "127.0.0.1", "0.0.0.0"} and actual.scheme == "http" and actual.hostname == "localhost" and actual.port and not actual.username and not actual.password:
            settings["public_base_url"] = runtime.rstrip("/")
    except ValueError:
        pass
    return settings


def _connection_settings(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        row["key"]: row["value"]
        for row in connection.execute("SELECT key, value FROM profile_settings")
    }


def save_settings(db_path: str | Path, values: Mapping[str, Any]) -> None:
    allowed = set(DEFAULT_SETTINGS)
    updates = [
        (key, str(value).strip()) for key, value in values.items() if key in allowed
    ]
    if not updates:
        return
    with _connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO profile_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            updates,
        )
        connection.commit()


def list_services(
    db_path: str | Path,
    category: str | None = None,
    *,
    kind: str | None = None,
    active_only: bool = True,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if category is not None:
        if category not in SERVICE_CATEGORIES:
            raise RequestValidationError("Неизвестное направление.")
        clauses.append("s.category = ?")
        params.append(category)
    if kind is not None:
        if kind not in SERVICE_KINDS:
            raise RequestValidationError("Неизвестный тип предложения.")
        clauses.append("s.kind = ?")
        params.append(kind)
    if active_only:
        clauses.append("s.active = 1")
        clauses.append("(sg.id IS NULL OR sg.active = 1)")
    if not include_archived:
        clauses.append("s.archived = 0")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT s.*, sg.name_ru AS group_name_ru, sg.name_ro AS group_name_ro,
                   sg.name_en AS group_name_en,
                   sg.description_ru AS group_description_ru,
                   sg.description_ro AS group_description_ro,
                   sg.description_en AS group_description_en,
                   sg.sort_order AS group_sort_order,
                   sg.active AS group_active
            FROM services AS s
            LEFT JOIN service_groups AS sg ON sg.id = s.group_id
            {where}
            ORDER BY CASE s.category WHEN 'Professional' THEN 0 ELSE 1 END,
                     COALESCE(sg.sort_order, 999999),
                     s.sort_order, s.id
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def list_service_groups(
    db_path: str | Path,
    category: str | None = None,
    *,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if category is not None:
        if category not in SERVICE_CATEGORIES:
            raise RequestValidationError("Неизвестное направление.")
        clauses.append("g.category = ?")
        params.append(category)
    if active_only:
        clauses.append("g.active = 1")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT g.*,
                   COUNT(CASE WHEN s.archived = 0 THEN 1 END) AS service_count,
                   COUNT(CASE WHEN s.archived = 0 AND s.active = 1 THEN 1 END) AS public_count
            FROM service_groups AS g
            LEFT JOIN services AS s ON s.group_id = g.id
            {where}
            GROUP BY g.id
            ORDER BY CASE g.category WHEN 'Professional' THEN 0 ELSE 1 END,
                     g.sort_order, g.id
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def add_service_group(
    db_path: str | Path,
    *,
    category: str,
    name_ru: str,
    name_ro: str = "",
    description_ru: str = "",
    description_ro: str = "",
    name_en: str = "",
    description_en: str = "",
) -> int:
    if category not in SERVICE_CATEGORIES:
        raise RequestValidationError("Неизвестное направление.")
    clean_name = _require_text(name_ru, "Укажите название группы.")
    with _connect(db_path) as connection:
        duplicate = connection.execute(
            """
            SELECT 1 FROM service_groups
            WHERE category = ? AND lower(name_ru) = lower(?)
            """,
            (category, clean_name),
        ).fetchone()
        if duplicate:
            raise RequestValidationError("Группа с таким названием уже существует.")
        next_order = int(connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM service_groups WHERE category = ?",
            (category,),
        ).fetchone()[0])
        cursor = connection.execute(
            """
            INSERT INTO service_groups (
                category, name_ru, name_ro, description_ru, description_ro,
                sort_order, name_en, description_en, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                category, clean_name, str(name_ro or "").strip(),
                str(description_ru or "").strip(),
                str(description_ro or "").strip(), next_order,
                str(name_en or "").strip(), str(description_en or "").strip(),
            ),
        )
    return int(cursor.lastrowid)


def update_service_group(
    db_path: str | Path,
    group_id: int,
    *,
    name_ru: str,
    name_ro: str,
    description_ru: str = "",
    description_ro: str = "",
    name_en: str | None = None,
    description_en: str | None = None,
) -> None:
    clean_name = _require_text(name_ru, "Укажите название группы.")
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT id FROM service_groups WHERE id = ?", (int(group_id),)
        ).fetchone()
        if not row:
            raise RequestValidationError("Группа не найдена.")
        connection.execute(
            """
            UPDATE service_groups SET
                name_ru = ?, name_ro = ?, description_ru = ?, description_ro = ?,
                name_en = COALESCE(?, name_en), description_en = COALESCE(?, description_en)
            WHERE id = ?
            """,
            (
                clean_name, str(name_ro or "").strip(),
                str(description_ru or "").strip(),
                str(description_ro or "").strip(),
                None if name_en is None else str(name_en).strip(),
                None if description_en is None else str(description_en).strip(), int(group_id),
            ),
        )


def set_service_group_active(
    db_path: str | Path, group_id: int, active: bool
) -> None:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT id FROM service_groups WHERE id = ?", (int(group_id),)
        ).fetchone()
        if not row:
            raise RequestValidationError("Группа не найдена.")
        connection.execute(
            "UPDATE service_groups SET active = ? WHERE id = ?",
            (int(bool(active)), int(group_id)),
        )


def _group_for_service(
    connection: sqlite3.Connection,
    category: str,
    kind: str,
    group_id: int | None,
) -> int:
    if group_id is not None:
        row = connection.execute(
            "SELECT id, category FROM service_groups WHERE id = ?",
            (int(group_id),),
        ).fetchone()
        if not row or row["category"] != category:
            raise RequestValidationError("Выберите группу из того же раздела.")
        return int(row["id"])
    preferred_name = (
        "Модельные проекты" if category == "Model"
        else "Обучение" if kind == "course"
        else "Индивидуальная работа"
    )
    row = connection.execute(
        """
        SELECT id FROM service_groups
        WHERE category = ?
        ORDER BY CASE WHEN name_ru = ? THEN 0 ELSE 1 END, sort_order, id
        LIMIT 1
        """,
        (category, preferred_name),
    ).fetchone()
    if not row:
        name_ru = "Основные услуги" if category == "Professional" else "Модельные форматы"
        name_ro = "Servicii principale" if category == "Professional" else "Formate Model"
        cursor = connection.execute(
            """
            INSERT INTO service_groups (
                category, name_ru, name_ro, description_ru, description_ro,
                sort_order, active
            ) VALUES (?, ?, ?, '', '', 10, 1)
            """,
            (category, name_ru, name_ro),
        )
        return int(cursor.lastrowid)
    return int(row["id"])


def _service_publication_ready(
    name: str,
    name_ro: str,
    description_ru: str,
    description_ro: str,
    translations_approved: bool,
) -> bool:
    return bool(
        str(name).strip()
        and str(name_ro).strip()
        and str(description_ru).strip()
        and str(description_ro).strip()
        and translations_approved
    )


def add_service(
    db_path: str | Path,
    category: str,
    name: str,
    price: float,
    duration: int,
    *,
    kind: str = "appointment",
    buffer_minutes: int = 10,
    name_ro: str = "",
    description_ru: str = "",
    description_ro: str = "",
    translations_approved: bool = False,
    group_id: int | None = None,
    name_en: str = "",
    description_en: str = "",
) -> int:
    clean_name = _require_text(name, "Укажите название.")
    if category not in SERVICE_CATEGORIES:
        raise RequestValidationError("Неизвестное направление.")
    if kind not in SERVICE_KINDS:
        raise RequestValidationError("Неизвестный тип предложения.")
    if float(price) < 0 or int(duration) < 5 or int(buffer_minutes) < 0:
        raise RequestValidationError("Проверьте цену, продолжительность и перерыв.")
    clean_name_ro = str(name_ro or "").strip()
    clean_description_ru = str(description_ru or "").strip()
    clean_description_ro = str(description_ro or "").strip()
    publication_ready = _service_publication_ready(
        clean_name, clean_name_ro, clean_description_ru,
        clean_description_ro, bool(translations_approved),
    )
    if translations_approved and not publication_ready:
        raise RequestValidationError(
            "Для публикации заполните название и описание на RU и RO."
        )
    with _connect(db_path) as connection:
        selected_group_id = _group_for_service(
            connection, category, kind, group_id
        )
        sort_order = int(connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM services WHERE group_id = ?",
            (selected_group_id,),
        ).fetchone()[0])
        cursor = connection.execute(
            """
            INSERT INTO services (
                category, kind, name, name_ro, description_ru,
                description_ro, translations_approved, price, duration,
                buffer_minutes, active, group_id, sort_order, name_en, description_en, archived
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                category, kind, clean_name, clean_name_ro,
                clean_description_ru, clean_description_ro,
                int(bool(translations_approved)), float(price), int(duration),
                int(buffer_minutes), int(publication_ready),
                selected_group_id, sort_order,
                str(name_en or "").strip(), str(description_en or "").strip(),
            ),
        )
    return int(cursor.lastrowid)


def update_service(
    db_path: str | Path,
    service_id: int,
    *,
    category: str,
    name: str,
    price: float,
    duration: int,
    kind: str | None = None,
    buffer_minutes: int | None = None,
    name_ro: str | None = None,
    description_ru: str | None = None,
    description_ro: str | None = None,
    translations_approved: bool | None = None,
    group_id: int | None = None,
    name_en: str | None = None,
    description_en: str | None = None,
) -> None:
    if category not in SERVICE_CATEGORIES:
        raise RequestValidationError("Неизвестное направление.")
    clean_name = _require_text(name, "Укажите название.")
    if float(price) < 0 or int(duration) < 5:
        raise RequestValidationError("Проверьте цену и продолжительность.")
    with _connect(db_path) as connection:
        current = connection.execute(
            "SELECT * FROM services WHERE id = ?", (int(service_id),)
        ).fetchone()
        if not current:
            raise RequestValidationError("Предложение не найдено.")
        next_kind = kind if kind is not None else current["kind"]
        next_buffer = int(buffer_minutes) if buffer_minutes is not None else int(current["buffer_minutes"])
        if next_kind not in SERVICE_KINDS or next_buffer < 0:
            raise RequestValidationError("Проверьте тип предложения и перерыв.")
        next_name_ro = current["name_ro"] if name_ro is None else str(name_ro).strip()
        next_description_ru = current["description_ru"] if description_ru is None else str(description_ru).strip()
        next_description_ro = current["description_ro"] if description_ro is None else str(description_ro).strip()
        next_name_en = current["name_en"] if name_en is None else str(name_en).strip()
        next_description_en = current["description_en"] if description_en is None else str(description_en).strip()
        next_approved = int(current["translations_approved"]) if translations_approved is None else int(bool(translations_approved))
        current_group = connection.execute(
            "SELECT category FROM service_groups WHERE id = ?",
            (current["group_id"],),
        ).fetchone()
        requested_group = group_id
        if requested_group is None and current_group and current_group["category"] == category:
            requested_group = int(current["group_id"])
        next_group_id = _group_for_service(
            connection, category, next_kind, requested_group
        )
        next_active = int(current["active"])
        if next_active and not _service_publication_ready(
            clean_name, next_name_ro, next_description_ru,
            next_description_ro, bool(next_approved),
        ):
            next_active = 0
        connection.execute(
            """
            UPDATE services SET
                category = ?, kind = ?, name = ?, name_ro = ?,
                description_ru = ?, description_ro = ?, translations_approved = ?,
                price = ?, duration = ?, buffer_minutes = ?, active = ?,
                group_id = ?, name_en = ?, description_en = ?
            WHERE id = ?
            """,
            (
                category, next_kind, clean_name,
                next_name_ro, next_description_ru, next_description_ro,
                next_approved, float(price), int(duration), next_buffer,
                next_active, next_group_id, next_name_en, next_description_en, int(service_id),
            ),
        )


def set_service_active(db_path: str | Path, service_id: int, active: bool) -> None:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM services WHERE id = ?", (int(service_id),)
        ).fetchone()
        if not row:
            raise RequestValidationError("Предложение не найдено.")
        if active and bool(row["archived"]):
            raise RequestValidationError("Сначала верните услугу из архива.")
        if active and not _service_publication_ready(
            row["name"], row["name_ro"], row["description_ru"],
            row["description_ro"], bool(row["translations_approved"]),
        ):
            raise RequestValidationError(
                "Перед публикацией подтвердите названия и описания на RU и RO."
            )
        connection.execute(
            "UPDATE services SET active = ? WHERE id = ?",
            (int(bool(active)), int(service_id)),
        )


def service_request_count(db_path: str | Path, service_id: int) -> int:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT id FROM services WHERE id = ?", (int(service_id),)
        ).fetchone()
        if not row:
            raise RequestValidationError("Предложение не найдено.")
        return int(connection.execute(
            "SELECT COUNT(*) FROM requests WHERE service_id = ?",
            (int(service_id),),
        ).fetchone()[0])


def archive_service(db_path: str | Path, service_id: int) -> None:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT id FROM services WHERE id = ?", (int(service_id),)
        ).fetchone()
        if not row:
            raise RequestValidationError("Предложение не найдено.")
        connection.execute(
            "UPDATE services SET active = 0, archived = 1 WHERE id = ?",
            (int(service_id),),
        )


def restore_service(db_path: str | Path, service_id: int) -> None:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT id FROM services WHERE id = ?", (int(service_id),)
        ).fetchone()
        if not row:
            raise RequestValidationError("Предложение не найдено.")
        connection.execute(
            "UPDATE services SET active = 0, archived = 0 WHERE id = ?",
            (int(service_id),),
        )


def delete_service(db_path: str | Path, service_id: int) -> None:
    """Permanently delete only an unused service; requests keep their history."""

    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT id FROM services WHERE id = ?", (int(service_id),)
        ).fetchone()
        if not row:
            raise RequestValidationError("Предложение не найдено.")
        requests = int(connection.execute(
            "SELECT COUNT(*) FROM requests WHERE service_id = ?",
            (int(service_id),),
        ).fetchone()[0])
        if requests:
            raise RequestValidationError(
                "Услуга связана с заявками. Её можно только отправить в архив."
            )
        connection.execute(
            "DELETE FROM services WHERE id = ?", (int(service_id),)
        )


def _require_text(value: Any, message: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise RequestValidationError(message)
    return clean


def normalize_moldova_phone(phone: Any) -> str:
    clean = _require_text(phone, "Укажите номер телефона.")
    digits = re.sub(r"\D", "", clean)
    if len(digits) == 9 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 8:
        digits = "373" + digits
    if len(digits) != 11 or not digits.startswith("373"):
        raise RequestValidationError("Поддерживаются только номера Молдовы +373.")
    return "+" + digits


def _validate_email(email: Any) -> str:
    clean = str(email or "").strip()
    if clean and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", clean):
        raise RequestValidationError("Проверьте адрес электронной почты.")
    return clean


def _locale(value: str) -> str:
    return normalize_locale(value, fallback="ro")


def _parse_hhmm(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise RequestValidationError("Проверьте время.") from exc


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RequestValidationError("Проверьте дату.") from exc


def _setting_int(settings: Mapping[str, str], key: str, minimum: int) -> int:
    try:
        value = int(settings[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise RequestValidationError(f"Некорректная настройка: {key}.") from exc
    if value < minimum:
        raise RequestValidationError(f"Некорректная настройка: {key}.")
    return value


def _service_row(connection: sqlite3.Connection, service_id: int) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM services WHERE id = ?", (int(service_id),)
    ).fetchone()
    if not row or not int(row["active"]):
        raise RequestValidationError("Предложение недоступно.")
    return row


def _working_periods(
    connection: sqlite3.Connection,
    target: date,
    settings: Mapping[str, str],
) -> list[tuple[time, time]]:
    exceptions = connection.execute(
        """
        SELECT kind, start_time, end_time FROM schedule_exceptions
        WHERE exception_date = ? ORDER BY id
        """,
        (target.isoformat(),),
    ).fetchall()
    if any(row["kind"] == "closed" for row in exceptions):
        regular: list[tuple[time, time]] = []
    else:
        weekdays = {
            int(value)
            for value in settings.get("schedule_weekdays", "").split(",")
            if value.strip().isdigit()
        }
        regular = []
        if target.weekday() in weekdays:
            start = _parse_hhmm(settings["schedule_start"])
            end = _parse_hhmm(settings["schedule_end"])
            break_start = settings.get("schedule_break_start", "").strip()
            break_end = settings.get("schedule_break_end", "").strip()
            if break_start and break_end:
                pause_start = _parse_hhmm(break_start)
                pause_end = _parse_hhmm(break_end)
                if start < pause_start < pause_end < end:
                    regular.extend(((start, pause_start), (pause_end, end)))
                else:
                    regular.append((start, end))
            else:
                regular.append((start, end))
    extras: list[tuple[time, time]] = []
    for row in exceptions:
        if row["kind"] == "extra":
            start = _parse_hhmm(row["start_time"])
            end = _parse_hhmm(row["end_time"])
            if start < end:
                extras.append((start, end))
    periods = sorted(set(regular + extras))
    merged: list[tuple[time, time]] = []
    for start, end in periods:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _expire_pending(connection: sqlite3.Connection, now: datetime) -> list[int]:
    rows = connection.execute(
        """
        SELECT * FROM requests
        WHERE status IN ('Ожидает подтверждения', 'Связались')
          AND hold_expires_at != ''
          AND hold_expires_at <= ?
        ORDER BY id
        """,
        (now.isoformat(timespec="seconds"),),
    ).fetchall()
    expired: list[int] = []
    for row in rows:
        connection.execute(
            "UPDATE requests SET status = 'Срок подтверждения истёк' WHERE id = ?",
            (row["id"],),
        )
        _queue_sms(connection, dict(row), "hold_expired", now)
        expired.append(int(row["id"]))
    return expired


def expire_pending_requests(
    db_path: str | Path,
    *,
    now: datetime | None = None,
) -> list[int]:
    moment = _now(now)
    with _connect(db_path) as connection:
        return _expire_pending(connection, moment)


def _available_slots(
    connection: sqlite3.Connection,
    service_id: int,
    target_date: str,
    now: datetime,
) -> list[str]:
    service = _service_row(connection, service_id)
    if service["kind"] != "appointment":
        return []
    target = _parse_date(target_date)
    settings = _connection_settings(connection)
    horizon = _setting_int(settings, "booking_horizon_days", 1)
    lead = _setting_int(settings, "minimum_lead_hours", 0)
    interval = _setting_int(settings, "slot_interval_minutes", 1)
    earliest = now + timedelta(hours=lead)
    if target < now.date() or target > now.date() + timedelta(days=horizon):
        return []

    _expire_pending(connection, now)
    reserved = connection.execute(
        """
        SELECT slot_start, slot_block_end FROM requests
        WHERE status IN ('Ожидает подтверждения', 'Связались', 'Подтверждена')
          AND slot_start != '' AND slot_block_end != ''
        """
    ).fetchall()
    blocked = [
        (
            datetime.fromisoformat(row["slot_start"]),
            datetime.fromisoformat(row["slot_block_end"]),
        )
        for row in reserved
    ]

    duration = timedelta(minutes=int(service["duration"]))
    buffer_time = timedelta(minutes=int(service["buffer_minutes"]))
    step = timedelta(minutes=interval)
    slots: list[str] = []
    for period_start, period_end in _working_periods(connection, target, settings):
        candidate = datetime.combine(target, period_start, CHISINAU)
        period_finish = datetime.combine(target, period_end, CHISINAU)
        while candidate + duration + buffer_time <= period_finish:
            block_end = candidate + duration + buffer_time
            overlaps = any(
                candidate < existing_end and block_end > existing_start
                for existing_start, existing_end in blocked
            )
            if candidate >= earliest and not overlaps:
                slots.append(candidate.strftime("%H:%M"))
            candidate += step
    return slots


def generate_available_slots(
    db_path: str | Path,
    service_id: int,
    target_date: str,
    *,
    now: datetime | None = None,
) -> list[str]:
    moment = _now(now)
    with _connect(db_path) as connection:
        return _available_slots(connection, service_id, target_date, moment)


def list_available_dates(
    db_path: str | Path,
    service_id: int,
    *,
    now: datetime | None = None,
    limit: int = 21,
) -> list[str]:
    moment = _now(now)
    settings = get_settings(db_path)
    horizon = _setting_int(settings, "booking_horizon_days", 1)
    result: list[str] = []
    for offset in range(horizon + 1):
        candidate = (moment.date() + timedelta(days=offset)).isoformat()
        if generate_available_slots(db_path, service_id, candidate, now=moment):
            result.append(candidate)
            if len(result) >= limit:
                break
    return result


def add_schedule_exception(
    db_path: str | Path,
    exception_date: str,
    kind: str,
    *,
    start_time: str = "",
    end_time: str = "",
    note: str = "",
) -> int:
    _parse_date(exception_date)
    if kind not in {"closed", "extra"}:
        raise RequestValidationError("Неизвестный тип исключения графика.")
    if kind == "extra":
        start = _parse_hhmm(start_time)
        end = _parse_hhmm(end_time)
        if start >= end:
            raise RequestValidationError("Проверьте дополнительное рабочее время.")
    else:
        start_time = ""
        end_time = ""
    with _connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO schedule_exceptions (
                exception_date, kind, start_time, end_time, note
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (exception_date, kind, start_time, end_time, str(note or "").strip()),
        )
    return int(cursor.lastrowid)


def list_schedule_exceptions(db_path: str | Path) -> list[dict[str, Any]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM schedule_exceptions ORDER BY exception_date, id"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_schedule_exception(db_path: str | Path, exception_id: int) -> None:
    with _connect(db_path) as connection:
        cursor = connection.execute(
            "DELETE FROM schedule_exceptions WHERE id = ?", (int(exception_id),)
        )
        if cursor.rowcount != 1:
            raise RequestValidationError("Исключение графика не найдено.")


def _hold_hours(row: Mapping[str, Any]) -> int:
    """Return the stored hold duration instead of assuming the default."""

    try:
        created_at = datetime.fromisoformat(str(row.get("created_at", "")))
        expires_at = datetime.fromisoformat(str(row.get("hold_expires_at", "")))
        seconds = max(0.0, (expires_at - created_at).total_seconds())
        return max(1, round(seconds / 3600))
    except (TypeError, ValueError):
        return 24


def _sms_body(row: Mapping[str, Any], event: str) -> str:
    locale = _locale(str(row.get("locale", "ro")))
    request_id = row.get("id", "")
    service = str(translate_literaltext(locale, str(row.get("service", "")).strip()))
    when = " ".join(
        value for value in (
            str(row.get("preferred_date", "")).strip(),
            str(row.get("preferred_time", "")).strip(),
        ) if value
    )
    subject = when or service
    hold_hours = _hold_hours(row)
    if locale == "en":
        templates = {
            "request_received": f"SCENA: request #{request_id} received. Your time {when} is held for {hold_hours} hours. Confirmation will follow separately.",
            "general_request_received": f"SCENA: request #{request_id} received. A reply and confirmation will follow separately.",
            "course_preregistration_received": f"SCENA: preregistration #{request_id} for {service} received. Your place is not automatically confirmed.",
            "confirmed": f"SCENA: request #{request_id} for {subject} is confirmed." if subject else f"SCENA: request #{request_id} is confirmed.",
            "rejected": f"SCENA: request #{request_id} was not confirmed. Contact the specialist for details.",
            "cancelled": f"SCENA: request #{request_id} was cancelled.",
            "hold_expired": f"SCENA: the {hold_hours}-hour hold for request #{request_id} has expired. The time is available again.",
        }
    elif locale == "ro":
        templates = {
            "request_received": (
                f"SCENA: cererea #{request_id} a fost primită. Ora {when} este "
                f"rezervată temporar pentru {hold_hours} ore. Confirmarea va veni separat."
            ),
            "general_request_received": (
                f"SCENA: cererea #{request_id} a fost primită. "
                "Răspunsul și confirmarea vor veni separat."
            ),
            "course_preregistration_received": (
                f"SCENA: preînscrierea #{request_id} pentru «{service}» a fost primită. "
                "Locul nu este confirmat automat."
            ),
            "confirmed": (
                f"SCENA: cererea #{request_id} pentru {subject} a fost confirmată."
                if subject else f"SCENA: cererea #{request_id} a fost confirmată."
            ),
            "rejected": f"SCENA: cererea #{request_id} nu a fost confirmată. Contactați specialistul pentru detalii.",
            "cancelled": f"SCENA: cererea #{request_id} a fost anulată.",
            "hold_expired": f"SCENA: termenul de {hold_hours} ore pentru cererea #{request_id} a expirat. Ora este disponibilă din nou.",
        }
    else:
        templates = {
            "request_received": (
                f"SCENA: заявка №{request_id} получена. Время {when} удерживается "
                f"на {hold_hours} ч. Подтверждение придёт отдельно."
            ),
            "general_request_received": (
                f"SCENA: заявка №{request_id} получена. "
                "Ответ и подтверждение придут отдельно."
            ),
            "course_preregistration_received": (
                f"SCENA: предзапись №{request_id} на «{service}» получена. "
                "Место не подтверждается автоматически."
            ),
            "confirmed": (
                f"SCENA: заявка №{request_id} на {subject} подтверждена."
                if subject else f"SCENA: заявка №{request_id} подтверждена."
            ),
            "rejected": f"SCENA: заявка №{request_id} не подтверждена. Свяжитесь с мастером для уточнения.",
            "cancelled": f"SCENA: заявка №{request_id} отменена.",
            "hold_expired": f"SCENA: срок удержания ({hold_hours} ч.) заявки №{request_id} истёк. Время снова доступно.",
        }
    return templates[event]


def _queue_sms(
    connection: sqlite3.Connection,
    row: Mapping[str, Any],
    event: str,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO sms_outbox (
            request_id, event, recipient, locale, body, status, created_at
        ) VALUES (?, ?, ?, ?, ?, 'queued', ?)
        """,
        (
            int(row["id"]), event, str(row["phone"]),
            _locale(str(row.get("locale", "ro"))), _sms_body(row, event),
            now.isoformat(timespec="seconds"),
        ),
    )


def list_sms_outbox(db_path: str | Path) -> list[dict[str, Any]]:
    with _connect(db_path) as connection:
        rows = connection.execute("SELECT * FROM sms_outbox ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def _base_contact(
    *, name: str, phone: str, email: str, consent: bool
) -> tuple[str, str, str]:
    clean_name = _require_text(name, "Укажите имя или название организации.")
    clean_phone = normalize_moldova_phone(phone)
    clean_email = _validate_email(email)
    if not consent:
        raise RequestValidationError("Необходимо согласие на обработку контактных данных.")
    return clean_name, clean_phone, clean_email


def create_service_request(
    db_path: str | Path,
    *,
    service_id: int,
    slot_date: str,
    slot_time: str,
    name: str,
    phone: str,
    email: str = "",
    message: str = "",
    consent: bool = False,
    locale: str = "ro",
    now: datetime | None = None,
) -> int:
    clean_name, clean_phone, clean_email = _base_contact(
        name=name, phone=phone, email=email, consent=consent
    )
    moment = _now(now)
    target = _parse_date(slot_date)
    chosen_time = _parse_hhmm(slot_time)
    slot_start = datetime.combine(target, chosen_time, CHISINAU)
    connection = _connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        service = _service_row(connection, service_id)
        if service["kind"] != "appointment":
            raise RequestValidationError("Для этого предложения не используется календарь.")
        available = _available_slots(connection, service_id, slot_date, moment)
        if slot_time not in available:
            raise RequestValidationError("Выбранное время уже недоступно. Выберите другое.")
        duration = timedelta(minutes=int(service["duration"]))
        buffer_time = timedelta(minutes=int(service["buffer_minutes"]))
        hold_hours = _setting_int(
            _connection_settings(connection), "pending_hold_hours", 1
        )
        cursor = connection.execute(
            """
            INSERT INTO requests (
                request_type, name, phone, email, service_id, service,
                preferred_date, preferred_time, slot_start, slot_end,
                slot_block_end, hold_expires_at, locale, message, consent,
                status, created_at
            ) VALUES (
                'service_request', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,
                'Ожидает подтверждения', ?
            )
            """,
            (
                clean_name, clean_phone, clean_email, int(service_id),
                service["name"], slot_date, slot_time,
                slot_start.isoformat(timespec="minutes"),
                (slot_start + duration).isoformat(timespec="minutes"),
                (slot_start + duration + buffer_time).isoformat(timespec="minutes"),
                (moment + timedelta(hours=hold_hours)).isoformat(timespec="seconds"),
                _locale(locale), str(message or "").strip(),
                moment.isoformat(timespec="seconds"),
            ),
        )
        request_id = int(cursor.lastrowid)
        row = dict(connection.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)
        ).fetchone())
        _queue_sms(connection, row, "request_received", moment)
        connection.commit()
        return request_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_course_preregistration(
    db_path: str | Path,
    *,
    service_id: int,
    name: str,
    phone: str,
    email: str = "",
    message: str = "",
    consent: bool = False,
    locale: str = "ro",
    now: datetime | None = None,
) -> int:
    clean_name, clean_phone, clean_email = _base_contact(
        name=name, phone=phone, email=email, consent=consent
    )
    moment = _now(now)
    with _connect(db_path) as connection:
        service = _service_row(connection, service_id)
        if service["kind"] != "course":
            raise RequestValidationError("Это предложение не является курсом.")
        cursor = connection.execute(
            """
            INSERT INTO requests (
                request_type, name, phone, email, service_id, service,
                locale, message, consent, status, created_at
            ) VALUES (
                'course_preregistration', ?, ?, ?, ?, ?, ?, ?, 1, 'Новая', ?
            )
            """,
            (
                clean_name, clean_phone, clean_email, int(service_id),
                service["name"], _locale(locale), str(message or "").strip(),
                moment.isoformat(timespec="seconds"),
            ),
        )
        request_id = int(cursor.lastrowid)
        row = dict(connection.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)
        ).fetchone())
        _queue_sms(connection, row, "course_preregistration_received", moment)
    return request_id


def create_request(
    db_path: str | Path,
    *,
    request_type: str,
    name: str,
    phone: str,
    email: str = "",
    organization: str = "",
    service: str = "",
    preferred_date: str = "",
    preferred_time: str = "",
    city: str = "",
    experience: str = "",
    message: str = "",
    consent: bool = False,
    locale: str = "ro",
    now: datetime | None = None,
) -> int:
    if request_type == "beauty_booking":
        raise RequestValidationError("Используйте запись по доступному времени мастера.")
    if request_type not in {"model_invitation", "model_application"}:
        raise RequestValidationError("Неизвестный тип заявки.")
    clean_name, clean_phone, clean_email = _base_contact(
        name=name, phone=phone, email=email, consent=consent
    )
    clean_service = str(service or "").strip()
    clean_date = str(preferred_date or "").strip()
    clean_time = str(preferred_time or "").strip()
    clean_city = str(city or "").strip()
    clean_experience = str(experience or "").strip()
    clean_organization = str(organization or "").strip()
    clean_message = str(message or "").strip()
    if request_type == "model_invitation":
        _require_text(clean_organization, "Укажите бренд или организацию.")
        _require_text(clean_service, "Укажите формат модельной работы.")
        _require_text(clean_date, "Укажите предполагаемую дату проекта.")
        _require_text(clean_message, "Добавьте краткий бриф проекта.")
    else:
        _require_text(clean_city, "Укажите город.")
        _require_text(clean_experience, "Выберите уровень опыта.")
    moment = _now(now)
    with _connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO requests (
                request_type, name, phone, email, organization, service,
                preferred_date, preferred_time, locale, city, experience,
                message, consent, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'Новая', ?)
            """,
            (
                request_type, clean_name, clean_phone, clean_email,
                clean_organization, clean_service, clean_date, clean_time,
                _locale(locale), clean_city, clean_experience, clean_message,
                moment.isoformat(timespec="seconds"),
            ),
        )
        request_id = int(cursor.lastrowid)
        row = dict(connection.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)
        ).fetchone())
        _queue_sms(connection, row, "general_request_received", moment)
    return request_id


def list_requests(
    db_path: str | Path,
    request_type: str | None = None,
) -> list[dict[str, Any]]:
    params: tuple[Any, ...] = ()
    where = ""
    if request_type:
        if request_type not in REQUEST_TYPES:
            raise RequestValidationError("Неизвестный тип заявки.")
        where = " WHERE request_type = ?"
        params = (request_type,)
    with _connect(db_path) as connection:
        _expire_pending(connection, _now())
        rows = connection.execute(
            f"SELECT * FROM requests{where} ORDER BY id DESC", params
        ).fetchall()
    return [dict(row) for row in rows]


def update_request_status(
    db_path: str | Path,
    request_id: int,
    status: str,
    *,
    now: datetime | None = None,
) -> None:
    if status not in REQUEST_STATUSES:
        raise RequestValidationError("Неизвестный статус заявки.")
    moment = _now(now)
    with _connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _expire_pending(connection, moment)
        row = connection.execute(
            "SELECT * FROM requests WHERE id = ?", (int(request_id),)
        ).fetchone()
        if not row:
            raise RequestValidationError("Заявка не найдена.")
        if row["status"] == status:
            return
        if status == "Подтверждена" and row["slot_start"] and row["slot_block_end"]:
            if row["status"] == "Срок подтверждения истёк":
                raise RequestValidationError(
                    "Срок удержания истёк. Сначала согласуйте с клиентом новое доступное время."
                )
            conflict = connection.execute(
                """
                SELECT id FROM requests
                WHERE id != ?
                  AND status IN ('Ожидает подтверждения', 'Связались', 'Подтверждена')
                  AND slot_start != '' AND slot_block_end != ''
                  AND slot_start < ? AND slot_block_end > ?
                LIMIT 1
                """,
                (int(request_id), row["slot_block_end"], row["slot_start"]),
            ).fetchone()
            if conflict:
                raise RequestValidationError(
                    "Это время уже занято другой заявкой. Согласуйте новое время."
                )
        connection.execute(
            "UPDATE requests SET status = ? WHERE id = ?", (status, int(request_id))
        )
        event = {
            "Подтверждена": "confirmed",
            "Отклонена": "rejected",
            "Отменена": "cancelled",
        }.get(status)
        if event:
            _queue_sms(connection, dict(row), event, moment)


def add_post(
    db_path: str | Path,
    *,
    title_ru: str,
    title_ro: str,
    body_ru: str,
    body_ro: str,
    image_url: str = "",
    link_url: str = "",
    translations_approved: bool = False,
    show_scene: bool = True,
    show_professional: bool = False,
    show_model: bool = False,
) -> int:
    if not str(body_ru).strip() and not str(body_ro).strip():
        raise RequestValidationError("Добавьте текст публикации.")
    with _connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO posts (
                title_ru, title_ro, body_ru, body_ro, image_url, link_url,
                translations_approved, show_scene, show_professional,
                show_model, active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                str(title_ru or "").strip(), str(title_ro or "").strip(),
                str(body_ru or "").strip(), str(body_ro or "").strip(),
                str(image_url or "").strip(), str(link_url or "").strip(),
                int(bool(translations_approved)), int(bool(show_scene)),
                int(bool(show_professional)), int(bool(show_model)),
                _now().isoformat(timespec="seconds"),
            ),
        )
    return int(cursor.lastrowid)


def set_post_active(db_path: str | Path, post_id: int, active: bool) -> None:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM posts WHERE id = ?", (int(post_id),)
        ).fetchone()
        if not row:
            raise RequestValidationError("Публикация не найдена.")
        if active and not (
            row["body_ru"].strip() and row["body_ro"].strip()
            and int(row["translations_approved"])
        ):
            raise RequestValidationError(
                "Публикация возможна только после подтверждения версий RU и RO."
            )
        connection.execute(
            "UPDATE posts SET active = ? WHERE id = ?",
            (int(bool(active)), int(post_id)),
        )


def list_posts(
    db_path: str | Path,
    destination: str | None = "scene",
    *,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    destination_columns = {
        "scene": "show_scene",
        "professional": "show_professional",
        "model": "show_model",
    }
    if destination is not None and destination not in destination_columns:
        raise RequestValidationError("Неизвестное место публикации.")
    clauses: list[str] = []
    if destination is not None:
        clauses.append(f"p.{destination_columns[destination]} = 1")
    if active_only:
        clauses.append("p.active = 1")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT p.*, COUNT(l.member_id) AS like_count
            FROM posts p
            LEFT JOIN post_likes l ON l.post_id = p.id
            {where}
            GROUP BY p.id
            ORDER BY p.id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def toggle_post_like(db_path: str | Path, post_id: int, member_id: int) -> bool:
    """Toggle a like for an already SMS-verified member; return the new state."""

    with _connect(db_path) as connection:
        post = connection.execute(
            "SELECT active FROM posts WHERE id = ?", (int(post_id),)
        ).fetchone()
        member = connection.execute(
            "SELECT phone_verified FROM members WHERE id = ?", (int(member_id),)
        ).fetchone()
        if not post or not int(post["active"]):
            raise RequestValidationError("Публикация недоступна.")
        if not member or not int(member["phone_verified"]):
            raise RequestValidationError("Лайк доступен после входа по SMS.")
        existing = connection.execute(
            "SELECT 1 FROM post_likes WHERE post_id = ? AND member_id = ?",
            (int(post_id), int(member_id)),
        ).fetchone()
        if existing:
            connection.execute(
                "DELETE FROM post_likes WHERE post_id = ? AND member_id = ?",
                (int(post_id), int(member_id)),
            )
            return False
        connection.execute(
            """
            INSERT INTO post_likes (post_id, member_id, created_at)
            VALUES (?, ?, ?)
            """,
            (int(post_id), int(member_id), _now().isoformat(timespec="seconds")),
        )
        return True


def get_admin_password() -> str | None:
    value = os.environ.get("SCENA_ADMIN_PASSWORD", "").strip()
    return value or None


def verify_admin_password(candidate: str, configured_password: str | None) -> bool:
    if not configured_password:
        return False
    return hmac.compare_digest(str(candidate), configured_password)
