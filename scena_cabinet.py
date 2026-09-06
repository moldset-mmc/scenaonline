"""PRO membership and cabinet conversation rules for SCENA Pilot V1.4."""

from __future__ import annotations

import math
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


CHISINAU = ZoneInfo("Europe/Chisinau")
OWNER_KEY = "master"
TRIAL_DAYS = 60


class CabinetValidationError(ValueError):
    """Raised when a cabinet action violates an owner-visible rule."""


def _now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(CHISINAU)
    if value.tzinfo is None:
        return value.replace(tzinfo=CHISINAU)
    return value.astimezone(CHISINAU)


def _connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(db_path), timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_cabinet_features(
    connection: sqlite3.Connection, *, now: datetime | None = None
) -> None:
    """Create V1.4 tables and seed the approved pilot trial exactly once."""

    current = _now(now)
    timestamp = current.isoformat(timespec="seconds")
    expires_at = (current + timedelta(days=TRIAL_DAYS)).isoformat(timespec="seconds")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pro_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_key TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
            source TEXT NOT NULL DEFAULT 'cabinet',
            created_at TEXT NOT NULL,
            decided_at TEXT NOT NULL DEFAULT '',
            decision_note TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_pro_applications_one_pending
        ON pro_applications(owner_key)
        WHERE status = 'pending'
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pro_subscriptions (
            owner_key TEXT PRIMARY KEY,
            tier TEXT NOT NULL CHECK (tier IN ('FREE', 'PRO')),
            status TEXT NOT NULL CHECK (status IN ('trial', 'active', 'expired')),
            started_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            source_application_id INTEGER,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(source_application_id) REFERENCES pro_applications(id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS support_threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_key TEXT NOT NULL,
            subject TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'closed')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER NOT NULL,
            sender TEXT NOT NULL CHECK (sender IN ('user', 'assistant', 'admin', 'system')),
            channel TEXT NOT NULL CHECK (channel IN ('support', 'assistant', 'system')),
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            external_update_id TEXT UNIQUE,
            FOREIGN KEY(thread_id) REFERENCES support_threads(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS integration_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            support_message_id INTEGER NOT NULL UNIQUE,
            channel TEXT NOT NULL CHECK (channel IN ('telegram')),
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'sent', 'failed')),
            attempts INTEGER NOT NULL DEFAULT 0,
            external_message_id TEXT,
            last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            sent_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(support_message_id) REFERENCES support_messages(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS integration_outbox_claims (
            outbox_id INTEGER PRIMARY KEY,
            claim_token TEXT NOT NULL UNIQUE,
            claimed_at_epoch REAL NOT NULL,
            FOREIGN KEY(outbox_id) REFERENCES integration_outbox(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS integration_state (
            channel TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY(channel, key)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS support_reply_preferences (
            support_message_id INTEGER PRIMARY KEY,
            reply_channel TEXT NOT NULL DEFAULT 'scena'
                CHECK (reply_channel IN ('scena', 'telegram', 'sms', 'email')),
            contact TEXT NOT NULL DEFAULT '',
            locale TEXT NOT NULL DEFAULT 'ru' CHECK (locale IN ('ru','ro','en')),
            request_key TEXT UNIQUE,
            FOREIGN KEY(support_message_id) REFERENCES support_messages(id) ON DELETE CASCADE
        )
        """
    )

    existing = connection.execute(
        "SELECT owner_key FROM pro_subscriptions WHERE owner_key = ?", (OWNER_KEY,)
    ).fetchone()
    if existing:
        return

    application = connection.execute(
        """
        INSERT INTO pro_applications (
            owner_key, message, status, source, created_at, decided_at,
            decision_note
        ) VALUES (?, ?, 'approved', 'pilot_preapproval', ?, ?, ?)
        """,
        (
            OWNER_KEY,
            "Льготный PRO Trial пилотного проекта SCENA",
            timestamp,
            timestamp,
            "Пилотный доступ одобрен автоматически.",
        ),
    )
    connection.execute(
        """
        INSERT INTO pro_subscriptions (
            owner_key, tier, status, started_at, expires_at,
            source_application_id, updated_at
        ) VALUES (?, 'PRO', 'trial', ?, ?, ?, ?)
        """,
        (OWNER_KEY, timestamp, expires_at, int(application.lastrowid), timestamp),
    )


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def get_pro_status(
    db_path: str | Path, *, now: datetime | None = None
) -> dict[str, Any]:
    current = _now(now)
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM pro_subscriptions WHERE owner_key = ?", (OWNER_KEY,)
        ).fetchone()
        if row is None:
            raise RuntimeError("PRO subscription state is not initialized.")

        expires_at = datetime.fromisoformat(row["expires_at"]).astimezone(CHISINAU)
        status = str(row["status"])
        if current >= expires_at and status != "expired":
            status = "expired"
            connection.execute(
                """
                UPDATE pro_subscriptions
                SET status = 'expired', tier = 'FREE', updated_at = ?
                WHERE owner_key = ?
                """,
                (current.isoformat(timespec="seconds"), OWNER_KEY),
            )
        seconds_remaining = max(0.0, (expires_at - current).total_seconds())
        days_remaining = int(math.ceil(seconds_remaining / 86_400))
        return {
            "tier": "PRO" if status in {"trial", "active"} else "FREE",
            "status": status,
            "label": "PRO Trial" if status == "trial" else ("PRO" if status == "active" else "FREE"),
            "started_at": row["started_at"],
            "expires_at": row["expires_at"],
            "days_remaining": days_remaining,
            "is_active": status in {"trial", "active"},
        }


def list_pro_applications(db_path: str | Path) -> list[dict[str, Any]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM pro_applications
            WHERE owner_key = ?
            ORDER BY created_at DESC, id DESC
            """,
            (OWNER_KEY,),
        ).fetchall()
    return [_row_dict(row) for row in rows]


def submit_pro_application(
    db_path: str | Path,
    message: str = "",
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    if get_pro_status(db_path, now=current)["is_active"]:
        raise CabinetValidationError("PRO уже активен в вашем кабинете.")
    request_text = str(message or "").strip()
    if len(request_text) > 2_000:
        raise CabinetValidationError("Текст заявки должен быть короче 2000 символов.")

    with _connect(db_path) as connection:
        pending = connection.execute(
            """
            SELECT * FROM pro_applications
            WHERE owner_key = ? AND status = 'pending'
            """,
            (OWNER_KEY,),
        ).fetchone()
        if pending:
            raise CabinetValidationError("Заявка на PRO уже отправлена и ожидает решения.")
        timestamp = current.isoformat(timespec="seconds")
        try:
            cursor = connection.execute(
                """
                INSERT INTO pro_applications (
                    owner_key, message, status, source, created_at
                ) VALUES (?, ?, 'pending', 'cabinet', ?)
                """,
                (OWNER_KEY, request_text, timestamp),
            )
        except sqlite3.IntegrityError as exc:
            raise CabinetValidationError(
                "Заявка на PRO уже отправлена и ожидает решения."
            ) from exc
        row = connection.execute(
            "SELECT * FROM pro_applications WHERE id = ?", (int(cursor.lastrowid),)
        ).fetchone()
    return _row_dict(row)


def decide_pro_application(
    db_path: str | Path,
    application_id: int,
    *,
    approved: bool,
    note: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record the platform decision; approval activates a fresh 60-day trial."""

    current = _now(now)
    timestamp = current.isoformat(timespec="seconds")
    decision = "approved" if approved else "rejected"
    with _connect(db_path) as connection:
        application = connection.execute(
            """
            SELECT * FROM pro_applications
            WHERE id = ? AND owner_key = ?
            """,
            (int(application_id), OWNER_KEY),
        ).fetchone()
        if application is None:
            raise CabinetValidationError("Заявка на PRO не найдена.")
        if application["status"] != "pending":
            raise CabinetValidationError("Решение по этой заявке уже принято.")
        connection.execute(
            """
            UPDATE pro_applications
            SET status = ?, decided_at = ?, decision_note = ?
            WHERE id = ?
            """,
            (decision, timestamp, str(note or "").strip(), int(application_id)),
        )
        if approved:
            expires_at = (current + timedelta(days=TRIAL_DAYS)).isoformat(
                timespec="seconds"
            )
            connection.execute(
                """
                INSERT INTO pro_subscriptions (
                    owner_key, tier, status, started_at, expires_at,
                    source_application_id, updated_at
                ) VALUES (?, 'PRO', 'trial', ?, ?, ?, ?)
                ON CONFLICT(owner_key) DO UPDATE SET
                    tier = excluded.tier,
                    status = excluded.status,
                    started_at = excluded.started_at,
                    expires_at = excluded.expires_at,
                    source_application_id = excluded.source_application_id,
                    updated_at = excluded.updated_at
                """,
                (OWNER_KEY, timestamp, expires_at, int(application_id), timestamp),
            )
        decided = connection.execute(
            "SELECT * FROM pro_applications WHERE id = ?", (int(application_id),)
        ).fetchone()
    return _row_dict(decided)


def _support_message_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = _row_dict(row)
    result["delivery_status"] = result.get("delivery_status") or "not_applicable"
    return result


def _get_or_create_support_thread(
    connection: sqlite3.Connection, timestamp: str
) -> int:
    row = connection.execute(
        """
        SELECT id FROM support_threads
        WHERE owner_key = ? AND status = 'open'
        ORDER BY id DESC LIMIT 1
        """,
        (OWNER_KEY,),
    ).fetchone()
    if row:
        return int(row["id"])
    cursor = connection.execute(
        """
        INSERT INTO support_threads (
            owner_key, subject, status, created_at, updated_at
        ) VALUES (?, ?, 'open', ?, ?)
        """,
        (OWNER_KEY, "Помощь и SCENA Ассистент", timestamp, timestamp),
    )
    return int(cursor.lastrowid)


def submit_support_message(
    db_path: str | Path,
    body: str,
    *,
    reply_channel: str = "scena",
    contact: str = "",
    locale: str = "ru",
    request_key: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    text = str(body or "").strip()
    if not text:
        raise CabinetValidationError("Напишите вопрос или опишите проблему.")
    if len(text) > 4_000:
        raise CabinetValidationError("Сообщение должно быть короче 4000 символов.")
    reply_channel, contact = validate_reply_preference(reply_channel, contact)
    locale = locale if locale in {"ru", "ro", "en"} else "ru"
    if request_key is not None and not re.fullmatch(r"[a-zA-Z0-9_-]{16,80}", request_key):
        raise CabinetValidationError("Обновите страницу и отправьте сообщение ещё раз.")
    timestamp = _now(now).isoformat(timespec="seconds")
    with _connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if request_key:
            previous = connection.execute(
                """SELECT m.*, o.status AS delivery_status, o.external_message_id,
                          p.reply_channel, p.contact, p.locale
                   FROM support_reply_preferences p
                   JOIN support_messages m ON m.id = p.support_message_id
                   JOIN support_threads t ON t.id = m.thread_id
                   LEFT JOIN integration_outbox o ON o.support_message_id = m.id
                   WHERE p.request_key = ? AND t.owner_key = ?""",
                (request_key, OWNER_KEY),
            ).fetchone()
            if previous is not None:
                if (previous["body"], previous["reply_channel"], previous["contact"]) != (text, reply_channel, contact):
                    raise CabinetValidationError("Это обращение уже отправлялось. Обновите страницу для нового сообщения.")
                return _support_message_dict(previous)
        thread_id = _get_or_create_support_thread(connection, timestamp)
        cursor = connection.execute(
            """
            INSERT INTO support_messages (
                thread_id, sender, channel, body, created_at
            ) VALUES (?, 'user', 'support', ?, ?)
            """,
            (thread_id, text, timestamp),
        )
        message_id = int(cursor.lastrowid)
        connection.execute(
            """INSERT INTO support_reply_preferences
                (support_message_id, reply_channel, contact, locale, request_key)
                VALUES (?, ?, ?, ?, ?)""",
            (message_id, reply_channel, contact, locale, request_key),
        )
        connection.execute(
            """
            INSERT INTO integration_outbox (
                support_message_id, channel, status, created_at
            ) VALUES (?, 'telegram', 'queued', ?)
            """,
            (message_id, timestamp),
        )
        connection.execute(
            "UPDATE support_threads SET updated_at = ? WHERE id = ?",
            (timestamp, thread_id),
        )
        row = connection.execute(
            """
            SELECT m.*, o.status AS delivery_status, o.external_message_id
            FROM support_messages AS m
            LEFT JOIN integration_outbox AS o ON o.support_message_id = m.id
            WHERE m.id = ?
            """,
            (message_id,),
        ).fetchone()
    return _support_message_dict(row)


def validate_reply_preference(channel: str, contact: str) -> tuple[str, str]:
    channel = str(channel or "").strip().lower()
    contact = str(contact or "").strip()
    if channel not in {"scena", "telegram", "sms", "email"}:
        raise CabinetValidationError("Выберите, где получить ответ.")
    if channel == "scena":
        return channel, ""
    if channel == "telegram":
        contact = re.sub(r"^https://t\.me/", "@", contact)
        if not re.fullmatch(r"@[A-Za-z][A-Za-z0-9_]{4,31}", contact):
            raise CabinetValidationError("Укажите Telegram в формате @username.")
    elif channel == "sms":
        contact = re.sub(r"[\s()-]", "", contact)
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", contact):
            raise CabinetValidationError("Укажите телефон с кодом страны, например +37360123456.")
    elif len(contact) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", contact):
        raise CabinetValidationError("Укажите корректный email.")
    return channel, contact


def list_support_messages(db_path: str | Path) -> list[dict[str, Any]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT m.*, o.status AS delivery_status, o.external_message_id,
                   COALESCE(p.reply_channel, 'scena') AS reply_channel,
                   COALESCE(p.contact, '') AS reply_contact
            FROM support_messages AS m
            JOIN support_threads AS t ON t.id = m.thread_id
            LEFT JOIN integration_outbox AS o ON o.support_message_id = m.id
            LEFT JOIN support_reply_preferences p ON p.support_message_id = m.id
            WHERE t.owner_key = ?
            ORDER BY m.created_at, m.id
            """,
            (OWNER_KEY,),
        ).fetchall()
    return [_support_message_dict(row) for row in rows]


def _claim_outbox_item(
    db_path: str | Path, outbox_id: int, *, now: datetime
) -> str | None:
    """Atomically claim one delivery without holding SQLite open during I/O."""

    claim_token = uuid.uuid4().hex
    stale_before = now.timestamp() - 300
    with _connect(db_path) as connection:
        connection.execute(
            "DELETE FROM integration_outbox_claims WHERE claimed_at_epoch < ?",
            (stale_before,),
        )
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO integration_outbox_claims (
                outbox_id, claim_token, claimed_at_epoch
            )
            SELECT id, ?, ? FROM integration_outbox
            WHERE id = ? AND status IN ('queued', 'failed')
            """,
            (claim_token, now.timestamp(), int(outbox_id)),
        )
    return claim_token if cursor.rowcount == 1 else None


def _finish_outbox_item(
    db_path: str | Path,
    outbox_id: int,
    claim_token: str,
    *,
    sent: bool,
    external_message_id: str = "",
    timestamp: str,
) -> bool:
    """Complete only the worker's own claim, leaving stale workers harmless."""

    with _connect(db_path) as connection:
        claim = connection.execute(
            """
            SELECT outbox_id FROM integration_outbox_claims
            WHERE outbox_id = ? AND claim_token = ?
            """,
            (int(outbox_id), claim_token),
        ).fetchone()
        if claim is None:
            return False
        if sent:
            connection.execute(
                """
                UPDATE integration_outbox
                SET status = 'sent', attempts = attempts + 1,
                    external_message_id = ?, sent_at = ?, last_error = ''
                WHERE id = ?
                """,
                (external_message_id, timestamp, int(outbox_id)),
            )
        else:
            connection.execute(
                """
                UPDATE integration_outbox
                SET status = 'failed', attempts = attempts + 1,
                    external_message_id = NULL, sent_at = '', last_error = ?
                WHERE id = ?
                """,
                ("Внешняя отправка временно недоступна.", int(outbox_id)),
            )
        connection.execute(
            """
            DELETE FROM integration_outbox_claims
            WHERE outbox_id = ? AND claim_token = ?
            """,
            (int(outbox_id), claim_token),
        )
    return True


def _safe_error_code(error: Exception) -> str:
    code = str(getattr(error, "code", "external_error")).strip().lower()
    return code if re.fullmatch(r"[a-z0-9_]{1,64}", code) else "external_error"


def _adapter_fingerprint(adapter: Any) -> str:
    fingerprint = str(
        getattr(adapter, "configuration_fingerprint", "") or ""
    ).strip().lower()
    return fingerprint if re.fullmatch(r"[a-f0-9]{64}", fingerprint) else ""


def _record_integration_result(
    db_path: str | Path,
    channel: str,
    *,
    now: datetime,
    error: Exception | None = None,
    fingerprint: str = "",
) -> None:
    timestamp = now.isoformat(timespec="microseconds")
    values = {
        "last_check_status": "failed" if error else "success",
        "last_check_at": timestamp,
        "last_error_code": _safe_error_code(error) if error else "",
        "configuration_fingerprint": fingerprint,
    }
    with _connect(db_path) as connection:
        for key, value in values.items():
            connection.execute(
                """
                INSERT INTO integration_state(channel, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(channel, key) DO UPDATE SET value = excluded.value
                """,
                (channel, key, value),
            )


def get_integration_health(db_path: str | Path, channel: str) -> dict[str, str]:
    if channel not in {"ai", "telegram"}:
        raise CabinetValidationError("Неизвестный внешний канал.")
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT key, value FROM integration_state WHERE channel = ?",
            (channel,),
        ).fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def dispatch_support_notifications(
    db_path: str | Path,
    telegram: Any,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Send queued support messages through the injected Telegram adapter."""

    current = _now(now)
    timestamp = current.isoformat(timespec="seconds")
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT o.id, o.support_message_id, m.thread_id, m.body,
                   COALESCE(p.reply_channel, 'scena') AS reply_channel,
                   COALESCE(p.contact, '') AS reply_contact,
                   COALESCE(p.locale, 'ru') AS locale
            FROM integration_outbox AS o
            JOIN support_messages AS m ON m.id = o.support_message_id
            JOIN support_threads AS t ON t.id = m.thread_id
            LEFT JOIN support_reply_preferences p ON p.support_message_id = m.id
            WHERE t.owner_key = ? AND o.channel = 'telegram'
              AND o.status IN ('queued', 'failed')
            ORDER BY o.id
            """,
            (OWNER_KEY,),
        ).fetchall()
    if not bool(getattr(telegram, "configured", False)):
        return {
            "sent": 0,
            "failed": 0,
            "waiting_configuration": len(rows),
        }

    sent = 0
    failed = 0
    last_error: Exception | None = None
    for row in rows:
        claim_token = _claim_outbox_item(
            db_path, int(row["id"]), now=current
        )
        if claim_token is None:
            continue
        try:
            preference = {
                "scena": "Ответить в SCENA: используйте Ответить / Reply на это сообщение.",
                "telegram": f"Предпочитает ответ в Telegram: {row['reply_contact']} (напишите лично).",
                "sms": f"Предпочитает SMS: {row['reply_contact']} (ответ отправляется оператором).",
                "email": f"Предпочитает email: {row['reply_contact']} (ответ отправляется оператором).",
            }[row["reply_channel"]]
            body = f"{row['body']}\n\n—\n{preference}\nЯзык ответа: {row['locale'].upper()}"
            external_id = str(
                telegram.send_support_message(
                    thread_id=int(row["thread_id"]), body=body
                )
            ).strip()
            if not external_id:
                raise RuntimeError("Telegram не вернул идентификатор сообщения.")
        except Exception as exc:
            last_error = exc
            if _finish_outbox_item(
                db_path,
                int(row["id"]),
                claim_token,
                sent=False,
                timestamp=timestamp,
            ):
                failed += 1
            continue
        if _finish_outbox_item(
            db_path,
            int(row["id"]),
            claim_token,
            sent=True,
            external_message_id=external_id,
            timestamp=timestamp,
        ):
            sent += 1
    if last_error is not None:
        _record_integration_result(
            db_path,
            "telegram",
            now=current,
            error=last_error,
            fingerprint=_adapter_fingerprint(telegram),
        )
    elif sent:
        _record_integration_result(
            db_path,
            "telegram",
            now=current,
            fingerprint=_adapter_fingerprint(telegram),
        )
    return {"sent": sent, "failed": failed, "waiting_configuration": 0}


def sync_telegram_replies(
    db_path: str | Path,
    telegram: Any,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Import administrator replies that reference a sent support message."""

    if not bool(getattr(telegram, "configured", False)):
        return {"received": 0, "ignored": 0, "waiting_configuration": 1}
    current = _now(now)
    timestamp = current.isoformat(timespec="seconds")
    with _connect(db_path) as connection:
        state = connection.execute(
            """
            SELECT value FROM integration_state
            WHERE channel = 'telegram' AND key = 'update_offset'
            """
        ).fetchone()
        offset = int(state["value"]) if state else 0

    try:
        poll_result = telegram.poll_admin_replies(offset=offset)
    except Exception as exc:
        _record_integration_result(
            db_path,
            "telegram",
            now=current,
            error=exc,
            fingerprint=_adapter_fingerprint(telegram),
        )
        raise
    if isinstance(poll_result, Mapping):
        updates = list(poll_result.get("replies", []) or [])
        try:
            reported_next_offset = int(poll_result.get("next_offset", offset))
        except (TypeError, ValueError):
            reported_next_offset = offset
    else:
        updates = list(poll_result or [])
        reported_next_offset = offset

    with _connect(db_path) as connection:
        received = 0
        ignored = 0
        next_offset = max(offset, reported_next_offset)
        for update in updates:
            try:
                update_id = int(update["update_id"])
            except (KeyError, TypeError, ValueError):
                ignored += 1
                continue
            next_offset = max(next_offset, update_id + 1)
            text = str(update.get("text", "")).strip()
            reply_to = str(update.get("reply_to_message_id", "")).strip()
            thread_id = update.get("thread_id")
            if reply_to:
                linked = connection.execute(
                    """
                    SELECT m.thread_id
                    FROM integration_outbox AS o
                    JOIN support_messages AS m ON m.id = o.support_message_id
                    JOIN support_threads AS t ON t.id = m.thread_id
                    WHERE o.external_message_id = ? AND t.owner_key = ?
                    """,
                    (reply_to, OWNER_KEY),
                ).fetchone()
                thread_id = int(linked["thread_id"]) if linked else None
            if not text or thread_id is None:
                ignored += 1
                continue
            owned_thread = connection.execute(
                "SELECT id FROM support_threads WHERE id = ? AND owner_key = ?",
                (int(thread_id), OWNER_KEY),
            ).fetchone()
            if owned_thread is None:
                ignored += 1
                continue
            external_update_id = f"telegram:{update_id}"
            try:
                connection.execute(
                    """
                    INSERT INTO support_messages (
                        thread_id, sender, channel, body, created_at,
                        external_update_id
                    ) VALUES (?, 'admin', 'support', ?, ?, ?)
                    """,
                    (int(thread_id), text, timestamp, external_update_id),
                )
            except sqlite3.IntegrityError:
                continue
            connection.execute(
                "UPDATE support_threads SET updated_at = ? WHERE id = ?",
                (timestamp, int(thread_id)),
            )
            received += 1
        if next_offset != offset:
            connection.execute(
                """
                INSERT INTO integration_state(channel, key, value)
                VALUES ('telegram', 'update_offset', ?)
                ON CONFLICT(channel, key) DO UPDATE SET value = excluded.value
                """,
                (str(next_offset),),
            )
    _record_integration_result(
        db_path,
        "telegram",
        now=current,
        fingerprint=_adapter_fingerprint(telegram),
    )
    return {"received": received, "ignored": ignored, "waiting_configuration": 0}


def _assistant_context(db_path: str | Path, now: datetime, locale: str = "ru") -> dict[str, Any]:
    """Bounded current-owner content and aggregates; never customer PII or secrets."""

    allowed_settings = {
        "master_name",
        "location",
        "bio",
        "beauty_title",
        "beauty_desc",
        "model_title",
        "model_desc",
        "scene_hero_image",
        "professional_hero_image",
        "profile_published",
        "professional_published",
        "model_published",
        "bio_translation_approved",
        "professional_translation_approved",
        "model_translation_approved",
    }
    # Explicit allowlist: no URLs, API keys, phone numbers, private support, or arbitrary settings.
    content_bases = ("master_name", "location", "bio", "beauty_title", "beauty_desc",
                     "model_title", "model_desc", "model_intro_title", "model_intro_text",
                     "model_intro_details")
    allowed_settings.update(f"{base}_{lang}" for base in content_bases for lang in ("ru", "ro", "en"))
    allowed_settings.update(f"model_slide_{index}_manifest_{lang}" for index in range(1, 6) for lang in ("ru", "ro", "en"))
    membership = get_pro_status(db_path, now=now)
    with _connect(db_path) as connection:
        settings = {
            row["key"]: str(row["value"])[:2400]
            for row in connection.execute(
                "SELECT key, value FROM profile_settings"
            )
            if row["key"] in allowed_settings
        }
        service_counts = {
            row["category"]: int(row["amount"])
            for row in connection.execute(
                """
                SELECT category, COUNT(*) AS amount
                FROM services
                WHERE active = 1 AND archived = 0
                GROUP BY category
                """
            )
        }
        post_count = int(connection.execute(
            "SELECT COUNT(*) FROM posts WHERE active = 1"
        ).fetchone()[0])
        services = [dict(row) for row in connection.execute(
            """SELECT id, category, kind, name, name_ro, description_ru, description_ro,
                      price, duration, active, archived
               FROM services ORDER BY active DESC, archived ASC, id LIMIT 40"""
        )]
        service_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(services)")}
        if {"name_en", "description_en"}.issubset(service_columns):
            english = {row["id"]: row for row in connection.execute("SELECT id, name_en, description_en FROM services ORDER BY id LIMIT 400")}
            for service in services:
                if service["id"] in english:
                    service.update({key: english[service["id"]][key] for key in ("name_en", "description_en")})
        for service in services:
            for key, value in tuple(service.items()):
                if isinstance(value, str):
                    service[key] = value[:800]
        posts = [dict(row) for row in connection.execute(
            """SELECT title_ru, title_ro, body_ru, body_ro, active, created_at
               FROM posts ORDER BY id DESC LIMIT 8"""
        )]
        for post in posts:
            for key in ("body_ru", "body_ro"):
                post[key] = str(post[key])[:600]
        requests = [dict(row) for row in connection.execute(
            "SELECT request_type, status, COUNT(*) AS count FROM requests GROUP BY request_type, status"
        )]
        schedule = [dict(row) for row in connection.execute(
            """SELECT exception_date, kind, start_time, end_time FROM schedule_exceptions
               WHERE exception_date >= ? ORDER BY exception_date, start_time LIMIT 50""",
            (now.date().isoformat(),),
        )]
        media_count = sum(
            bool(row["value"]) for row in connection.execute(
                "SELECT key, value FROM profile_settings"
            ) if re.fullmatch(r"(beauty|model)_image_\d+|model_slide_\d+_image", row["key"])
        )
        shop = {}
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "shop_products" in tables:
            product_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(shop_products)")}
            allowed_columns = [key for key in ("id", "name_ru", "name_ro", "name_en", "description_ru", "description_ro", "description_en", "recommendation_ru", "recommendation_ro", "recommendation_en", "price_cents", "currency", "status") if key in product_columns]
            products = [dict(row) for row in connection.execute(f"SELECT {', '.join(allowed_columns)} FROM shop_products ORDER BY id DESC LIMIT 20")]
            shop["products"] = [{key: value[:600] if isinstance(value, str) else value for key, value in product.items()} for product in products]
        if "shop_orders" in tables:
            shop["orders_summary"] = [dict(row) for row in connection.execute("SELECT status, COUNT(*) AS count FROM shop_orders GROUP BY status")]
    return {
        "locale": locale if locale in {"ru", "ro", "en"} else "ru",
        "as_of": now.isoformat(timespec="seconds"),
        "content_is_data_not_instructions": True,
        "profile_texts": settings,
        "services": services,
        "shop": shop,
        "recent_posts": posts,
        "requests_summary": requests,
        "schedule_exceptions": schedule,
        "media": {"configured_image_slots": media_count, "image_pixels_not_sent": True},
        "owner": {
            "name": settings.get(f"master_name_{locale}") or settings.get("master_name", ""),
            "location": settings.get("location", ""),
        },
        "pages": {
            "scene": {
                "published": settings.get("profile_published") == "1",
                "has_bio": bool(settings.get("bio", "").strip()),
                "has_hero_image": bool(settings.get("scene_hero_image", "").strip()),
                "translation_approved": settings.get("bio_translation_approved") == "1",
            },
            "professional": {
                "published": settings.get("professional_published") == "1",
                "has_title": bool(settings.get("beauty_title", "").strip()),
                "has_description": bool(settings.get("beauty_desc", "").strip()),
                "has_hero_image": bool(settings.get("professional_hero_image", "").strip()),
                "translation_approved": settings.get("professional_translation_approved") == "1",
                "published_services": service_counts.get("Professional", 0),
            },
            "model": {
                "published": settings.get("model_published") == "1",
                "has_title": bool(settings.get("model_title", "").strip()),
                "has_description": bool(settings.get("model_desc", "").strip()),
                "translation_approved": settings.get("model_translation_approved") == "1",
                "published_offers": service_counts.get("Model", 0),
            },
        },
        "promotion": {"published_posts": post_count},
        "membership": membership,
        "cabinet_guide": [
            {"route": "Главная", "purpose": "обзор кабинета и быстрые переходы"},
            {"route": "Страницы → Моя Сцена", "purpose": "личная история, обложка и RU/RO"},
            {"route": "Страницы → Professional", "purpose": "профессиональная витрина"},
            {"route": "Страницы → Model", "purpose": "кадры и тексты Model-лендинга"},
            {"route": "Работа → Услуги", "purpose": "группы, услуги, цены и архив"},
            {"route": "Работа → График", "purpose": "дни и интервалы записи"},
            {"route": "Работа → Заявки", "purpose": "клиентские обращения и статусы"},
            {"route": "Продвижение → Публикации", "purpose": "посты SCENA"},
            {"route": "Продвижение → QR-коды", "purpose": "ссылки и QR страниц"},
            {"route": "Помощь → SCENA Ассистент", "purpose": "подсказки по кабинету без изменения данных"},
            {"route": "Помощь → Команда SCENA", "purpose": "сохранённый запрос администратору"},
            {"route": "PRO", "purpose": "возможности, срок доступа и продление"},
            {"route": "Страницы → Market", "purpose": "личный магазин и заказы"},
            {"route": "Продвижение → Промпты", "purpose": "задания своему AI и история версий"},
            {"route": "Настройки → SMS", "purpose": "локальная очередь уведомлений"},
            {"route": "Настройки → Резервная копия", "purpose": "скачивание копии SQLite"},
            {"route": "Настройки → Подключения", "purpose": "настройки AI и Telegram владельцем"},
        ],
    }


def _save_conversation_message(
    db_path: str | Path,
    *,
    thread_id: int,
    sender: str,
    channel: str,
    body: str,
    timestamp: str,
) -> dict[str, Any]:
    with _connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO support_messages (
                thread_id, sender, channel, body, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (thread_id, sender, channel, body, timestamp),
        )
        connection.execute(
            "UPDATE support_threads SET updated_at = ? WHERE id = ?",
            (timestamp, thread_id),
        )
        row = connection.execute(
            """
            SELECT m.*, NULL AS delivery_status, NULL AS external_message_id
            FROM support_messages AS m WHERE m.id = ?
            """,
            (int(cursor.lastrowid),),
        ).fetchone()
    return _support_message_dict(row)


def ask_scena_assistant(
    db_path: str | Path,
    question: str,
    assistant: Any,
    *,
    locale: str = "ru",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist a question and, when configured, its read-only AI answer."""

    text = str(question or "").strip()
    if not text:
        raise CabinetValidationError("Напишите вопрос SCENA Ассистенту.")
    if len(text) > 4_000:
        raise CabinetValidationError("Вопрос должен быть короче 4000 символов.")
    current = _now(now)
    timestamp = current.isoformat(timespec="seconds")
    with _connect(db_path) as connection:
        thread_id = _get_or_create_support_thread(connection, timestamp)
        history_rows = connection.execute(
            """
            SELECT sender, body FROM support_messages
            WHERE thread_id = ? AND channel = 'assistant'
              AND sender IN ('user', 'assistant')
            ORDER BY created_at DESC, id DESC LIMIT 12
            """,
            (thread_id,),
        ).fetchall()
    history = [
        {"role": row["sender"], "content": row["body"]}
        for row in reversed(history_rows)
    ]
    user_message = _save_conversation_message(
        db_path,
        thread_id=thread_id,
        sender="user",
        channel="assistant",
        body=text,
        timestamp=timestamp,
    )

    if not bool(getattr(assistant, "configured", False)):
        from scena_help_ui import local_guide_answer
        system_message = _save_conversation_message(
            db_path,
            thread_id=thread_id,
            sender="system",
            channel="system",
            body=local_guide_answer(text, _assistant_context(db_path, current, locale), locale),
            timestamp=timestamp,
        )
        return {
            "status": "guided",
            "user_message": user_message,
            "assistant_message": system_message,
        }

    try:
        answer = str(
            assistant.answer(
                question=text,
                context=_assistant_context(db_path, current, locale),
                history=history,
            )
        ).strip()
        if not answer:
            raise RuntimeError("AI-подключение вернуло пустой ответ.")
    except Exception as exc:
        _record_integration_result(
            db_path,
            "ai",
            now=current,
            error=exc,
            fingerprint=_adapter_fingerprint(assistant),
        )
        system_message = _save_conversation_message(
            db_path,
            thread_id=thread_id,
            sender="system",
            channel="system",
            body={
                "ru": "Ответ не получен. Вопрос остался в переписке. Попробуйте отправить его ещё раз или напишите команде SCENA.",
                "ro": "Răspunsul nu a fost primit. Întrebarea rămâne în conversație. Încercați din nou sau scrieți echipei SCENA.",
                "en": "No answer was received. Your question remains in this conversation. Try again or contact the SCENA team.",
            }.get(locale, "Ответ не получен. Вопрос остался в переписке."),
            timestamp=timestamp,
        )
        return {
            "status": "failed",
            "user_message": user_message,
            "assistant_message": system_message,
        }

    _record_integration_result(
        db_path,
        "ai",
        now=current,
        fingerprint=_adapter_fingerprint(assistant),
    )
    assistant_message = _save_conversation_message(
        db_path,
        thread_id=thread_id,
        sender="assistant",
        channel="assistant",
        body=answer[:8_000],
        timestamp=timestamp,
    )
    return {
        "status": "answered",
        "user_message": user_message,
        "assistant_message": assistant_message,
    }
