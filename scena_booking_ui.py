"""Presentation and three-step customer booking, backed by the existing scheduler."""
from __future__ import annotations

import calendar
import html
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

from scena_i18n import tr as _tr, content_text, localized_name, translate_literaltext

from scena_core import (
    CHISINAU, RequestValidationError, create_service_request,
    generate_available_slots, list_services,
)


MONTHS = {
    "ru": ("", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"),
    "en": ("", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
    "ro": ("", "Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie", "Iulie", "August", "Septembrie", "Octombrie", "Noiembrie", "Decembrie"),
}
WEEKDAYS = {"ru": ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"), "ro": ("Lu", "Ma", "Mi", "Jo", "Vi", "Sâ", "Du"), "en": ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")}
FULL_WEEKDAYS={"ru":("Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"),"ro":("Luni","Marți","Miercuri","Joi","Vineri","Sâmbătă","Duminică"),"en":("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")}


def _name(item: dict, locale: str) -> str:
    return content_text(item, "name", locale)


def _price(item: dict, settings: dict, locale: str) -> str:
    amount = float(item["price"])
    return f"{amount:,.0f} {settings.get('currency', 'MDL')}".replace(",", " ") if amount else _tr(locale, "Цена по договорённости", "Preț la înțelegere")


def _date_label(value: str, locale: str) -> str:
    day = date.fromisoformat(value)
    return f"{FULL_WEEKDAYS[locale][day.weekday()]}, {day:%d.%m.%Y}"


def _day(value: str, fallback: date) -> date:
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return fallback


def _choose_day(value: str) -> None:
    st.session_state["booking_date"] = value
    st.session_state["booking_month"] = value[:7] + "-01"
    st.session_state.pop("booking_time", None)


def _choose_time(value: str) -> None:
    st.session_state["booking_time"] = value


def _service_changed() -> None:
    st.session_state.pop("booking_time", None)
    st.session_state.pop("booking_confirmation", None)


def _move_month(value: str) -> None:
    st.session_state["booking_month"] = value


def _calendar(db_path: Path, service_id: int, locale: str, now: datetime, last_day: date) -> None:
    today = now.date()
    selected = _day(st.session_state.get("booking_date"), today)
    if not today <= selected <= last_day:
        selected = today
        _choose_day(selected.isoformat())
    st.session_state["booking_date"] = selected.isoformat()
    month = _day(st.session_state.get("booking_month"), selected).replace(day=1)
    month = max(today.replace(day=1), min(month, last_day.replace(day=1)))
    st.session_state["booking_month"] = month.isoformat()
    previous = (month - timedelta(days=1)).replace(day=1)
    following = (month + timedelta(days=32)).replace(day=1)
    with st.container(key="booking_calendar", border=True):
        with st.container(key="booking_month_header"):
            title, back, forward = st.columns([5, 1, 1], gap="small", vertical_alignment="center")
            title.markdown(f"**{MONTHS[locale][month.month]} {month.year}**")
            back.button("‹", key="booking_month_previous", help=_tr(locale, "Предыдущий месяц", "Luna precedentă"), disabled=previous < today.replace(day=1), on_click=_move_month, args=(previous.isoformat(),), width="stretch")
            forward.button("›", key="booking_month_next", help=_tr(locale, "Следующий месяц", "Luna următoare"), disabled=following > last_day.replace(day=1), on_click=_move_month, args=(following.isoformat(),), width="stretch")
        for column, heading in zip(st.columns(7, gap="small"), WEEKDAYS[locale]):
            column.markdown(f'<div class="scena-calendar-weekday">{heading}</div>', unsafe_allow_html=True)
        for week in calendar.Calendar(firstweekday=0).monthdatescalendar(month.year, month.month):
            for column, candidate in zip(st.columns(7, gap="small"), week):
                if candidate.month != month.month:
                    column.markdown('<div class="scena-calendar-blank" aria-hidden="true"></div>', unsafe_allow_html=True)
                    continue
                valid = today <= candidate <= last_day
                free = bool(generate_available_slots(db_path, service_id, candidate.isoformat(), now=now)) if valid else False
                label = str(candidate.day) + (" ·" if free and candidate != selected else "")
                availability = _tr(locale, "есть свободное время", "ore disponibile") if free else _tr(locale, "свободного времени нет", "nu sunt ore disponibile")
                column.button(label, key=f"booking_day_{candidate.isoformat()}", type="primary" if candidate == selected else "secondary", disabled=not valid, help=f"{_date_label(candidate.isoformat(), locale)} — {availability}", on_click=_choose_day, args=(candidate.isoformat(),), width="stretch")
        st.caption(_tr(locale, "Точка рядом с датой — есть свободное время.", "Un punct lângă dată indică ore disponibile."))


def _time_blocks(db_path: Path, service_id: int, locale: str, now: datetime, last_day: date) -> list[str]:
    selected = st.session_state["booking_date"]
    st.markdown(f'<h3 class="scena-booking-date">{html.escape(_date_label(selected, locale))}</h3>', unsafe_allow_html=True)
    slots = generate_available_slots(db_path, service_id, selected, now=now)
    if st.session_state.get("booking_time") not in slots:
        st.session_state.pop("booking_time", None)
    if not slots:
        st.info(_tr(locale, "В этот день нет свободного времени. Выберите другую дату или посмотрите ближайшую доступную.", "În această zi nu sunt ore disponibile. Alegeți altă dată sau vedeți următoarea dată disponibilă."))
        candidate = date.fromisoformat(selected) + timedelta(days=1)
        nearest = None
        while candidate <= last_day:
            if generate_available_slots(db_path, service_id, candidate.isoformat(), now=now):
                nearest = candidate.isoformat()
                break
            candidate += timedelta(days=1)
        if nearest:
            st.caption(_tr(locale, "Ближайшая доступная дата: ", "Următoarea dată disponibilă: ") + _date_label(nearest, locale))
            st.button(_tr(locale, "Перейти к ближайшей дате", "Alege următoarea dată"), key="booking_nearest_day", type="primary", on_click=_choose_day, args=(nearest,), width="stretch")
        else:
            st.caption(_tr(locale, "На более поздние даты свободного времени пока нет. Можно выбрать другой день в календаре.", "Nu sunt ore disponibile la date ulterioare. Puteți alege altă zi în calendar."))
        return []
    for period, title, is_morning in (
        ("morning", _tr(locale, "До обеда", "Înainte de prânz"), True),
        ("afternoon", _tr(locale, "После обеда", "După prânz"), False),
    ):
        with st.container(key=f"booking_{period}", border=True):
            period_slots = [slot for slot in slots if (int(slot[:2]) < 12) == is_morning]
            if not period_slots:
                st.caption(_tr(locale, "Свободного времени нет", "Nu sunt ore disponibile"))
            for offset in range(0, len(period_slots), 3):
                for column, slot in zip(st.columns(3, gap="small"), period_slots[offset:offset + 3]):
                    column.button(slot, key=f"booking_slot_{slot}", type="primary" if st.session_state.get("booking_time") == slot else "secondary", on_click=_choose_time, args=(slot,), width="stretch")
    return slots


def _signature(item: dict, settings: dict) -> tuple:
    return (int(item["id"]), item["name"], item.get("name_ro", ""), item.get("name_en", ""), float(item["price"]), int(item["duration"]), settings.get("currency", "MDL"))


def _edit_selection() -> None:
    confirmed = st.session_state.pop("booking_confirmation", {})
    if confirmed:
        st.session_state["booking_service"] = confirmed["service_id"]
        st.session_state["booking_date"] = confirmed["date"]
        st.session_state["booking_time"] = confirmed["time"]


def _new_booking() -> None:
    for key in ("booking_receipt", "booking_confirmation", "booking_time"):
        st.session_state.pop(key, None)


def _confirmation(db_path: Path, settings: dict, locale: str, services: list[dict]) -> None:
    confirmation = st.session_state["booking_confirmation"]
    item = next((item for item in services if item["id"] == confirmation["service_id"]), None)
    if item is None or _signature(item, settings) != confirmation["signature"]:
        st.warning(_tr(locale, "Условия услуги изменились. Пожалуйста, проверьте их перед записью.", "Condițiile serviciului s-au schimbat. Verificați-le înainte de programare."))
        st.button(_tr(locale, "Вернуться к выбору", "Înapoi la selecție"), key="booking_edit", on_click=_edit_selection)
        return
    st.subheader(_tr(locale, "Проверьте вашу запись", "Verificați programarea"))
    with st.container(border=True):
        st.markdown(f"**{html.escape(_name(item, locale))}**")
        st.write(f"{_date_label(confirmation['date'], locale)} · {confirmation['time']} · {item['duration']} {_tr(locale, 'мин.', 'min.')}")
        st.markdown(f"**{_price(item, settings, locale)}**")
        st.caption(_tr(locale, "После заявки мастер свяжется с вами и подтвердит запись.", "După cerere, specialistul vă va contacta și va confirma programarea."))
    st.button(_tr(locale, "Изменить услугу, дату или время", "Schimbă serviciul, data sau ora"), key="booking_edit", on_click=_edit_selection)
    with st.form("service_request_form"):
        st.subheader(_tr(locale, "Как с вами связаться?", "Cum vă contactăm?"))
        first, second = st.columns(2)
        name = first.text_input(_tr(locale, "Ваше имя *", "Numele dvs. *"), key="booking_contact_name")
        phone = second.text_input(_tr(locale, "Телефон +373 *", "Telefon +373 *"), placeholder="60 123 456", key="booking_contact_phone")
        with st.expander(_tr(locale, "Добавить email или пожелание", "Adaugă email sau o preferință")):
            email = st.text_input(_tr(locale, "Email — необязательно", "Email — opțional"), key="booking_contact_email")
            message = st.text_area(_tr(locale, "Комментарий — необязательно", "Comentariu — opțional"), height=80, key="booking_contact_message")
        consent = st.checkbox(_tr(locale, "Согласие на обработку контактных данных *", "Acord pentru prelucrarea datelor de contact *"), key="booking_contact_consent")
        submitted = st.form_submit_button(_tr(locale, "Отправить заявку", "Trimite cererea"), type="primary", width="stretch")
    if submitted:
        try:
            request_id = create_service_request(db_path, service_id=item["id"], slot_date=confirmation["date"], slot_time=confirmation["time"], name=name, phone=phone, email=email, message=message, consent=consent, locale=locale)
        except RequestValidationError as exc:
            ro = {
                "Укажите имя или название организации.": "Introduceți numele.",
                "Укажите номер телефона.": "Introduceți numărul de telefon.",
                "Поддерживаются только номера Молдовы +373.": "Sunt acceptate doar numerele din Moldova +373.",
                "Проверьте адрес электронной почты.": "Verificați adresa de email.",
                "Необходимо согласие на обработку контактных данных.": "Este necesar acordul pentru prelucrarea datelor de contact.",
                "Выбранное время уже недоступно. Выберите другое.": "Ora aleasă nu mai este disponibilă. Alegeți alta.",
                "Предложение недоступно.": "Oferta nu este disponibilă.",
            }
            st.error(translate_literaltext(locale, str(exc)))
        else:
            st.session_state["booking_receipt"] = {"id": request_id, "service": _name(item, locale), "service_ru": _name(item, "ru"), "service_ro": _name(item, "ro"), "service_en": _name(item, "en"), "date": confirmation["date"], "time": confirmation["time"]}
            st.session_state.pop("booking_confirmation", None)
            st.rerun()


def render_booking(db_path: str | Path, app_dir: str | Path, settings: dict[str, str], locale: str) -> None:
    from scena_design import render_stage_intro

    locale = locale if locale in {"ru", "ro", "en"} else "ru"
    db_path, app_dir = Path(db_path), Path(app_dir)
    if settings.get("professional_published", "1") != "1":
        st.title(_tr(locale, "Запись на встречу", "Programare"))
        st.info(_tr(locale, "Запись сейчас недоступна. Загляните немного позже.", "Programarea nu este disponibilă acum. Reveniți puțin mai târziu."))
        return
    if not st.session_state.get("booking_confirmation") and not st.session_state.get("booking_receipt"):
        render_stage_intro(app_dir, settings, locale,
            kicker=_tr(locale, "ВАШ ОБРАЗ · ВАШ МОМЕНТ", "IMAGINEA TA · MOMENTUL TĂU"),
            title=content_text(settings, "booking_title", locale, _tr(locale, "Время для себя", "Timp pentru tine", "Time for you")),
            text=content_text(settings, "booking_description", locale, _tr(locale, "Особенный повод или желание увидеть себя по-новому. Выберите образ и удобное время — начнём с вашей идеи.", "O ocazie specială sau dorința de a te vedea altfel. Alege serviciul și ora potrivită — pornim de la ideea ta.", "A special occasion or a wish to see yourself differently. Choose your look and a convenient time — we will start with your idea.")),
            image=settings.get("professional_hero_image", "media/scena-v13/professional-portrait.webp"),
            tag=f"{localized_name(settings, locale)} · {content_text(settings, 'location', locale)}",
        )
    else:
        st.caption(localized_name(settings, locale))
        st.title(_tr(locale, "Ваша запись", "Programarea dvs."))
    st.markdown("""<style>
    .scena-booking-date{font-size:20px!important;line-height:1.4!important;min-height:56px;padding:0 0 12px!important;margin:0!important;display:flex;align-items:flex-start}
    .st-key-booking_service button{min-height:50px!important;padding:10px 20px!important;transition:box-shadow .18s,background .18s}
    .st-key-booking_service button p{font-size:17px!important}
    .st-key-booking_service button[aria-pressed="true"]{background:linear-gradient(145deg,#e7d0a4,#c4a16a)!important;border-color:#96703c!important;color:#372718!important;box-shadow:inset 0 2px 2px #fff8,0 5px 12px #7b5c342e!important;font-weight:700!important}
    .st-key-booking_morning,.st-key-booking_afternoon{background:linear-gradient(130deg,#fffdf8,#f1e8d8)!important;box-shadow:0 8px 24px #6c523608}
    .st-key-booking_calendar [data-testid="stHorizontalBlock"] {display:flex!important;flex-direction:row!important;flex-wrap:nowrap!important;gap:6px!important}
    .st-key-booking_calendar [data-testid="stColumn"] {min-width:0!important}
    .st-key-booking_calendar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {flex:1 1 0!important}
    .st-key-booking_month_header [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {flex:5 1 0!important}
    .st-key-booking_calendar button {min-height:42px;padding:4px 0!important;min-width:0!important;border-radius:14px!important}
    .st-key-booking_calendar button p {font-size:15px!important;white-space:nowrap;line-height:1.1!important}
    .scena-calendar-weekday {text-align:center;font-size:13px;color:var(--muted,#71695f)}
    .scena-calendar-blank {height:42px}
    .st-key-booking_morning [data-testid="stHorizontalBlock"],.st-key-booking_afternoon [data-testid="stHorizontalBlock"] {display:flex!important;flex-direction:row!important;flex-wrap:nowrap!important;gap:8px!important}
    .st-key-booking_morning [data-testid="stColumn"],.st-key-booking_afternoon [data-testid="stColumn"] {min-width:0!important;flex:1 1 0!important}
    .st-key-booking_morning button,.st-key-booking_afternoon button {padding:8px!important;min-height:44px}
    @media(max-width:640px){.st-key-booking_calendar{padding:.65rem!important}.st-key-booking_calendar [data-testid="stHorizontalBlock"]{gap:3px!important}.st-key-booking_calendar button{min-height:40px}.st-key-booking_calendar button p{font-size:14px!important}}
    </style>""", unsafe_allow_html=True)
    if st.session_state.get("booking_receipt"):
        receipt = st.session_state["booking_receipt"]
        st.success(_tr(locale, f"Спасибо! Заявка №{receipt['id']} принята. Мастер свяжется с вами, чтобы подтвердить встречу.", f"Mulțumim! Cererea #{receipt['id']} a fost primită. Specialistul vă va contacta pentru a confirma întâlnirea."))
        service_name = receipt.get(f"service_{locale}", receipt["service"])
        st.write(f"{service_name} · {_date_label(receipt['date'], locale)} · {receipt['time']}")
        st.subheader(_tr(locale, "Познакомьтесь чуть ближе", "Cunoaște-ne mai bine"))
        st.write(_tr(locale, "Образы, вдохновение и история человека, которому вы доверяете свою красоту.", "Imagini, inspirație și povestea persoanei căreia îi încredințați frumusețea."))
        st.link_button(_tr(locale, "Открыть её Сцену", "Deschide Scena ei"), f"?page=scene&lang={locale}", type="primary")
        st.button(_tr(locale, "Выбрать ещё одну услугу", "Alege încă un serviciu"), key="booking_new", on_click=_new_booking)
        return
    services = list_services(db_path, "Professional", kind="appointment")
    if st.session_state.get("booking_confirmation"):
        _confirmation(db_path, settings, locale, services)
        return
    if not services:
        st.info(_tr(locale, "Новые даты и услуги появятся здесь. А пока познакомьтесь с работами мастера.", "Servicii și date noi vor apărea aici. Până atunci, descoperiți lucrările specialistului."))
        st.link_button(_tr(locale, "Посмотреть портфолио", "Vezi portofoliul"), f"?page=portfolio&lang={locale}")
        return
    valid_ids = [int(item["id"]) for item in services]
    requested = str(st.query_params.get("service", ""))
    if requested.isdigit() and int(requested) in valid_ids:
        st.session_state.setdefault("booking_service", int(requested))
    if st.session_state.get("booking_service") not in valid_ids:
        st.session_state.pop("booking_service", None)
    group_ids = {item.get("group_id") for item in services}
    labels = {
        item["id"]: (f"{item.get('group_name_'+locale) or item.get('group_name_ru') or ''} · " if len(group_ids) > 1 else "") + _name(item, locale)
        for item in services
    }
    selected_service = st.pills(_tr(locale, "1. Выберите услугу", "1. Alegeți serviciul"), valid_ids, key="booking_service", format_func=lambda value: labels.get(value, ""), on_change=_service_changed)
    if not selected_service:
        st.caption(_tr(locale, "Выберите услугу, чтобы увидеть её стоимость и свободные даты.", "Alegeți serviciul pentru a vedea prețul și datele disponibile."))
        return
    item = next(item for item in services if item["id"] == selected_service)
    st.markdown(f"**{_price(item, settings, locale)}** · {item['duration']} {_tr(locale, 'мин.', 'min.')}")
    description = content_text(item, "description", locale)
    if description:
        st.caption(description)
    now = datetime.now(CHISINAU)
    last_day = now.date() + timedelta(days=int(settings.get("booking_horizon_days", "90")))
    day_column, time_column = st.columns([1.05, 1], gap="large")
    with day_column:
        st.markdown('<h3 class="scena-booking-date">'+html.escape(_tr(locale, "2. Выберите день и время", "2. Alegeți ziua și ora", "2. Choose a day and time"))+'</h3>',unsafe_allow_html=True)
        _calendar(db_path, selected_service, locale, now, last_day)
    with time_column:
        slots = _time_blocks(db_path, selected_service, locale, now, last_day)
    chosen_time = st.session_state.get("booking_time")
    if chosen_time in slots:
        st.caption(f"{_name(item, locale)} · {_date_label(st.session_state['booking_date'], locale)} · {chosen_time}")
        if st.button(_tr(locale, "Продолжить", "Continuă"), key="booking_continue", type="primary", width="stretch"):
            st.session_state["booking_confirmation"] = {"service_id": selected_service, "date": st.session_state["booking_date"], "time": chosen_time, "signature": _signature(item, settings)}
            st.rerun()
