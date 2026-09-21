"""Customer booking email delivery through Resend.

The sender is derived only from the configured canonical SCENA hostname:
mbstudio.scena.life -> mbstudio@scena.life. Request Host headers never choose
the sender address.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAIL_ROOT_DOMAIN = "scena.life"
RESEND_ENDPOINT = "https://api.resend.com/emails"
EVENTS = ("received", "confirmed")


def sender_from_public_base(public_base_url: str) -> str:
    """Return <tenant>@scena.life for one safe tenant label, otherwise empty."""
    try:
        parsed = urlsplit(str(public_base_url or "").strip())
        host = (parsed.hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return ""
    suffix = "." + MAIL_ROOT_DOMAIN
    if parsed.scheme != "https" or not host.endswith(suffix):
        return ""
    tenant = host[:-len(suffix)]
    if "." in tenant or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", tenant):
        return ""
    return f"{tenant}@{MAIL_ROOT_DOMAIN}"


def _price(value, currency: str, locale: str) -> str:
    amount = float(value or 0)
    if amount <= 0:
        return {
            "ru": "Цена по договорённости",
            "ro": "Preț la înțelegere",
            "en": "Price by agreement",
        }[locale]
    rendered = f"{amount:,.0f}" if amount.is_integer() else f"{amount:,.2f}"
    return rendered.replace(",", " ") + " " + (currency or "MDL")


def _snapshot(db, request_id: int):
    from scena_core import _connect
    from scena_i18n import content_text, normalize_locale

    with _connect(db) as con:
        row = con.execute(
            "SELECT * FROM requests WHERE id=? AND request_type='service_request'",
            (int(request_id),),
        ).fetchone()
        if not row:
            return None
        request_row = dict(row)
        service_row = con.execute(
            "SELECT * FROM services WHERE id=?",
            (int(request_row["service_id"]),),
        ).fetchone()
        settings = {
            item["key"]: item["value"]
            for item in con.execute("SELECT key,value FROM profile_settings")
        }

    locale = normalize_locale(str(request_row.get("locale", "ro")), fallback="ro")
    service = dict(service_row) if service_row else {}
    service_name = (
        content_text(service, "name", locale)
        if service
        else str(request_row.get("service", ""))
    )
    return {
        "request": request_row,
        "service": service,
        "settings": settings,
        "locale": locale,
        "service_name": service_name,
    }


def _payload(snapshot: dict, event: str = "received") -> dict:
    if event not in EVENTS:
        return {}
    row = snapshot["request"]
    service = snapshot["service"]
    settings = snapshot["settings"]
    locale = snapshot["locale"]
    sender = sender_from_public_base(settings.get("public_base_url", ""))
    if not sender:
        return {}

    try:
        when = date.fromisoformat(str(row["preferred_date"])).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        when = str(row.get("preferred_date", ""))

    translations = {
        "ru": {
            "received_subject": f"SCENA · Заявка №{row['id']} принята",
            "confirmed_subject": f"SCENA · Запись №{row['id']} подтверждена",
            "hello": f"Здравствуйте, {row['name']}!",
            "received": "Мы получили вашу заявку на запись.",
            "confirmed": "Ваша запись подтверждена.",
            "service": "Услуга",
            "date": "Дата и время",
            "duration": "Продолжительность",
            "price": "Стоимость",
            "minutes": "мин.",
            "received_next": "Мастер свяжется с вами и подтвердит запись.",
            "confirmed_next": "Ждём вас в выбранное время.",
        },
        "ro": {
            "received_subject": f"SCENA · Cererea #{row['id']} a fost primită",
            "confirmed_subject": f"SCENA · Programarea #{row['id']} este confirmată",
            "hello": f"Bună, {row['name']}!",
            "received": "Am primit cererea dvs. de programare.",
            "confirmed": "Programarea dvs. este confirmată.",
            "service": "Serviciu",
            "date": "Data și ora",
            "duration": "Durată",
            "price": "Preț",
            "minutes": "min.",
            "received_next": "Specialistul vă va contacta și va confirma programarea.",
            "confirmed_next": "Vă așteptăm la ora aleasă.",
        },
        "en": {
            "received_subject": f"SCENA · Request #{row['id']} received",
            "confirmed_subject": f"SCENA · Booking #{row['id']} confirmed",
            "hello": f"Hello, {row['name']}!",
            "received": "We received your booking request.",
            "confirmed": "Your booking is confirmed.",
            "service": "Service",
            "date": "Date and time",
            "duration": "Duration",
            "price": "Price",
            "minutes": "min",
            "received_next": "Your artist will contact you and confirm the appointment.",
            "confirmed_next": "We look forward to seeing you at the selected time.",
        },
    }
    text = translations[locale]
    duration = int(service.get("duration") or 0)
    price = _price(service.get("price", 0), settings.get("currency", "MDL"), locale)
    lines = [
        text["hello"],
        "",
        text[event],
        f"{text['service']}: {snapshot['service_name']}",
        f"{text['date']}: {when} · {row['preferred_time']}",
    ]
    if duration:
        lines.append(f"{text['duration']}: {duration} {text['minutes']}")
    lines.extend((f"{text['price']}: {price}", "", text[event + "_next"], "", "SCENA"))
    return {
        "from": sender,
        "to": [str(row["email"]).strip()],
        "subject": text[event + "_subject"],
        "text": "\n".join(lines),
    }


class ResendAdapter:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def send(self, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            RESEND_ENDPOINT,
            data=body,
            method="POST",
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "SCENA/1.0",
            },
        )
        with urlopen(request, timeout=8) as response:
            if not 200 <= int(response.status) < 300:
                raise RuntimeError("Resend delivery failed")
            return json.loads(response.read().decode("utf-8") or "{}")


def dispatch(db, *, request_id: int, event: str = "received", adapter=None) -> str:
    """Send a customer booking message after the booking/status is committed."""
    try:
        if event not in EVENTS:
            return "invalid_event"
        snapshot = _snapshot(db, request_id)
        if not snapshot:
            return "idle"
        row = snapshot["request"]
        if row.get("contact_channel") != "email" or not str(row.get("email", "")).strip():
            return "skipped"
        if event == "confirmed" and row.get("status") != "Подтверждена":
            return "invalid_status"
        payload = _payload(snapshot, event)
        if not payload:
            return "unconfigured"
        if adapter is None:
            api_key = os.environ.get("RESEND_API_KEY", "").strip()
            if not api_key:
                return "unconfigured"
            adapter = ResendAdapter(api_key)
        result = adapter.send(payload)
        return "sent" if isinstance(result, dict) else "failed"
    except Exception:
        # Booking/status is already committed. Email delivery must never roll it
        # back or expose provider credentials in a customer-facing error.
        return "failed"
