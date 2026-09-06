"""SCENA V1.7 — local professional workspace and personal stage."""

from __future__ import annotations

import html
import os
import tempfile
import warnings
import uuid
from datetime import date, datetime, time
from pathlib import Path
from urllib.parse import urlencode, urlparse

import streamlit as st
from PIL import Image, UnidentifiedImageError

from model_landing import (
    build_model_landing_html,
    image_uri,
    model_slides_from_settings,
    model_intro_from_settings,
    normalize_public_base_url,
    public_page_url,
    qr_png_bytes,
)

from scena_core import (
    CHISINAU,
    REQUEST_STATUSES,
    REQUEST_TYPES,
    SERVICE_CATEGORIES,
    SERVICE_KINDS,
    RequestValidationError,
    add_service_group,
    add_post,
    add_schedule_exception,
    add_service,
    archive_service,
    create_course_preregistration,
    create_request,
    create_service_request,
    delete_service,
    delete_schedule_exception,
    expire_pending_requests,
    get_admin_password,
    get_settings,
    init_db,
    list_available_dates,
    list_posts,
    list_requests,
    list_schedule_exceptions,
    list_service_groups,
    list_services,
    list_sms_outbox,
    save_settings,
    service_request_count,
    set_service_group_active,
    set_post_active,
    set_service_active,
    restore_service,
    update_service_group,
    update_request_status,
    update_service,
    verify_admin_password,
)
from scena_cabinet import (
    CabinetValidationError,
    ask_scena_assistant,
    dispatch_support_notifications,
    get_integration_health,
    get_pro_status,
    list_pro_applications,
    list_support_messages,
    submit_pro_application,
    submit_support_message,
    sync_telegram_replies,
)
from scena_integrations import OpenAIResponsesAdapter, TelegramBotAdapter
from scena_design import apply_editorial_styles, render_stage_intro, render_path_note, public_model_image


APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("SCENA_DB_PATH", APP_DIR / "scena_master.db"))
MEDIA_DIR = APP_DIR / "media"
MEDIA_DIR.mkdir(exist_ok=True)
Image.MAX_IMAGE_PIXELS = 30_000_000


from scena_i18n import tr, localized_name, content_text, translate_literaltext, normalize_locale

def ui(value: str) -> str:
    """Translate platform copy only; never user content or storage keys."""
    return translate_literaltext(st.session_state.get("scena_ui_locale", "ru"), value)


def clean(value: object) -> str:
    return html.escape(str(value or "").strip())


PUBLIC_ERROR_RO = {
    "Укажите имя или название организации.": "Introduceți numele sau denumirea organizației.",
    "Укажите номер телефона.": "Introduceți numărul de telefon.",
    "Поддерживаются только номера Молдовы +373.": "Sunt acceptate doar numerele din Moldova +373.",
    "Проверьте адрес электронной почты.": "Verificați adresa de email.",
    "Необходимо согласие на обработку контактных данных.": "Este necesar acordul pentru prelucrarea datelor de contact.",
    "Предложение недоступно.": "Oferta nu este disponibilă.",
    "Для этого предложения не используется календарь.": "Această ofertă nu utilizează calendarul.",
    "Выбранное время уже недоступно. Выберите другое.": "Ora aleasă nu mai este disponibilă. Alegeți alta.",
    "Это предложение не является курсом.": "Această ofertă nu este un curs.",
    "Укажите бренд или организацию.": "Introduceți brandul sau organizația.",
    "Укажите формат модельной работы.": "Indicați formatul proiectului de modeling.",
    "Укажите предполагаемую дату проекта.": "Indicați data estimată a proiectului.",
    "Добавьте краткий бриф проекта.": "Adăugați un brief scurt al proiectului.",
    "Укажите город.": "Indicați orașul.",
    "Выберите уровень опыта.": "Alegeți nivelul de experiență.",
}


def public_error(locale: str, error: Exception) -> str:
    message = str(error)
    return str(translate_literaltext(locale, message))


def render_data_table(rows: list[dict]) -> None:
    """Render an escaped, scrollable table without an optional dataframe runtime."""

    if not rows:
        return
    headings = list(rows[0])
    head = "".join(f"<th>{clean(ui(label))}</th>" for label in headings)
    body = "".join(
        "<tr>" + "".join(f"<td>{clean(row.get(label, ''))}</td>" for label in headings) + "</tr>"
        for row in rows
    )
    st.markdown(
        f'<div class="scena-table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ink: #201b17;
            --muted: #71695f;
            --paper: #f7f2e8;
            --card: #fffdf8;
            --line: #d9cdbb;
            --accent: #a98648;
            --accent-dark: #70552a;
            --accent-soft: #eadbbd;
            --soft: #eee6da;
            --success: #426a50;
            --danger: #9b4338;
            --gutter: clamp(1rem, 4vw, 1.6rem);
        }
        html, body, [class*="css"] {
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: var(--ink);
        }
        .stApp { background: var(--paper); }
        .block-container {
            inline-size: min(100%, 1040px);
            padding: 1.15rem var(--gutter) 3rem;
        }
        header[data-testid="stHeader"] { background: transparent; }
        #MainMenu, footer { visibility: hidden; }
        h1, h2, h3 { color: var(--ink); letter-spacing: -.025em; text-wrap: balance; }
        h1 { font-size: clamp(2.15rem, 5vw, 3.65rem) !important; line-height: 1.02 !important; }
        h2 { font-size: clamp(1.65rem, 3.4vw, 2.35rem) !important; }
        h3 { font-size: clamp(1.1rem, 2vw, 1.35rem) !important; }
        p, li { line-height: 1.58; }
        .scena-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            border-bottom: 1px solid var(--line);
            padding: .45rem 0 .9rem;
        }
        .scena-logo {
            color: var(--ink) !important;
            font-family: Georgia, serif;
            font-size: 1.25rem;
            font-weight: 700;
            letter-spacing: .12em;
            text-decoration: none !important;
        }
        .scena-locale { display: flex; gap: .35rem; align-items: center; }
        .scena-locale a {
            border: 1px solid var(--line);
            border-radius: 999px;
            color: var(--ink) !important;
            font-size: .78rem;
            font-weight: 700;
            padding: .4rem .62rem;
            text-decoration: none !important;
        }
        .scena-locale a.active { color: #fff !important; background: var(--ink); border-color: var(--ink); }
        .scena-nav {
            display: flex;
            gap: 1.1rem;
            overflow-x: auto;
            padding: .8rem 0 .35rem;
            scrollbar-width: none;
            white-space: nowrap;
        }
        .scena-nav a {
            color: var(--muted) !important;
            font-size: .86rem;
            text-decoration: none !important;
        }
        .scena-nav a.active { color: var(--accent) !important; font-weight: 700; }
        .scena-eyebrow {
            color: var(--accent);
            font-size: .74rem;
            font-weight: 750;
            letter-spacing: .16em;
            margin-bottom: .75rem;
            text-transform: uppercase;
        }
        .scena-lead { color: var(--muted); font-size: 1.08rem; line-height: 1.62; max-width: 650px; }
        .scena-section { border-top: 1px solid var(--line); margin-top: 3.2rem; padding-top: 1.35rem; }
        .scena-card, .scena-role, .scena-post, .scena-step {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 1.15rem;
            margin-bottom: .8rem;
            min-inline-size: 0;
        }
        .scena-role { min-height: 170px; }
        .scena-role small, .scena-muted { color: var(--muted); }
        .scena-role a, .scena-card a, .scena-post a { color: var(--accent-dark) !important; }
        .scena-placeholder {
            min-height: 270px;
            border: 1px solid var(--line);
            border-radius: 20px;
            background: linear-gradient(145deg, #e8dfd6, #f5efe8);
            color: #796e64;
            display: grid;
            place-items: center;
            padding: 1.5rem;
            text-align: center;
        }
        .scena-stepper {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: .55rem;
            margin: 1.2rem 0;
        }
        .scena-stepper span {
            border-top: 3px solid var(--line);
            color: var(--muted);
            font-size: .76rem;
            padding-top: .55rem;
        }
        .scena-stepper span.active { border-color: var(--accent); color: var(--ink); font-weight: 700; }
        .scena-table-wrap {
            border: 1px solid var(--line);
            border-radius: 14px;
            inline-size: 100%;
            overflow-x: auto;
        }
        .scena-table-wrap table { border-collapse: collapse; font-size: .82rem; inline-size: 100%; }
        .scena-table-wrap th, .scena-table-wrap td {
            border-bottom: 1px solid var(--line);
            padding: .65rem .7rem;
            text-align: left;
            vertical-align: top;
            white-space: nowrap;
        }
        .scena-table-wrap th { background: var(--soft); }
        .scena-note {
            background: var(--soft);
            border-left: 4px solid var(--accent);
            border-radius: 0 12px 12px 0;
            color: #4a423d;
            margin: .8rem 0 1.3rem;
            padding: .85rem 1rem;
        }
        .scena-footer {
            border-top: 1px solid var(--line);
            color: var(--muted);
            font-size: .82rem;
            margin-top: 3rem;
            padding-top: 1.25rem;
            text-align: center;
        }
        .scena-personal-hero {
            background: rgba(255,253,248,.88);
            border: 1px solid rgba(185,163,126,.55);
            border-radius: 28px;
            box-shadow: 0 28px 70px rgba(77,57,30,.14);
            margin: 1.35rem auto 2rem;
            max-width: 920px;
            overflow: hidden;
            padding: clamp(1.4rem, 4vw, 3.5rem);
            position: relative;
            text-align: center;
        }
        .scena-personal-mark {
            border: 1px solid var(--accent-soft);
            border-radius: 999px;
            color: var(--accent-dark);
            display: inline-flex;
            font-family: Georgia, serif;
            font-size: .78rem;
            letter-spacing: .34em;
            margin-bottom: .7rem;
            padding: .5rem .75rem .5rem 1rem;
        }
        .scena-personal-art {
            display: block;
            height: clamp(270px, 34vw, 350px);
            margin: -.2rem auto -.55rem;
            object-fit: contain;
            width: min(100%, 520px);
        }
        .scena-personal-name {
            font-family: Georgia, "Times New Roman", serif !important;
            font-size: clamp(2rem, 4.2vw, 3.35rem) !important;
            font-weight: 500 !important;
            letter-spacing: .01em;
            line-height: 1;
            margin: 0;
            text-transform: uppercase;
        }
        .scena-personal-role {
            color: #4f453a;
            font-family: Georgia, "Times New Roman", serif;
            font-size: clamp(1rem, 2vw, 1.35rem);
            margin: .7rem 0 1.55rem;
        }
        .scena-cta-row {
            display: flex;
            gap: .8rem;
            justify-content: center;
            margin-inline: auto;
            max-width: 560px;
        }
        .scena-cta {
            align-items: center;
            border: 1px solid var(--accent);
            border-radius: 10px;
            color: var(--accent-dark) !important;
            display: inline-flex;
            font-family: Georgia, "Times New Roman", serif;
            justify-content: center;
            min-height: 50px;
            padding: .75rem 1.25rem;
            text-decoration: none !important;
            width: 100%;
        }
        .scena-cta.primary {
            background: linear-gradient(135deg, #c9aa68, #9c7436);
            border-color: #9c7436;
            color: #fffdf8 !important;
            box-shadow: 0 10px 26px rgba(112,85,42,.18);
        }
        .scena-editorial-copy {
            margin: 0 auto 3rem;
            max-width: 720px;
            text-align: center;
        }
        .scena-editorial-copy p {
            color: var(--muted);
            font-family: Georgia, "Times New Roman", serif;
            font-size: clamp(1.12rem, 2.2vw, 1.45rem);
            line-height: 1.65;
        }
        .scena-pilot-note {
            color: var(--muted);
            font-size: .78rem;
            margin: 1rem auto 0;
            max-width: 680px;
        }
        .scena-professional-shell {
            background: #171513;
            border: 1px solid #6e5a39;
            border-radius: 28px;
            box-shadow: 0 28px 70px rgba(77,57,30,.2);
            display: grid;
            grid-template-columns: minmax(0, .95fr) minmax(420px, 1.05fr);
            margin: 1.4rem 0 2.5rem;
            min-height: 650px;
            overflow: hidden;
        }
        .scena-professional-portrait {
            background: #d8c3a3;
            min-height: 650px;
            overflow: hidden;
            position: relative;
        }
        .scena-professional-portrait img {
            height: 100%;
            inset: 0;
            object-fit: cover;
            object-position: 50% 45%;
            position: absolute;
            width: 100%;
        }
        .scena-professional-panel {
            background: #fffaf0;
            color: var(--ink);
            padding: clamp(1.5rem, 4vw, 3.4rem);
        }
        .scena-professional-kicker {
            color: var(--accent-dark);
            font-family: Georgia, "Times New Roman", serif;
            font-size: .82rem;
            letter-spacing: .18em;
            text-transform: uppercase;
        }
        .scena-professional-title {
            font-family: Georgia, "Times New Roman", serif !important;
            font-size: clamp(2rem, 4vw, 3.35rem) !important;
            font-weight: 500 !important;
            line-height: 1.04;
            margin: .7rem 0 .6rem;
        }
        .scena-professional-lead { color: var(--muted); margin-bottom: 1.6rem; }
        .scena-public-group { border-top: 1px solid var(--line); padding: 1.2rem 0 .25rem; }
        .scena-public-group h3 {
            font-family: Georgia, "Times New Roman", serif;
            font-size: 1.1rem !important;
            font-weight: 500;
            letter-spacing: .08em;
            margin: 0 0 .25rem;
            text-transform: uppercase;
        }
        .scena-public-group > p { color: var(--muted); font-size: .86rem; margin: .1rem 0 .6rem; }
        .scena-public-service {
            align-items: center;
            border-top: 1px solid rgba(217,205,187,.65);
            color: var(--ink) !important;
            display: grid;
            gap: .75rem;
            grid-template-columns: minmax(0, 1fr) auto;
            padding: .8rem 0;
            text-decoration: none !important;
        }
        .scena-public-service:first-of-type { border-top: 0; }
        .scena-public-service strong { font-family: Georgia, "Times New Roman", serif; font-size: 1.02rem; font-weight: 500; }
        .scena-public-service span { color: var(--accent-dark); font-size: .85rem; white-space: nowrap; }
        .scena-booking-entry {
            background: #286052;
            border: 1px solid #b99a59;
            border-radius: 10px;
            color: #fff !important;
            display: block;
            margin: .45rem 0 1.35rem;
            padding: .9rem 1.2rem;
            text-align: center;
            text-decoration: none !important;
        }
        .st-key-scena_admin_header {
            border-bottom: 1px solid var(--line);
            margin-bottom: .85rem;
            padding: .25rem 0 .75rem;
        }
        .st-key-scena_admin_header .scena-logo-static {
            color: var(--ink);
            font-family: Georgia, "Times New Roman", serif;
            font-size: 1.38rem;
            font-weight: 700;
            letter-spacing: .16em;
            line-height: 2.15rem;
        }
        .st-key-scena_admin_main_nav { margin: .65rem 0 .7rem; }
        .st-key-scena_admin_main_nav div[data-testid="stButtonGroup"],
        .st-key-scena_admin_main_nav div[role="radiogroup"] { width: 100%; }
        .st-key-scena_admin_main_nav button { min-height: 46px; }
        .st-key-scena_admin_subnav { margin: 0 0 .9rem; }
        .scena-pro-banner {
            align-items: center;
            background: linear-gradient(135deg, #25201b, #44382a);
            border: 1px solid #836e49;
            border-radius: 16px;
            box-shadow: 0 12px 30px rgba(47,37,25,.13);
            color: #fffaf0;
            display: flex;
            gap: 1rem;
            justify-content: space-between;
            margin: .65rem 0 1rem;
            padding: .9rem 1rem;
        }
        .scena-pro-banner strong { display: block; font-size: 1rem; }
        .scena-pro-banner span { color: #dfcfaf; font-size: .86rem; }
        .scena-pro-days {
            background: rgba(255,255,255,.1);
            border: 1px solid rgba(255,255,255,.18);
            border-radius: 999px;
            font-size: .82rem;
            font-weight: 750;
            padding: .45rem .72rem;
            white-space: nowrap;
        }
        .scena-conversation {
            display: grid;
            gap: .65rem;
            margin: 1rem 0 1.35rem;
        }
        .scena-message {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 16px 16px 16px 5px;
            max-width: 88%;
            padding: .8rem .95rem;
        }
        .scena-message.user {
            background: #eee4d3;
            border-radius: 16px 16px 5px 16px;
            justify-self: end;
        }
        .scena-message small { color: var(--muted); display: block; margin-bottom: .25rem; }
        .scena-message p { margin: 0; white-space: pre-wrap; }
        .scena-connection {
            border: 1px solid var(--line);
            border-radius: 14px;
            display: flex;
            gap: .75rem;
            justify-content: space-between;
            margin-bottom: 1rem;
            padding: .75rem .9rem;
        }
        .scena-connection b.connected { color: var(--success); }
        .scena-connection b.waiting { color: #8a6428; }
        .scena-connection b.failed { color: var(--danger); }
        .scena-breadcrumbs {
            align-items: center;
            background: rgba(255,253,248,.82);
            border: 1px solid var(--line);
            border-radius: 12px;
            color: #5d544a;
            display: flex;
            flex-wrap: wrap;
            font-size: .9rem;
            font-weight: 600;
            gap: .55rem;
            margin: 1.15rem 0 .75rem;
            padding: .65rem .8rem;
        }
        .scena-breadcrumbs a { color: var(--accent-dark) !important; text-decoration: none !important; }
        .scena-breadcrumbs strong { color: var(--ink); font-weight: 700; }
        .scena-admin-title {
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            font-size: clamp(2rem, 5vw, 3.35rem);
            letter-spacing: -.04em;
            line-height: 1.03;
            margin: .25rem 0 .35rem;
        }
        .scena-admin-lead { color: var(--muted); font-size: 1rem; margin: 0 0 1.25rem; max-width: 720px; }
        .scena-dashboard-grid {
            display: grid;
            gap: .8rem;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            margin: 1.2rem 0 2rem;
        }
        .scena-dashboard-card-content {
            color: var(--ink) !important;
            min-height: 105px;
            padding: .35rem .2rem .6rem;
        }
        .scena-dashboard-card-content small { color: var(--accent-dark); font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
        .scena-dashboard-card-content h3 { margin: .55rem 0 .35rem; }
        .scena-dashboard-card-content p { color: var(--muted); margin: 0; }
        .scena-group-card {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 18px;
            margin-bottom: .85rem;
            padding: 1rem 1.1rem;
        }
        .scena-group-summary {
            align-items: start;
            display: flex;
            gap: .8rem;
            justify-content: space-between;
            margin-bottom: .7rem;
        }
        .scena-group-summary h3 { margin: 0 0 .15rem; }
        .scena-group-summary p { color: var(--muted); font-size: .86rem; margin: 0; }
        .scena-service-row {
            align-items: center;
            border-top: 1px solid var(--line);
            display: grid;
            gap: .8rem;
            grid-template-columns: minmax(0, 1fr) auto;
            padding: .8rem 0 .3rem;
        }
        .scena-service-row strong { display: block; }
        .scena-service-row small { color: var(--muted); }
        .scena-service-empty { color: var(--muted); font-size: .9rem; padding: .75rem 0 .25rem; }
        .scena-path-example {
            background: #fffaf0;
            border: 1px dashed #bea46f;
            border-radius: 14px;
            color: #54483b;
            margin: .75rem 0 1rem;
            padding: .85rem 1rem;
        }
        .scena-service-status {
            border-radius: 999px;
            display: inline-block;
            font-size: .72rem;
            font-weight: 700;
            padding: .24rem .48rem;
        }
        .scena-service-status.public { background: #dfeadf; color: #28563a; }
        .scena-service-status.draft { background: #eee5d7; color: #6f5a3a; }
        .scena-service-status.archived { background: #eadfdd; color: #7b3a33; }
        .scena-danger-note { background: #f4e7e3; border-left: 4px solid var(--danger); border-radius: 0 12px 12px 0; padding: .8rem 1rem; }
        div.stButton > button, div.stFormSubmitButton > button, div.stLinkButton > a {
            min-height: 46px;
            border-radius: 12px;
            font-weight: 650;
        }
        div[data-testid="stForm"] {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 1.1rem;
        }
        div[data-testid="stImage"] img { border-radius: 18px; }
        [data-testid="stMetric"] {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 15px;
            padding: .8rem .9rem;
        }
        [data-testid="stDataFrame"] { max-width: 100%; overflow-x: auto; }
        div[data-testid="stPills"] button { min-height: 44px; }
        @media (max-width: 700px) {
            .block-container { padding: .75rem 1rem 2.5rem; }
            .scena-top { position: sticky; top: 0; z-index: 50; background: rgba(248,245,240,.96); }
            .scena-nav { margin-inline: -1rem; padding-inline: 1rem; }
            .scena-section { margin-top: 2.4rem; }
            .scena-role { min-height: auto; }
            h1 { font-size: clamp(2rem, 10vw, 2.8rem) !important; }
            h2 { font-size: clamp(1.55rem, 8vw, 2.05rem) !important; }
            div[data-testid="stHorizontalBlock"] { flex-direction: column !important; flex-wrap: nowrap !important; gap: .65rem !important; }
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] { flex: 1 1 100% !important; inline-size: 100% !important; min-inline-size: 0 !important; }
            div[data-testid="stTabs"] [data-baseweb="tab-list"] { overflow-x: auto; white-space: nowrap; scrollbar-width: thin; }
            div[data-testid="stForm"] { padding: .9rem; }
            input, textarea, button, [data-baseweb="select"] { font-size: 16px !important; }
            .scena-stepper { gap: .35rem; }
            .scena-stepper span { font-size: .68rem; }
            .scena-personal-hero { border-radius: 20px; margin-top: .8rem; padding: 1.25rem 1rem 1.35rem; }
            .scena-personal-art { height: min(78vw, 360px); margin-bottom: -.3rem; }
            .scena-personal-name { font-size: clamp(1.7rem, 9vw, 2.55rem); }
            .scena-cta-row { flex-direction: column; }
            .scena-professional-shell { border-radius: 20px; grid-template-columns: 1fr; min-height: 0; }
            .scena-professional-portrait { min-height: min(105vw, 500px); }
            .scena-professional-panel { padding: 1.35rem 1.1rem 1.5rem; }
            .scena-dashboard-grid { grid-template-columns: 1fr; }
            .scena-public-service { grid-template-columns: 1fr; gap: .25rem; }
            .scena-pro-banner { align-items: flex-start; flex-direction: column; }
            .scena-pro-days { white-space: normal; }
            .scena-message { max-width: 96%; }
        }
        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; transition-duration: .01ms !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_url(page: str, locale: str, **params: object) -> str:
    query = {"page": page, "lang": locale}
    query.update({key: str(value) for key, value in params.items() if value not in (None, "")})
    return "?" + urlencode(query)


def set_admin_route(locale: str, section: str, view: str = "") -> None:
    if section not in ADMIN_SECTIONS or section == "home":
        section = "work"
    views = ADMIN_VIEWS.get(section, {})
    if views and view not in views:
        view = next(iter(views))
    if not views:
        view = ""
    params = {
        "page": "admin",
        "lang": locale if locale in {"ru", "ro"} else "ru",
        "admin": "1",
        "section": section,
    }
    if view:
        params["view"] = view
    st.query_params.from_dict(params)


def image_source(value: str) -> str | None:
    candidate = str(value or "").strip()
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme in {"http", "https"}:
        return candidate
    local_path = (APP_DIR / candidate).resolve()
    try:
        local_path.relative_to(APP_DIR)
    except ValueError:
        return None
    return str(local_path) if local_path.is_file() else None


def render_image(value: str, label: str, *, portrait: bool = False) -> None:
    source = image_source(value)
    if source:
        st.image(source, width="stretch")
        return
    height = "400px" if portrait else "240px"
    st.markdown(
        f"<div class='scena-placeholder' style='min-height:{height}'><div><strong>{clean(label)}{ui('</strong><br><small>Фото добавляется в кабинете</small></div></div>')}",
        unsafe_allow_html=True,
    )


def stage_uploaded_image(uploaded_file, slot: str) -> tuple[Path, Path, str]:
    safe_slots = {
        "avatar", "beauty_1", "beauty_2", "beauty_3",
        "model_1", "model_2", "model_3",
        "model_slide_1", "model_slide_2", "model_slide_3",
        "model_slide_4", "model_slide_5",
    }
    if slot not in safe_slots:
        raise ValueError("Неизвестное назначение изображения.")
    temporary_path: Path | None = None
    try:
        uploaded_file.seek(0, os.SEEK_END)
        if uploaded_file.tell() > 20 * 1024 * 1024:
            raise ValueError("Размер одного изображения не должен превышать 20 МБ.")
        uploaded_file.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(uploaded_file) as source:
                source.verify()
            uploaded_file.seek(0)
            with Image.open(uploaded_file) as source:
                image = source.convert("RGB")
                image.thumbnail((1800, 1800))
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{slot}-", suffix=".webp", dir=MEDIA_DIR
            )
            os.close(descriptor)
            temporary_path = Path(temporary_name)
            image.save(temporary_path, "WEBP", quality=88, method=6)
        destination = MEDIA_DIR / f"{slot}-{uuid.uuid4().hex}.webp"
    except ValueError:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError) as exc:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise ValueError("Файл не является поддерживаемым изображением.") from exc
    return temporary_path, destination, destination.relative_to(APP_DIR).as_posix()


def save_uploaded_images(selections: list[tuple[str, str, object]]) -> int:
    staged: list[tuple[str, Path, Path, str]] = []
    try:
        for slot, setting_key, uploaded in selections:
            temporary, destination, relative = stage_uploaded_image(uploaded, slot)
            staged.append((setting_key, temporary, destination, relative))
    except Exception:
        for _, temporary, _, _ in staged:
            temporary.unlink(missing_ok=True)
        raise
    committed: list[tuple[Path, Path | None]] = []
    try:
        for _, temporary, destination, _ in staged:
            backup = None
            if destination.exists():
                descriptor, backup_name = tempfile.mkstemp(
                    prefix=f".{destination.stem}-backup-", suffix=destination.suffix,
                    dir=MEDIA_DIR,
                )
                os.close(descriptor)
                backup = Path(backup_name)
                os.replace(destination, backup)
            committed.append((destination, backup))
            os.replace(temporary, destination)
        save_settings(DB_PATH, {key: relative for key, _, _, relative in staged})
    except Exception:
        for destination, backup in reversed(committed):
            destination.unlink(missing_ok=True)
            if backup and backup.exists():
                os.replace(backup, destination)
        for _, temporary, _, _ in staged:
            temporary.unlink(missing_ok=True)
        raise
    else:
        for _, backup in committed:
            if backup:
                backup.unlink(missing_ok=True)
    return len(staged)


def detected_locale(settings: dict[str, str]) -> str:
    requested = str(st.query_params.get("lang", "")).lower()
    if requested in {"ru", "ro", "en"}:
        return requested
    browser_locale = ""
    try:
        browser_locale = str(getattr(st.context, "locale", "") or "").lower()
    except Exception:
        browser_locale = ""
    if browser_locale.startswith("ru"):
        return "ru"
    if browser_locale.startswith("ro"):
        return "ro"
    if browser_locale.startswith("en"):
        return "en"
    return settings.get("default_locale", "ro") if settings.get("default_locale") in {"ru", "ro", "en"} else "ro"


def render_header(page: str, locale: str, *, admin: bool = False) -> None:
    if admin:
        section = str(st.query_params.get("section", "work"))
        view = str(st.query_params.get("view", ""))
        with st.container(key="scena_admin_header"):
            brand_col, mode_col, locale_col = st.columns([2, 3, 2], vertical_alignment="bottom")
            with brand_col:
                badge = '<span class="scena-pro-mark">PRO</span>' if get_pro_status(DB_PATH)['is_active'] else ''
                st.markdown('<div class="scena-logo-static">SCENA'+badge+'</div>', unsafe_allow_html=True)
            with mode_col:
                owner = f'<div class="scena-owner-name">{clean(localized_name(get_settings(DB_PATH), locale))}</div>' if st.session_state.get("scena_admin_authenticated") else ""
                st.markdown(f'<div class="scena-workspace-title">{clean(tr(locale, "Рабочий кабинет", "Spațiu de lucru", "Workspace"))}</div>'+owner, unsafe_allow_html=True)
            with locale_col:
                selected_locale = st.segmented_control(
                    ui("Язык"),
                    ("ru", "ro", "en"),
                    default=locale,
                    format_func=lambda value: value.upper(),
                    key=f"admin_locale_navigation_{locale}_{section}_{view or 'root'}",
                    label_visibility="collapsed",
                    width="stretch",
                )
        if selected_locale and selected_locale != locale:
            set_admin_route(selected_locale, section, view)
            st.rerun()
        return
    retained = {}
    if page == "post":
        retained['post'] = st.query_params.get('post', '')
    elif page == "posts":
        retained['destination'] = st.query_params.get('destination', 'scene')
    elif page == "portfolio":
        retained['view'] = st.query_params.get('view', 'professional')
    elif page in {"booking", "course"}:
        retained['service'] = st.query_params.get('service', '')
    ru_url = page_url(page, "ru", **retained)
    ro_url = page_url(page, "ro", **retained)
    en_url = page_url(page, "en", **retained)
    mode = tr(locale, "Моя Сцена", "Scena mea")
    st.markdown(
        f"""
        <div class="scena-top">
          <a class="scena-logo" href="{page_url('scene', locale)}" target="_self">SCENA</a>
          <span class="scena-muted">{clean(mode)}</span>
          <div class="scena-locale">
            <a class="{'active' if locale == 'ru' else ''}" href="{ru_url}" target="_self">RU</a>
            <a class="{'active' if locale == 'ro' else ''}" href="{ro_url}" target="_self">RO</a>
            <a class="{'active' if locale == 'en' else ''}" href="{en_url}" target="_self">EN</a>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    items = [
        ("scene", tr(locale, "Моя Сцена", "Scena mea")),
        ("portfolio", tr(locale, "Портфолио", "Portofoliu")),
        ("professional", tr(locale, "Услуги и курсы", "Servicii și cursuri")),
        ("model", "Model"),
        ("join-model", tr(locale, "Стать моделью", "Devino model")),
    ]
    settings = get_settings(DB_PATH)
    items = [(key, label) for key, label in items if key != "model" or (settings.get("model_in_scene", "1") == "1" and settings.get("model_published", "1") == "1")]
    if settings.get("shop_enabled", "0") == "1":
        items.insert(-1, ("shop", "Market"))
    links = "".join(
        f'<a class="{"active" if key == page else ""}" href="{page_url(key, locale)}" target="_self">{clean(label)}</a>'
        for key, label in items
    )
    st.markdown(f'<nav class="scena-nav">{links}</nav>', unsafe_allow_html=True)


def render_footer(locale: str) -> None:
    st.markdown(
        f"""
        <div class="scena-footer">
          SCENA · {clean(tr(locale, 'Ваша история. Ваша Сцена.', 'Povestea ta. Scena ta.'))}<br>
          <a href="{page_url('admin', locale, admin='1')}" target="_self">{clean(tr(locale, 'Вход в кабинет', 'Intrare în cabinet'))}</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def configured_admin_password() -> str | None:
    password = get_admin_password()
    if password:
        return password
    try:
        secret = str(st.secrets.get("SCENA_ADMIN_PASSWORD", "")).strip()
    except (FileNotFoundError, KeyError):
        secret = ""
    return secret or None


def require_admin(locale: str) -> None:
    if st.session_state.get("scena_admin_authenticated"):
        return
    render_header("admin", locale, admin=True)
    st.title(ui("Вход в кабинет"))
    st.caption(ui("Заявки, график и настройки доступны только после проверки пароля."))
    configured = configured_admin_password()
    if not configured:
        st.error(
            ui("Пароль администратора не настроен. Запустите приложение через START-SCENA.cmd "
            "или задайте переменную SCENA_ADMIN_PASSWORD.")
        )
        st.markdown(f"{ui('[← Открыть публичную страницу](')}{page_url('scene', locale)})")
        st.stop()
    attempts = int(st.session_state.get("scena_admin_attempts", 0))
    if attempts >= 5:
        st.error(ui("Слишком много неверных попыток. Закройте вкладку и откройте приложение заново."))
        st.stop()
    with st.form("admin_login_form"):
        candidate = st.text_input(ui("Пароль"), type="password", autocomplete="current-password")
        submitted = st.form_submit_button(ui("Войти"), type="primary", width="stretch")
    if submitted:
        if verify_admin_password(candidate, configured):
            st.session_state["scena_admin_authenticated"] = True
            st.session_state["scena_admin_attempts"] = 0
            st.rerun()
        st.session_state["scena_admin_attempts"] = attempts + 1
        st.error(ui("Неверный пароль."))
    st.markdown(f"{ui('[← Открыть публичную страницу](')}{page_url('scene', locale)})")
    st.stop()


def rerun_admin_with_success(message: str) -> None:
    """Keep a save confirmation visible after Streamlit reruns the page."""

    st.session_state["scena_admin_notice"] = ("success", message)
    st.rerun()


def rerun_admin_with_notice(kind: str, message: str) -> None:
    """Keep a typed cabinet notice visible after a Streamlit rerun."""

    if kind not in {"success", "warning", "error", "info"}:
        kind = "info"
    st.session_state["scena_admin_notice"] = (kind, message)
    st.rerun()


def service_name(service: dict, locale: str) -> str:
    return content_text(service, "name", locale)


def service_description(service: dict, locale: str) -> str:
    return content_text(service, "description", locale)


def format_price(service: dict, currency: str, locale: str) -> str:
    price = float(service["price"])
    if not price:
        return tr(locale, "Цена по договорённости", "Preț la înțelegere")
    return f"{price:,.0f} {currency}".replace(",", " ")


def contact_buttons(settings: dict[str, str]) -> None:
    links = []
    for label, key in (("Instagram", "instagram_url"), ("Telegram", "telegram_url")):
        url = settings.get(key, "").strip()
        if urlparse(url).scheme in {"http", "https"}:
            links.append((label, url))
    if not links:
        return
    columns = st.columns(len(links))
    for column, (label, url) in zip(columns, links):
        with column:
            st.link_button(label, url, width="stretch")


def render_posts(locale: str, destination: str) -> None:
    from scena_publication_ui import render_feed
    render_feed(DB_PATH, APP_DIR, get_settings(DB_PATH), locale, destination)


def portfolio_images(settings: dict[str, str], kind: str) -> list[str]:
    prefix = "beauty" if kind == "professional" else "model"
    return [settings.get(f"{prefix}_image_{index}", "") for index in range(1, 13)]


def render_portfolio_grid(settings: dict[str, str], locale: str, kind: str) -> None:
    from scena_portfolio import render_portfolio
    render_portfolio(APP_DIR, settings, locale, kind)


def render_scene(settings: dict[str, str], locale: str) -> None:
    if settings.get("profile_published", "1") != "1":
        st.title(tr(locale, "Моя Сцена", "Scena mea"))
        st.info(tr(locale, "Личное пространство пока не опубликовано.", "Spațiul personal nu este încă publicat."))
        return
    hero_value = settings.get("avatar_url", "").strip() or settings.get(
        "scene_hero_image", "media/scena-v13/my-scena-hero.webp"
    )
    hero_uri = image_uri(APP_DIR, hero_value)
    hero_html = (
        f'<img class="scene-art" src="{clean(hero_uri)}" '
        f'alt="{clean(localized_name(settings, locale))}">'
        if hero_uri else ""
    )
    actions: list[str] = []
    if settings.get("professional_published", "1") == "1" and settings.get("professional_in_scene", "1") == "1":
        actions.append(
            f'<a class="scena-cta primary" href="{page_url("booking", locale)}" target="_self">'
            f'{clean(content_text(settings, "booking_cta", locale, tr(locale, "Записаться на макияж", "Programare la machiaj", "Book makeup")))}</a>'
        )
    if settings.get("model_published", "1") == "1" and settings.get("model_in_scene", "1") == "1":
        actions.append(
            f'<a class="scena-cta" href="{page_url("model", locale)}" target="_self">'
            f'{clean(tr(locale, "Открыть Model", "Deschide Model"))}</a>'
        )
    bio = content_text(settings, "bio", locale)
    st.markdown(
        f"""
        <section class="scena-editorial-scene">
          {hero_html}
          <div class="scene-identity">
          <div class="scena-eyebrow">{clean(tr(locale, 'Моя Сцена · знакомство', 'Scena mea · cunoaște-mă'))}</div>
          <h1 class="scena-personal-name">{clean(localized_name(settings, locale))}</h1>
          <p class="scena-personal-role">Model &amp; Makeup Artist</p>
          <p>{clean(bio)}</p>
          <small class="scena-muted">{clean(content_text(settings, 'location', locale))}</small>
          <div class="scena-cta-row">{''.join(actions)}</div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    contact_buttons(settings)
    st.markdown("<div class='scena-section'></div>", unsafe_allow_html=True)
    render_posts(locale, "scene")


def render_portfolio_page(settings: dict[str, str], locale: str) -> None:
    st.markdown(
        f"<div class='scena-eyebrow'>SCENA · {clean(tr(locale, 'История в кадрах', 'Poveste în imagini'))}</div>",
        unsafe_allow_html=True,
    )
    st.title(tr(locale, "Портфолио", "Portofoliu"))
    view = str(st.query_params.get("view", "professional"))
    if view not in {"professional", "model"}:
        view = "professional"
    tabs = st.columns(2)
    with tabs[0]:
        st.link_button(
            tr(locale, "Профессиональное", "Profesional"),
            page_url("portfolio", locale, view="professional"),
            width="stretch",
            type="primary" if view == "professional" else "secondary",
        )
    with tabs[1]:
        st.link_button(
            "Model",
            page_url("portfolio", locale, view="model"),
            width="stretch",
            type="primary" if view == "model" else "secondary",
        )
    published_key = "professional_published" if view == "professional" else "model_published"
    if settings.get(published_key, "1") != "1":
        st.info(tr(locale, "Этот раздел пока не опубликован.", "Această secțiune nu este încă publicată."))
        return
    render_portfolio_grid(settings, locale, view)


def render_offering_card(service: dict, settings: dict[str, str], locale: str) -> None:
    name = service_name(service, locale)
    description = service_description(service, locale)
    kind = service["kind"]
    detail = format_price(service, settings["currency"], locale)
    if kind == "appointment":
        detail += f" · {service['duration']} {tr(locale, 'мин.', 'min.')}"
        target = page_url("booking", locale, service=service["id"])
        action = tr(locale, "Выбрать время", "Alege ora")
    elif kind == "course":
        target = page_url("course", locale, service=service["id"])
        action = tr(locale, "Описание и предзапись", "Descriere și preînscriere")
    else:
        target = page_url("invite-model", locale)
        action = tr(locale, "Отправить запрос", "Trimite o cerere")
    st.markdown(
        f"<div class='scena-card'><div class='scena-eyebrow'>{clean(tr(locale, SERVICE_KINDS[kind], {'appointment': 'Programare', 'course': 'Curs · preînscriere', 'inquiry': 'Solicitare fără calendar'}[kind]))}</div>"
        f"<h3>{clean(name)}</h3><p>{clean(description)}</p><p><strong>{clean(detail)}</strong></p>"
        f"<a href='{target}' target='_self'>{clean(action)} →</a></div>",
        unsafe_allow_html=True,
    )


def render_professional(settings: dict[str, str], locale: str) -> None:
    if settings.get("professional_published", "1") != "1":
        st.title(tr(locale, "Профессиональная страница", "Pagina profesională"))
        st.info(tr(locale, "Страница пока не опубликована.", "Pagina nu este încă publicată."))
        return
    title = content_text(settings, "beauty_title", locale)
    description = content_text(settings, "beauty_desc", locale)
    offerings = list_services(DB_PATH, "Professional")
    groups = list_service_groups(DB_PATH, "Professional")
    service_html: list[str] = []
    for group in groups:
        group_services = [
            item for item in offerings if item.get("group_id") == group["id"]
        ]
        if not group_services:
            continue
        group_name = content_text(group, "name", locale)
        group_description = content_text(group, "description", locale)
        rows: list[str] = []
        for service in group_services:
            target = (
                page_url("course", locale, service=service["id"])
                if service["kind"] == "course"
                else page_url("booking", locale, service=service["id"])
            )
            detail = format_price(service, settings["currency"], locale)
            if service["kind"] == "appointment":
                detail += f" · {service['duration']} {tr(locale, 'мин.', 'min.')}"
            rows.append(
                f'<a class="scena-public-service" href="{target}" target="_self"><strong>{clean(service_name(service, locale))}</strong><span>{clean(detail)} →</span></a>'
            )
        service_html.append(
            f'<div class="scena-public-group"><h3>{clean(group_name)}</h3><p>{clean(group_description)}</p>{"".join(rows)}</div>'
        )
    portrait_value = settings.get("beauty_image_1", "").strip() or settings.get(
        "professional_hero_image", "media/scena-v13/professional-portrait.webp"
    )
    portrait_uri = image_uri(APP_DIR, portrait_value)
    portrait_html = (
        f'<img src="{clean(portrait_uri)}" alt="{clean(tr(locale, "Профессиональный beauty-портрет Марии", "Portret beauty profesional al Mariei"))}">'
        if portrait_uri else ""
    )
    empty_html = ""
    if not service_html:
        empty_html = f'<p class="scena-muted">{clean(tr(locale, "Предложения пока не опубликованы.", "Ofertele nu sunt încă publicate."))}</p>'
    professional_markup = (
        '<section class="scena-professional-shell">'
        f'<div class="scena-professional-portrait">{portrait_html}</div>'
        '<div class="scena-professional-panel">'
        f'<div class="scena-professional-kicker">SCENA · {clean(localized_name(settings, locale))}</div>'
        f'<h1 class="scena-professional-title">{clean(title)}</h1>'
        f'<p class="scena-professional-lead">{clean(description)}</p>'
        f'<a class="scena-booking-entry" href="{page_url("booking", locale)}" target="_self">'
        f'{clean(tr(locale, "Выбрать услугу и время", "Alege serviciul și ora"))}</a>'
        f'{"".join(service_html)}{empty_html}'
        '</div></section>'
    )
    st.markdown(professional_markup, unsafe_allow_html=True)
    st.markdown(
        f'<div class="scena-cta-row"><a class="scena-cta" href="{page_url("portfolio", locale, view="professional")}" target="_self">{clean(tr(locale, "Открыть портфолио", "Deschide portofoliul"))}</a></div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div class='scena-section'></div>", unsafe_allow_html=True)
    render_posts(locale, "professional")


def render_model(settings: dict[str, str], locale: str) -> None:
    if settings.get("model_published", "1") != "1":
        render_header("model", locale)
        st.title("Model")
        st.info(tr(locale, "Страница пока не опубликована.", "Pagina nu este încă publicată."))
        render_footer(locale)
        return
    slides = model_slides_from_settings(settings, APP_DIR)
    if model_intro_from_settings(settings, APP_DIR) or (settings.get("model_slider_enabled", "1") == "1" and slides):
        st.markdown(
            """
            <style>
            header[data-testid="stHeader"], footer { display: none !important; }
            .block-container { inline-size: 100% !important; max-inline-size: none !important; padding: 0 !important; }
            [data-testid="stAppViewContainer"], [data-testid="stMain"], .stApp { background: #030303 !important; }
            [data-testid="stIFrame"] { display: block; border: 0; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.iframe(
            build_model_landing_html(settings, locale, APP_DIR),
            width="stretch",
            height=920,
        )
        return
    render_header("model", locale)
    title = settings.get("model_title", "") if locale == "ru" else settings.get("model_title_ro", "")
    description = settings.get("model_desc", "") if locale == "ru" else settings.get("model_desc_ro", "")
    st.markdown("<div class='scena-eyebrow'>Model</div>", unsafe_allow_html=True)
    st.title(title)
    st.markdown(f"<div class='scena-lead'>{clean(description)}</div>", unsafe_allow_html=True)
    buttons = st.columns(3)
    with buttons[0]:
        st.link_button(
            tr(locale, "Модельное портфолио", "Portofoliu model"),
            page_url("portfolio", locale, view="model"), width="stretch",
        )
    with buttons[1]:
        st.link_button(
            tr(locale, "Пригласить как модель", "Invită ca model"),
            page_url("invite-model", locale), width="stretch", type="primary",
        )
    with buttons[2]:
        st.link_button(
            tr(locale, "Хочу стать моделью", "Vreau să devin model"),
            page_url("join-model", locale), width="stretch",
        )
    st.markdown("<div class='scena-section'></div>", unsafe_allow_html=True)
    render_portfolio_grid(settings, locale, "model")
    st.markdown("<div class='scena-section'></div>", unsafe_allow_html=True)
    render_posts(locale, "model")
    render_footer(locale)


def submit_model_request(locale: str, **payload: object) -> None:
    try:
        request_id = create_request(DB_PATH, locale=locale, **payload)
    except RequestValidationError as exc:
        st.error(public_error(locale, exc))
        return
    st.success(
        tr(locale, f'Заявка №{request_id} сохранена. Это запрос: решение и условия подтверждаются отдельно.', f'Cererea #{request_id} a fost salvată. Este o solicitare: decizia și condițiile se confirmă separat.', f'Request #{request_id} saved. Participation and terms are confirmed separately.')
    )


def render_join_model(locale: str) -> None:
    settings = get_settings(DB_PATH)
    from scena_workspace_ui import render_model_path
    render_model_path(APP_DIR, settings, locale)
    with st.form("model_application_form"):
        left, right = st.columns(2)
        with left:
            name = st.text_input(tr(locale, "Ваше публичное имя *", "Numele public *"))
            phone = st.text_input(tr(locale, "Телефон +373 *", "Telefon +373 *"), placeholder="60 123 456")
        with right:
            city = st.text_input(tr(locale, "Город *", "Oraș *"), value="Кишинёв" if locale == "ru" else "Chișinău")
            email = st.text_input("Email")
        experience_options = [
            tr(locale, "Без опыта", "Fără experiență"),
            tr(locale, "Есть любительские съёмки", "Am ședințe foto de amator"),
            tr(locale, "Есть профессиональный опыт", "Am experiență profesională"),
        ]
        experience = st.selectbox(tr(locale, "Опыт *", "Experiență *"), experience_options)
        message = st.text_area(tr(locale, "Расскажите о себе", "Povestiți despre dvs."), height=80, placeholder=tr(locale,"Какой образ мечтаете примерить?","Ce imagine visezi să încerci?"))
        consent = st.checkbox(tr(locale, "Согласие на обработку контактных данных *", "Acord pentru prelucrarea datelor de contact *"))
        submitted = st.form_submit_button(tr(locale, "Отправить заявку", "Trimite cererea"), type="primary", width="stretch")
    if submitted:
        submit_model_request(
            locale, request_type="model_application", name=name, phone=phone,
            email=email, city=city, experience=experience, message=message,
            consent=consent,
        )


def render_invite_model(settings: dict[str, str], locale: str) -> None:
    if settings.get("model_published", "1") != "1":
        st.title(tr(locale, "Пригласить как модель", "Invită ca model"))
        st.info(tr(locale, "Модельная страница пока не опубликована.", "Pagina de model nu este încă publicată."))
        return
    render_stage_intro(APP_DIR, settings, locale, kicker="SCENA · COLLABORATION",
        title=tr(locale, "Пригласить как модель", "Invită ca model"),
        text=tr(locale,"У вашего проекта есть идея. Давайте найдём для неё образ. Расскажите о съёмке, показе или кампании — обсудим детали и условия участия.","Proiectul vostru are o idee. Să-i găsim imaginea. Povestiți despre ședința foto, prezentare sau campanie — discutăm detaliile și condițiile de participare."),
        image=public_model_image(APP_DIR, settings, 3), tag=localized_name(settings, locale), mobile_y=8,
    )
    model_offers = list_services(DB_PATH, "Model")
    formats = {service_name(item, locale): item["name"] for item in model_offers}
    if not formats:
        formats = {tr(locale, "Модельный проект", "Proiect de modeling"): "Модельный проект"}
    with st.form("model_invitation_form"):
        left, right = st.columns(2)
        with left:
            organization = st.text_input(tr(locale, "Бренд / организация *", "Brand / organizație *"))
            name = st.text_input(tr(locale, "Контактное лицо *", "Persoană de contact *"))
        with right:
            phone = st.text_input(tr(locale, "Телефон +373 *", "Telefon +373 *"), placeholder="60 123 456")
            email = st.text_input("Email")
        selected = st.selectbox(tr(locale, "Формат проекта *", "Formatul proiectului *"), list(formats))
        project_date = st.date_input(
            tr(locale, "Предполагаемая дата *", "Data estimată *"),
            min_value=datetime.now(CHISINAU).date(),
        )
        message = st.text_area(tr(locale, "Краткий бриф *", "Brief scurt *"))
        consent = st.checkbox(tr(locale, "Согласие на обработку контактных данных *", "Acord pentru prelucrarea datelor de contact *"))
        submitted = st.form_submit_button(tr(locale, "Отправить приглашение", "Trimite invitația"), type="primary", width="stretch")
    if submitted:
        submit_model_request(
            locale, request_type="model_invitation", name=name, phone=phone,
            email=email, organization=organization, service=formats[selected],
            preferred_date=project_date.isoformat(), message=message, consent=consent,
        )


def pill_choice(label: str, options: list, *, key: str, format_func=None):
    if hasattr(st, "pills"):
        return st.pills(label, options, key=key, format_func=format_func)
    return st.radio(label, [None, *options], key=key, format_func=format_func, horizontal=True)


def human_date(value: str, locale: str) -> str:
    parsed = date.fromisoformat(value)
    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    weekdays_ro = ["Lu", "Ma", "Mi", "Jo", "Vi", "Sâ", "Du"]
    weekday = weekdays_ru[parsed.weekday()] if locale == "ru" else weekdays_ro[parsed.weekday()]
    return f"{weekday}, {parsed:%d.%m}"


def render_stepper(locale: str, active: int) -> None:
    labels = [
        tr(locale, "1. Услуга", "1. Serviciu"),
        tr(locale, "2. Дата и время", "2. Data și ora"),
        tr(locale, "3. Контакты", "3. Contacte"),
    ]
    spans = "".join(
        f'<span class="{"active" if index <= active else ""}">{clean(label)}</span>'
        for index, label in enumerate(labels, start=1)
    )
    st.markdown(f'<div class="scena-stepper">{spans}</div>', unsafe_allow_html=True)


def render_booking(settings: dict[str, str], locale: str) -> None:
    from scena_booking_ui import render_booking as render_booking_screen
    render_booking_screen(DB_PATH, APP_DIR, settings, locale)


def render_course(settings: dict[str, str], locale: str) -> None:
    if settings.get("professional_published", "1") != "1":
        st.title(tr(locale, "Курс", "Curs"))
        st.info(tr(locale, "Профессиональная страница пока не опубликована.", "Pagina profesională nu este încă publicată."))
        return
    requested = str(st.query_params.get("service", ""))
    courses = list_services(DB_PATH, "Professional", kind="course")
    course = next((item for item in courses if str(item["id"]) == requested), None)
    if course is None:
        st.warning(tr(locale, "Курс не найден или предзапись закрыта.", "Cursul nu a fost găsit sau preînscrierea este închisă."))
        return
    description = service_description(course, locale)
    if course.get('name') == 'Авторский курс' and description == tr(locale, 'Предварительная запись без автоматического подтверждения места.', 'Preînscriere fără confirmarea automată a locului.'):
        description = tr(locale, 'Новый навык начинается с первого шага. Узнайте программу, формат занятий и ближайшие даты у автора курса.', 'O abilitate nouă începe cu primul pas. Aflați programul, formatul și datele apropiate de la autorul cursului.')
    render_stage_intro(APP_DIR, settings, locale, kicker="SCENA · BEAUTY CLASS",
        title=service_name(course, locale),
        text=description,
        image=settings.get('professional_hero_image', ''),
        tag=localized_name(settings, locale) + ' · ' + format_price(course, settings['currency'], locale),
    )
    st.write(tr(locale,"Хотите узнать программу и ближайшие даты? Оставьте контакты — обсудим обучение и подтвердим место лично.","Doriți să aflați programul și datele apropiate? Lăsați datele de contact — discutăm despre curs și confirmăm locul personal."))
    with st.form("course_preregistration_form"):
        left, right = st.columns(2)
        with left:
            name = st.text_input(tr(locale, "Ваше имя *", "Numele dvs. *"))
        with right:
            phone = st.text_input(tr(locale, "Телефон +373 *", "Telefon +373 *"), placeholder="60 123 456")
        email = st.text_input("Email")
        message = st.text_area(tr(locale, "Ваш вопрос — необязательно", "Întrebarea dvs. — opțional"), height=80)
        consent = st.checkbox(tr(locale, "Согласие на обработку контактных данных *", "Acord pentru prelucrarea datelor de contact *"))
        submitted = st.form_submit_button(tr(locale, "Предварительно записаться", "Preînscrie-mă"), type="primary", width="stretch")
    if submitted:
        try:
            request_id = create_course_preregistration(
                DB_PATH, service_id=int(course["id"]), name=name, phone=phone,
                email=email, message=message, consent=consent, locale=locale,
            )
        except RequestValidationError as exc:
            st.error(public_error(locale, exc))
        else:
            st.success(
                tr(locale, f'Заявка №{request_id} сохранена. Мастер свяжется с вами, чтобы обсудить программу и подтвердить место.', f'Cererea #{request_id} a fost salvată. Specialistul vă va contacta pentru a discuta programul și a confirma locul.', f'Request #{request_id} saved. The specialist will contact you to discuss the program and confirm your place.')
            )


def render_crm() -> None:
    expire_pending_requests(DB_PATH)
    rows = list_requests(DB_PATH)
    counts = {key: sum(row["request_type"] == key for row in rows) for key in REQUEST_TYPES}
    metric_columns = st.columns(4)
    metric_columns[0].metric(ui('Все'), len(rows))
    metric_columns[1].metric(ui('Услуги'), counts["service_request"])
    metric_columns[2].metric(ui('Курсы'), counts["course_preregistration"])
    metric_columns[3].metric(ui('Модельный путь'), counts["model_application"] + counts["model_invitation"])
    filter_options = {"all": "Все пути", **REQUEST_TYPES}
    selected_filter = st.selectbox(ui("Показать"), list(filter_options), format_func=lambda key: ui(filter_options[key]))
    visible = rows if selected_filter == "all" else [row for row in rows if row["request_type"] == selected_filter]
    if not visible:
        st.info(ui("В выбранной категории заявок пока нет."))
        return
    st.subheader(ui("Список заявок"))
    display_rows = []
    for row in visible:
        title = f"#{row['id']} · {ui(REQUEST_TYPES[row['request_type']])} · {row['name']}"
        with st.expander(title, expanded=len(visible) == 1):
            st.caption(f"{ui('Статус: ')}{ui(row['status'])}{ui(' · Создано: ')}{row['created_at']}")
            detail_columns = st.columns(2)
            details = [
                ("Телефон", row["phone"]), ("Email", row["email"]),
                ("Организация", row["organization"]), ("Услуга / формат", row["service"]),
                ("Дата и время", " · ".join(value for value in (row["preferred_date"], row["preferred_time"]) if value)),
                ("Язык", row["locale"].upper()), ("Город", row["city"]),
                ("Опыт", row["experience"]), ("Сообщение", row["message"]),
                ("Удержание до", row["hold_expires_at"]),
            ]
            for index, (label, value) in enumerate(details):
                with detail_columns[index % 2]:
                    st.caption(ui(label))
                    st.write(value or "—")
        display_rows.append({
            "ID": row["id"], "Путь": ui(REQUEST_TYPES[row["request_type"]]),
            "Имя": row["name"], "Телефон": row["phone"], "Услуга": row["service"],
            "Дата": row["preferred_date"], "Время": row["preferred_time"],
            "Статус": ui(row["status"]), "Язык": row["locale"].upper(),
        })
    with st.expander(ui("Полная таблица заявок")):
        st.caption(ui("На телефоне таблица прокручивается внутри этого блока."))
        render_data_table(display_rows)
    st.subheader(ui("Изменить статус"))
    labels = {row["id"]: f"#{row['id']} · {ui(REQUEST_TYPES[row['request_type']])} · {row['name']}" for row in visible}
    with st.form("status_form"):
        request_id = st.selectbox(ui("Заявка"), list(labels), format_func=labels.get)
        current = next(row["status"] for row in visible if row["id"] == request_id)
        status = st.selectbox(ui("Статус"), REQUEST_STATUSES, index=REQUEST_STATUSES.index(current), format_func=ui)
        submitted = st.form_submit_button(ui("Сохранить статус"), type="primary")
    if submitted:
        try:
            update_request_status(DB_PATH, request_id, status)
        except RequestValidationError as exc:
            st.error(ui(str(exc)))
        else:
            rerun_admin_with_success(
                "Статус обновлён; соответствующее SMS добавлено в очередь, "
                "если статус требует сообщения."
            )


def render_profile_admin(settings: dict[str, str]) -> None:
    st.write(ui("Здесь настраивается обязательное личное пространство «Моя Сцена» и видимость направлений."))
    with st.form("profile_form"):
        left, right = st.columns(2)
        with left:
            name = st.text_input(ui("Публичное имя"), value=settings["master_name"])
            slug = st.text_input(ui("Уникальный адрес"), value=settings["profile_slug"])
            location = st.text_input(ui("Город"), value=settings["location"])
            currency = st.text_input(ui("Валюта"), value=settings["currency"], max_chars=8)
            instagram = st.text_input("Instagram", value=settings["instagram_url"])
            telegram = st.text_input("Telegram", value=settings["telegram_url"])
        with right:
            profile_published = st.checkbox(ui("«Моя Сцена» опубликована"), value=settings["profile_published"] == "1")
            profile_indexed = st.checkbox(ui("Разрешить индексацию «Моей Сцены»"), value=settings["profile_indexed"] == "1")
            professional_in_scene = st.checkbox(ui("Показывать профессиональную страницу в «Моей Сцене»"), value=settings["professional_in_scene"] == "1")
            model_in_scene = st.checkbox(ui("Показывать Model в «Моей Сцене»"), value=settings["model_in_scene"] == "1")
            pilot_notice = False
        st.subheader(ui("О человеке"))
        bio_ru = st.text_area(ui("Текст RU"), value=settings["bio"], height=110)
        bio_ro = st.text_area("Text RO", value=settings["bio_ro"], height=110)
        bio_approved = st.checkbox(ui("Языковые версии проверены"), value=settings["bio_translation_approved"] == "1")
        st.caption(ui("Проверьте тексты на русском и румынском перед публикацией."))
        role_a, role_b = st.columns(2)
        with role_a:
            st.subheader(ui("Профессиональная страница"))
            beauty_title = st.text_input(ui("Название RU"), value=settings["beauty_title"], key="beauty_title_ru")
            beauty_title_ro = st.text_input("Denumire RO", value=settings["beauty_title_ro"])
            beauty_desc = st.text_area(ui("Описание RU"), value=settings["beauty_desc"])
            beauty_desc_ro = st.text_area("Descriere RO", value=settings["beauty_desc_ro"])
            professional_published = st.checkbox(ui("Страница опубликована"), value=settings["professional_published"] == "1", key="professional_published")
            professional_indexed = st.checkbox(ui("Индексация включена"), value=settings["professional_indexed"] == "1", key="professional_indexed")
            professional_approved = st.checkbox(ui("Обе версии страницы проверены"), value=settings["professional_translation_approved"] == "1", key="professional_approved")
        with role_b:
            st.subheader("Model")
            model_title = st.text_input(ui("Название RU"), value=settings["model_title"], key="model_title_ru")
            model_title_ro = st.text_input("Denumire RO", value=settings["model_title_ro"])
            model_desc = st.text_area(ui("Описание RU"), value=settings["model_desc"])
            model_desc_ro = st.text_area("Descriere RO", value=settings["model_desc_ro"])
            model_published = st.checkbox(ui("Страница опубликована"), value=settings["model_published"] == "1", key="model_published")
            model_indexed = st.checkbox(ui("Индексация включена"), value=settings["model_indexed"] == "1", key="model_indexed")
            model_approved = st.checkbox(ui("Обе версии страницы проверены"), value=settings["model_translation_approved"] == "1", key="model_approved")
        submitted = st.form_submit_button(ui("Сохранить профиль"), type="primary", width="stretch")
    if submitted:
        errors = []
        if not name.strip():
            errors.append("Укажите публичное имя.")
        if not slug.strip() or not all(char.isalnum() or char in "-_" for char in slug):
            errors.append("Уникальный адрес может содержать буквы, цифры, дефис и подчёркивание.")
        if profile_published and not pilot_notice and not (
            settings.get("avatar_url") and bio_ru.strip()
            and bio_ro.strip() and bio_approved
        ):
            errors.append("Для публикации «Моей Сцены» нужны главное фото, тексты RU/RO и подтверждение перевода.")
        if professional_published and not (
            beauty_title.strip() and beauty_title_ro.strip()
            and beauty_desc.strip() and beauty_desc_ro.strip()
            and professional_approved
        ):
            errors.append("Для профессиональной страницы заполните и подтвердите версии RU/RO.")
        if model_published and not (
            model_title.strip() and model_title_ro.strip()
            and model_desc.strip() and model_desc_ro.strip()
            and model_approved
        ):
            errors.append("Для Model заполните и подтвердите версии RU/RO.")
        if errors:
            for error in errors:
                st.error(error)
        else:
            save_settings(DB_PATH, {
                "master_name": name, "profile_slug": slug, "location": location,
                "currency": currency or "MDL", "instagram_url": instagram,
                "telegram_url": telegram, "pilot_notice": "1" if pilot_notice else "0",
                "profile_published": "1" if profile_published else "0",
                "profile_indexed": "1" if profile_indexed else "0",
                "professional_in_scene": "1" if professional_in_scene else "0",
                "model_in_scene": "1" if model_in_scene else "0",
                "bio": bio_ru, "bio_ro": bio_ro,
                "bio_translation_approved": "1" if bio_approved else "0",
                "beauty_title": beauty_title, "beauty_title_ro": beauty_title_ro,
                "beauty_desc": beauty_desc, "beauty_desc_ro": beauty_desc_ro,
                "professional_published": "1" if professional_published else "0",
                "professional_indexed": "1" if professional_indexed else "0",
                "professional_translation_approved": "1" if professional_approved else "0",
                "model_title": model_title, "model_title_ro": model_title_ro,
                "model_desc": model_desc, "model_desc_ro": model_desc_ro,
                "model_published": "1" if model_published else "0",
                "model_indexed": "1" if model_indexed else "0",
                "model_translation_approved": "1" if model_approved else "0",
            })
            rerun_admin_with_success("Профиль сохранён.")

    st.subheader(ui("Фотографии"))
    slots = [
        ("avatar", "avatar_url", "Главное фото"),
        ("beauty_1", "beauty_image_1", "Профессиональная работа 1"),
        ("beauty_2", "beauty_image_2", "Профессиональная работа 2"),
        ("beauty_3", "beauty_image_3", "Профессиональная работа 3"),
        ("model_1", "model_image_1", "Модельная работа 1"),
        ("model_2", "model_image_2", "Модельная работа 2"),
        ("model_3", "model_image_3", "Модельная работа 3"),
    ]
    with st.form("media_form"):
        uploads = {slot: st.file_uploader(label, type=["jpg", "jpeg", "png", "webp"], key=f"upload_{slot}") for slot, _, label in slots}
        upload_submit = st.form_submit_button(ui("Сохранить выбранные фотографии"), type="primary")
    if upload_submit:
        selections = [(slot, setting_key, uploads[slot]) for slot, setting_key, _ in slots if uploads[slot] is not None]
        if not selections:
            st.warning(ui("Выберите хотя бы одну фотографию."))
        else:
            try:
                count = save_uploaded_images(selections)
            except (OSError, ValueError) as exc:
                st.error(ui(str(exc)))
            else:
                rerun_admin_with_success(f"Сохранено фотографий: {count}.")


def render_media_slots(
    settings: dict[str, str],
    slots: list[tuple[str, str, str]],
    *,
    form_key: str,
) -> None:
    preview_columns = st.columns(min(len(slots), 3))
    for index, (_, setting_key, label) in enumerate(slots):
        with preview_columns[index % len(preview_columns)]:
            source = image_source(settings.get(setting_key, ""))
            if source:
                st.image(source, width="stretch", caption=ui(label))
            else:
                st.caption(f"{ui(label)}{ui(': используется фирменное изображение SCENA')}")
    with st.form(form_key):
        uploads = {
            slot: st.file_uploader(
                ui(label), type=["jpg", "jpeg", "png", "webp"],
                key=f"{form_key}_{slot}",
            )
            for slot, _, label in slots
        }
        submitted = st.form_submit_button(
            ui("Сохранить выбранные фотографии"), type="primary"
        )
    if not submitted:
        return
    selections = [
        (slot, setting_key, uploads[slot])
        for slot, setting_key, _ in slots
        if uploads[slot] is not None
    ]
    if not selections:
        st.warning(ui("Выберите хотя бы одну фотографию."))
        return
    try:
        count = save_uploaded_images(selections)
    except (OSError, ValueError) as exc:
        st.error(ui(str(exc)))
        return
    rerun_admin_with_success(f"Сохранено фотографий: {count}.")


def render_scene_admin(settings: dict[str, str]) -> None:
    st.markdown(
        ui('<div class="scena-note">Сначала заполните имя, короткую историю и главное фото. Вид страницы можно проверить по кнопке «Открыть Мою Сцену».</div>'),
        unsafe_allow_html=True,
    )
    with st.form("scene_settings_v13"):
        identity, visibility = st.columns([1.35, 1])
        with identity:
            st.subheader(ui("Основное"))
            name = st.text_input(ui("Имя и фамилия · RU"), value=localized_name(settings, "ru"))
            name_ro = st.text_input("Nume · RO", value=localized_name(settings, "ro"))
            name_en = st.text_input("Name · EN", value=localized_name(settings, "en"))
            slug = settings["profile_slug"]
            with st.expander(ui("Идентификатор страницы")):
                st.code(slug)
                st.caption(ui("Это короткое имя для переноса страницы на платформу. Рабочие ссылки и QR-коды находятся в разделе «Продвижение → QR-коды»."))
            location = st.text_input(ui("Город"), value=settings["location"])
            instagram = st.text_input("Instagram", value=settings["instagram_url"])
            telegram = st.text_input("Telegram", value=settings["telegram_url"])
        with visibility, st.container(key="scena_visibility", border=True):
            st.subheader(ui("Что показывать"))
            profile_published = st.toggle(
                ui("Моя Сцена опубликована"), value=settings["profile_published"] == "1"
            )
            profile_indexed = st.toggle(
                ui("Разрешить поиск в интернете"), value=settings["profile_indexed"] == "1"
            )
            professional_in_scene = st.toggle(
                ui("Professional в навигации и на Сцене"), value=settings["professional_in_scene"] == "1"
            )
            model_in_scene = st.toggle(
                ui("Model в навигации и на Сцене"), value=settings["model_in_scene"] == "1"
            )
            pilot_notice = False
        st.subheader(ui("Моя история"))
        bio_ru = st.text_area(ui("Текст RU"), value=settings["bio"], height=100)
        bio_ro = st.text_area("Text RO", value=settings["bio_ro"], height=100)
        bio_en = st.text_area("Story · EN", value=settings.get("bio_en", ""), height=100)
        st.subheader(ui("Кнопка записи"))
        cta_ru = st.text_input(ui("Текст кнопки · RU"), value=content_text(settings, "booking_cta", "ru", "Записаться на макияж"))
        cta_ro = st.text_input("Text buton · RO", value=content_text(settings, "booking_cta", "ro", "Programare la machiaj"))
        cta_en = st.text_input("Button text · EN", value=content_text(settings, "booking_cta", "en", "Book makeup"))
        bio_approved = st.toggle(
            ui("Языковые версии проверены"),
            value=settings["bio_translation_approved"] == "1",
        )
        submitted = st.form_submit_button(
            ui("Сохранить Мою Сцену"), type="primary", width="stretch"
        )
    if submitted:
        errors: list[str] = []
        if not name.strip():
            errors.append("Укажите публичное имя.")
        if not slug.strip() or not all(char.isalnum() or char in "-_" for char in slug):
            errors.append("Адрес может содержать буквы, цифры, дефис и подчёркивание.")
        if profile_published and not (bio_ru.strip() and bio_ro.strip() and bio_approved):
            errors.append("Для публикации заполните и подтвердите текст RU/RO.")
        if errors:
            for error in errors:
                st.error(error)
        else:
            save_settings(DB_PATH, {
                "master_name": name, "master_name_ru": name, "master_name_ro": name_ro, "master_name_en": name_en, "profile_slug": slug, "location": location,
                "instagram_url": instagram, "telegram_url": telegram,
                "profile_published": "1" if profile_published else "0",
                "profile_indexed": "1" if profile_indexed else "0",
                "professional_in_scene": "1" if professional_in_scene else "0",
                "model_in_scene": "1" if model_in_scene else "0",
                "pilot_notice": "1" if pilot_notice else "0",
                "bio": bio_ru, "bio_ro": bio_ro, "bio_en": bio_en,
                "booking_cta_ru": cta_ru, "booking_cta_ro": cta_ro, "booking_cta_en": cta_en,
                "bio_translation_approved": "1" if bio_approved else "0",
            })
            rerun_admin_with_success("Моя Сцена сохранена.")
    st.subheader(ui("Главное фото"))
    render_media_slots(
        settings,
        [("avatar", "avatar_url", "Главное фото")],
        form_key="scene_media_v13",
    )
    st.link_button(
        ui("Открыть Мою Сцену"), page_url("scene", "ru"), width="stretch"
    )


def render_professional_admin(settings: dict[str, str]) -> None:
    st.markdown(
        ui('<div class="scena-note">Здесь настраивается только профессиональная страница. Сами группы и цены находятся в разделе «Работа → Услуги».</div>'),
        unsafe_allow_html=True,
    )
    with st.form("professional_settings_v13"):
        left, right = st.columns([1.45, 1])
        with left:
            title_ru = st.text_input(ui("Название RU"), value=settings["beauty_title"])
            title_ro = st.text_input("Denumire RO", value=settings["beauty_title_ro"])
            title_en = st.text_input("Title · EN", value=settings.get("beauty_title_en", ""))
            description_ru = st.text_area(ui("Описание RU"), value=settings["beauty_desc"])
            description_ro = st.text_area("Descriere RO", value=settings["beauty_desc_ro"])
            description_en = st.text_area("Description · EN", value=settings.get("beauty_desc_en", ""))
        with right:
            currency = st.text_input(ui("Валюта"), value=settings["currency"], max_chars=8)
            published = st.checkbox(
                ui("Страница опубликована"), value=settings["professional_published"] == "1"
            )
            indexed = st.checkbox(
                ui("Разрешить поиск в интернете"), value=settings["professional_indexed"] == "1"
            )
            approved = st.checkbox(
                ui("Языковые версии проверены"),
                value=settings["professional_translation_approved"] == "1",
            )
        submitted = st.form_submit_button(
            ui("Сохранить Professional"), type="primary", width="stretch"
        )
    if submitted:
        if published and not (
            title_ru.strip() and title_ro.strip() and description_ru.strip()
            and description_ro.strip() and approved
        ):
            st.error(ui("Для публикации заполните и подтвердите версии RU/RO."))
        else:
            save_settings(DB_PATH, {
                "beauty_title": title_ru, "beauty_title_ro": title_ro,
                "beauty_desc": description_ru, "beauty_desc_ro": description_ro,
                "beauty_title_en": title_en, "beauty_desc_en": description_en,
                "currency": currency or "MDL",
                "professional_published": "1" if published else "0",
                "professional_indexed": "1" if indexed else "0",
                "professional_translation_approved": "1" if approved else "0",
            })
            rerun_admin_with_success("Профессиональная страница сохранена.")
    with st.expander(ui("Баннер страницы записи")):
        with st.form("booking_cover_v17"):
            cover = {}
            for lang in ("ru", "ro", "en"):
                cover[f"booking_title_{lang}"] = st.text_input(ui("Заголовок")+" · "+lang.upper(), value=settings.get(f"booking_title_{lang}", ""), key="booking_title_edit_"+lang)
                cover[f"booking_description_{lang}"] = st.text_area(ui("Описание")+" · "+lang.upper(), value=settings.get(f"booking_description_{lang}", ""), key="booking_description_edit_"+lang, height=100)
            cover_saved = st.form_submit_button(ui("Сохранить баннер"),type="primary")
        if cover_saved:
            save_settings(DB_PATH,cover)
            rerun_admin_with_success(ui("Баннер сохранён."))
    st.caption(ui("Обложки используют ваши фотографии автоматически. Название и описание каждого курса редактируются в «Работа → Услуги»."))
    st.subheader(ui("Портфолио"))
    from scena_portfolio import render_portfolio_editor
    render_portfolio_editor(DB_PATH, APP_DIR, settings, "Professional")
    st.link_button(
        ui("Открыть Professional"), page_url("professional", "ru"), width="stretch"
    )


def render_model_admin(settings: dict[str, str]) -> None:
    with st.expander(ui("Сценарий, оформление и история Model")):
        from scena_model_builder import render_model_builder
        render_model_builder(DB_PATH, settings, APP_DIR, detected_locale(settings))
    from scena_model_intro import render_intro_editor
    render_intro_editor(DB_PATH, APP_DIR, settings)
    st.markdown("<div class='scena-section'></div>", unsafe_allow_html=True)
    st.subheader(ui("Образы и настройки Model"))
    with st.form("model_settings_v13"):
        left, right = st.columns([1.45, 1])
        with left:
            title_ru = st.text_input(ui("Название RU"), value=settings["model_title"])
            title_ro = st.text_input("Denumire RO", value=settings["model_title_ro"])
            title_en = st.text_input("Title · EN", value=settings.get("model_title_en", ""))
            description_ru = st.text_area(ui("Описание RU"), value=settings["model_desc"])
            description_ro = st.text_area("Descriere RO", value=settings["model_desc_ro"])
            description_en = st.text_area("Description · EN", value=settings.get("model_desc_en", ""))
        with right:
            published = st.checkbox(
                ui("Страница опубликована"), value=settings["model_published"] == "1"
            )
            indexed = st.checkbox(
                ui("Разрешить поиск в интернете"), value=settings["model_indexed"] == "1"
            )
            approved = st.checkbox(
                ui("Языковые версии проверены"),
                value=settings["model_translation_approved"] == "1",
            )
        submitted = st.form_submit_button(
            ui("Сохранить настройки Model"), type="primary", width="stretch"
        )
    if submitted:
        if published and not (
            title_ru.strip() and title_ro.strip() and description_ru.strip()
            and description_ro.strip() and approved
        ):
            st.error(ui("Для публикации заполните и подтвердите версии RU/RO."))
        else:
            save_settings(DB_PATH, {
                "model_title": title_ru, "model_title_ro": title_ro,
                "model_desc": description_ru, "model_desc_ro": description_ro,
                "model_title_en": title_en, "model_desc_en": description_en,
                "model_published": "1" if published else "0",
                "model_indexed": "1" if indexed else "0",
                "model_translation_approved": "1" if approved else "0",
            })
            rerun_admin_with_success("Настройки Model сохранены.")
    st.markdown("<div class='scena-section'></div>", unsafe_allow_html=True)
    render_model_slider_admin(settings)
    st.subheader(ui("Портфолио Model"))
    from scena_portfolio import render_portfolio_editor
    render_portfolio_editor(DB_PATH, APP_DIR, settings, "Model")



def _admin_int(settings: dict[str, str], key: str, default: int) -> int:
    try:
        return int(settings.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def render_model_slider_admin(settings: dict[str, str]) -> None:
    st.write(
        ui("Здесь модель управляет пятью образами, которые открываются после знакомства. "
        "Каждый кадр получает отдельный личный посыл на RU и RO.")
    )
    st.info(
        ui("Кадр публикуется только после включения видимости, заполнения обеих "
        "языковых версий и отметки «Языковые версии проверены». Остальное сохраняется как черновик.")
    )
    uploads: dict[int, object] = {}
    values: dict[str, object] = {}
    with st.form("model_slider_form"):
        top_left, top_middle, top_right = st.columns(3)
        with top_left:
            values["model_slider_enabled"] = st.checkbox(
                ui("Использовать сценический лендинг"),
                value=settings.get("model_slider_enabled", "1") == "1",
            )
        with top_middle:
            values["model_slider_autoplay"] = st.checkbox(
                ui("Автоматически менять кадры"),
                value=settings.get("model_slider_autoplay", "1") == "1",
            )
        with top_right:
            current_first = min(max(_admin_int(settings, "model_slider_first", 1), 1), 5)
            values["model_slider_first"] = st.selectbox(
                ui("Первый кадр"),
                range(1, 6),
                index=current_first - 1,
                format_func=lambda item: f"{ui('Кадр №')}{item}",
            )

        for slot in range(1, 6):
            prefix = f"model_slide_{slot}"
            with st.expander(f"{ui('Кадр №')}{slot}", expanded=slot == current_first):
                source = image_source(settings.get(f"{prefix}_image", ""))
                if source:
                    st.image(source, width=220)
                uploads[slot] = st.file_uploader(
                    ui("Заменить фотографию"),
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"upload_{prefix}",
                )
                state_left, state_middle, state_right = st.columns(3)
                with state_left:
                    values[f"{prefix}_visible"] = st.checkbox(
                        ui("Показывать кадр"),
                        value=settings.get(f"{prefix}_visible", "1") == "1",
                        key=f"visible_{prefix}",
                    )
                with state_middle:
                    current_order = min(max(_admin_int(settings, f"{prefix}_order", slot), 1), 5)
                    values[f"{prefix}_order"] = st.selectbox(
                        ui("Порядок"),
                        range(1, 6),
                        index=current_order - 1,
                        key=f"order_{prefix}",
                    )
                with state_right:
                    values[f"{prefix}_duration_seconds"] = st.number_input(
                        ui("Показ, секунд"),
                        min_value=3,
                        max_value=30,
                        value=min(max(_admin_int(settings, f"{prefix}_duration_seconds", 7), 3), 30),
                        key=f"duration_{prefix}",
                    )
                values[f"{prefix}_manifesto_ru"] = st.text_area(
                    ui("Личный посыл / подпись RU"),
                    value=settings.get(f"{prefix}_manifesto_ru", ""),
                    height=82,
                    key=f"manifesto_ru_{prefix}",
                )
                values[f"{prefix}_manifesto_ro"] = st.text_area(
                    "Mesaj personal / text RO",
                    value=settings.get(f"{prefix}_manifesto_ro", ""),
                    height=82,
                    key=f"manifesto_ro_{prefix}",
                )
                values[f"{prefix}_manifesto_en"] = st.text_area("Personal message · EN", value=settings.get(f"{prefix}_manifesto_en", ""), height=82, key=f"manifesto_en_{prefix}")
                with st.expander(ui("Описание изображения и кадрирование")):
                    values[f"{prefix}_alt_en"] = st.text_input("Image description · EN", value=settings.get(f"{prefix}_alt_en", ""), key=f"alt_en_{prefix}")
                    values[f"{prefix}_alt_ru"] = st.text_input(
                        ui("Описание для доступности RU"),
                        value=settings.get(f"{prefix}_alt_ru", ""),
                        key=f"alt_ru_{prefix}",
                    )
                    values[f"{prefix}_alt_ro"] = st.text_input(
                        "Descriere pentru accesibilitate RO",
                        value=settings.get(f"{prefix}_alt_ro", ""),
                        key=f"alt_ro_{prefix}",
                    )
                    crop_desktop, crop_mobile = st.columns(2)
                    with crop_desktop:
                        st.caption(ui("Фокус на компьютере"))
                        values[f"{prefix}_desktop_x"] = st.slider(
                            ui("По горизонтали, %"), 0, 100,
                            min(max(_admin_int(settings, f"{prefix}_desktop_x", 50), 0), 100),
                            key=f"desktop_x_{prefix}",
                        )
                        values[f"{prefix}_desktop_y"] = st.slider(
                            ui("По вертикали, %"), 0, 100,
                            min(max(_admin_int(settings, f"{prefix}_desktop_y", 50), 0), 100),
                            key=f"desktop_y_{prefix}",
                        )
                    with crop_mobile:
                        st.caption(ui("Фокус на телефоне"))
                        values[f"{prefix}_mobile_x"] = st.slider(
                            ui("По горизонтали, %"), 0, 100,
                            min(max(_admin_int(settings, f"{prefix}_mobile_x", 50), 0), 100),
                            key=f"mobile_x_{prefix}",
                        )
                        values[f"{prefix}_mobile_y"] = st.slider(
                            ui("По вертикали, %"), 0, 100,
                            min(max(_admin_int(settings, f"{prefix}_mobile_y", 50), 0), 100),
                            key=f"mobile_y_{prefix}",
                        )
                values[f"{prefix}_translations_approved"] = st.checkbox(
                    ui("Языковые версии проверены"),
                    value=settings.get(f"{prefix}_translations_approved", "1") == "1",
                    key=f"approved_{prefix}",
                )
        submitted = st.form_submit_button(
            ui("Сохранить Model-лендинг"), type="primary", width="stretch"
        )

    if not submitted:
        return

    errors: list[str] = []
    orders = [int(values[f"model_slide_{slot}_order"]) for slot in range(1, 6)]
    if len(set(orders)) != 5:
        errors.append("У каждого кадра должен быть уникальный номер порядка от 1 до 5.")
    first_slot = int(values["model_slider_first"])
    for slot in range(1, 6):
        prefix = f"model_slide_{slot}"
        approved = bool(values[f"{prefix}_translations_approved"])
        if approved:
            required_text = (
                values[f"{prefix}_manifesto_ru"],
                values[f"{prefix}_manifesto_ro"],
                values[f"{prefix}_alt_ru"],
                values[f"{prefix}_alt_ro"],
            )
            has_image = uploads[slot] is not None or image_source(
                settings.get(f"{prefix}_image", "")
            )
            if not has_image or not all(str(item).strip() for item in required_text):
                errors.append(
                    f"Кадр №{slot}: для подтверждения нужны фотография, посыл и описание на RU/RO."
                )
    first_prefix = f"model_slide_{first_slot}"
    if bool(values["model_slider_enabled"]) and not (
        bool(values[f"{first_prefix}_visible"])
        and bool(values[f"{first_prefix}_translations_approved"])
    ):
        errors.append("Первый кадр должен быть видимым и подтверждённым.")
    if errors:
        for error in errors:
            st.error(error)
        return

    selections = [
        (f"model_slide_{slot}", f"model_slide_{slot}_image", uploads[slot])
        for slot in range(1, 6)
        if uploads[slot] is not None
    ]
    try:
        if selections:
            save_uploaded_images(selections)
        save_settings(
            DB_PATH,
            {
                key: ("1" if value else "0")
                if isinstance(value, bool)
                else value
                for key, value in values.items()
            },
        )
    except (OSError, ValueError) as exc:
        st.error(ui(str(exc)))
        return
    rerun_admin_with_success("Model-лендинг сохранён.")


def render_qr_admin(settings: dict[str, str]) -> None:
    st.write(
        ui("Покажите QR-код клиенту или сохраните для визитки. «Запись к мастеру» сразу открывает выбор услуги и времени.")
    )
    with st.form("public_url_form"):
        base_url = st.text_input(
            ui("Публичный адрес SCENA"),
            value=settings.get("public_base_url", "http://localhost:8501"),
            help=ui("Укажите адрес, по которому ваши страницы открываются у клиентов."),
        )
        save_base_url = st.form_submit_button(ui("Сохранить адрес"), type="primary")
    if save_base_url:
        parsed = urlparse(base_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            st.error(ui("Укажите полный адрес, начинающийся с http:// или https://."))
            return
        save_settings(DB_PATH, {"public_base_url": normalize_public_base_url(base_url)})
        rerun_admin_with_success(
            "Публичный адрес сохранён; QR-коды обновлены."
        )

    locale = detected_locale(settings)
    host = urlparse(settings.get("public_base_url", "")).hostname
    if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        st.caption(tr(locale,"QR сейчас ведёт на этот компьютер. Перед передачей клиентам укажите адрес вашей Сцены, который открывается с телефона.","QR-ul duce la acest computer. Înainte de a-l oferi clienților, indicați adresa Scenei accesibilă de pe telefon.","This QR opens this computer. Before sharing it with clients, enter a Scene address that opens on their phones."))
    from scena_qr import render_qr_campaigns
    render_qr_campaigns(settings, locale, APP_DIR)
    with st.expander(tr(locale,"Ссылки и отдельные QR-коды","Linkuri și coduri QR separate","Links and separate QR codes")):
        for page, label in (("scene",tr(locale,"Моя Сцена","Scena mea","My Scene")),("professional","Professional"),("model","Model"),("booking",tr(locale,"Запись к мастеру","Programare","Booking"))):
            url = public_page_url(settings,page)
            st.write(label)
            st.code(url,language=None,wrap_lines=True)
            st.download_button(tr(locale,"Скачать QR-код","Descarcă codul QR","Download QR code"),qr_png_bytes(url),file_name=f"scena-{page}-qr.png",mime="image/png",key=f"download_{page}_qr")


def _service_admin_status(service: dict) -> tuple[str, str]:
    if service["archived"]:
        return "archived", "В архиве"
    if service["active"] and not bool(service.get("group_active", 1)):
        return "hidden", "Скрыта группой"
    if service["active"]:
        return "public", "Опубликована"
    if bool(service["translations_approved"]):
        return "hidden", "Скрыта"
    return "draft", "Черновик"


def _service_kind_explanation(kind: str) -> str:
    return {
        "appointment": "Клиент выбирает свободную дату и время.",
        "course": "Клиент оставляет предварительную заявку на обучение.",
        "inquiry": "Клиент описывает задачу, а детали согласовываются лично.",
    }[kind]


def render_services_admin(settings: dict[str, str]) -> None:
    all_groups = list_service_groups(DB_PATH, active_only=False)
    all_services = list_services(
        DB_PATH, active_only=False, include_archived=True
    )

    st.markdown(
        ui('<div class="scena-service-guide"><strong>Простой порядок:</strong> добавьте услугу, выберите готовую группу или создайте новую прямо в форме. Черновик можно сохранить сразу, а перевод заполнить перед публикацией.</div>'),
        unsafe_allow_html=True,
    )

    category = st.selectbox(
        ui("Где показывать услуги?"),
        list(SERVICE_CATEGORIES),
        format_func=lambda key: ui(SERVICE_CATEGORIES[key]),
        key="service_area_v141",
    )
    list_mode = st.radio(
        ui("Что показать?"),
        ("Текущие услуги", "Архив услуг"),
        horizontal=True,
        key="service_list_mode_v141",
        format_func=ui,
    )
    archive_mode = list_mode == "Архив услуг"
    groups = [item for item in all_groups if item["category"] == category]
    services = [
        item for item in all_services
        if item["category"] == category
        and bool(item["archived"]) == archive_mode
    ]

    title_column, action_column = st.columns([3, 1])
    with title_column:
        st.subheader(ui('Архив услуг') if archive_mode else ui('Ваши услуги'))
        st.caption(
            ui('Здесь находятся услуги, которые можно восстановить или удалить навсегда.') if archive_mode else ui('Клиент видит только услуги со статусом «Опубликована».')
        )
    with action_column:
        if not archive_mode and st.button(
            ui("Добавить услугу"),
            type="primary",
            width="stretch",
            key="open_add_service_v141",
        ):
            st.session_state["service_add_open_v141"] = not st.session_state.get(
                "service_add_open_v141", False
            )
            st.session_state.pop("service_editor_id_v141", None)
            st.session_state.pop("service_more_id_v141", None)
            st.rerun()

    if not archive_mode and st.session_state.get("service_add_open_v141"):
        st.markdown("<div class='scena-section'></div>", unsafe_allow_html=True)
        st.subheader(ui("Новая услуга"))
        st.caption(ui("Сначала достаточно названия, группы, цены и способа записи."))

        group_options: list[object] = [item["id"] for item in groups]
        if not group_options:
            group_options.append("__default__")
        group_options.append("__new__")
        group_labels = {
            item["id"]: (
                content_text(item, "name", detected_locale(settings)) + (ui(" · скрыта") if not item["active"] else "")
            )
            for item in groups
        }
        group_labels["__default__"] = ui("Основные услуги · создастся автоматически")
        group_labels["__new__"] = ui("Создать новую группу")
        group_choice = st.selectbox(
            ui("К какой группе относится услуга?"),
            group_options,
            format_func=group_labels.get,
            key=f"new_service_group_v141_{category}",
        )
        kind = st.selectbox(
            ui("Как клиент записывается?"),
            list(SERVICE_KINDS),
            format_func=lambda key: ui(SERVICE_KINDS[key]),
            key=f"new_service_kind_v141_{category}",
            help=(
                ui("Запись по времени — календарь; курс — предварительная запись; "
                "обращение — согласование без календаря.")
            ),
        )
        st.caption(ui(_service_kind_explanation(kind)))

        with st.form(f"add_service_v141_{category}"):
            if group_choice == "__new__":
                new_group_ru = st.text_input(ui("Название новой группы"))
                new_group_ro = st.text_input(
                    ui("Название группы на RO — можно заполнить позже")
                )
            else:
                new_group_ru = ""
                new_group_ro = ""

            name = st.text_input(ui("Название услуги"))
            description_ru = st.text_area(
                ui("Короткое описание для клиента — можно заполнить позже"),
                height=90,
            )
            price_column, duration_column = st.columns(2)
            with price_column:
                price = st.number_input(
                    ui("Цена, 0 = договорная"), min_value=0.0, step=100.0
                )
            with duration_column:
                duration = st.number_input(
                    ui("Продолжительность, мин."),
                    min_value=5,
                    value=60,
                    step=5,
                    disabled=kind == "inquiry",
                )
            buffer_minutes = st.number_input(
                ui("Перерыв после записи, мин."),
                min_value=0,
                value=int(settings["default_buffer_minutes"]),
                step=5,
                disabled=kind != "appointment",
            )
            with st.expander(ui("Перевод и публикация")):
                name_ro = st.text_input(ui("Название услуги на RO"))
                description_ro = st.text_area(
                    ui("Описание услуги на RO"), height=90
                )
                name_en = st.text_input("Service name · EN")
                description_en = st.text_area("Service description · EN", height=90)
                publish_now = st.checkbox(
                    ui("RU и RO проверены — сразу опубликовать")
                )
                st.caption(
                    ui("Без этой отметки услуга сохранится как черновик и не будет видна клиентам.")
                )
            submit_service = st.form_submit_button(
                ui("Сохранить услугу"), type="primary", width="stretch"
            )

        if submit_service:
            if group_choice == "__new__" and not new_group_ru.strip():
                st.error(ui("Укажите название новой группы."))
            elif not name.strip():
                st.error(ui("Укажите название услуги."))
            elif publish_now and not all(
                value.strip()
                for value in (name, name_ro, description_ru, description_ro)
            ):
                st.error(
                    ui("Для публикации заполните название и описание на RU и RO.")
                )
            else:
                try:
                    selected_group_id = None
                    if group_choice == "__new__":
                        selected_group_id = add_service_group(
                            DB_PATH,
                            category=category,
                            name_ru=new_group_ru,
                            name_ro=new_group_ro,
                        )
                    elif group_choice != "__default__":
                        selected_group_id = int(group_choice)
                    add_service(
                        DB_PATH,
                        category,
                        name,
                        price,
                        60 if kind == "inquiry" else duration,
                        kind=kind,
                        buffer_minutes=(
                            buffer_minutes if kind == "appointment" else 0
                        ),
                        name_ro=name_ro, name_en=name_en, description_en=description_en,
                        description_ru=description_ru,
                        description_ro=description_ro,
                        translations_approved=publish_now,
                        group_id=selected_group_id,
                    )
                except RequestValidationError as exc:
                    st.error(ui(str(exc)))
                else:
                    st.session_state.pop("service_add_open_v141", None)
                    rerun_admin_with_success(
                        "Услуга сохранена и опубликована."
                        if publish_now
                        else "Услуга сохранена как черновик."
                    )

        if st.button(
            ui("Закрыть без сохранения"),
            key="close_add_service_v141",
            width="stretch",
        ):
            st.session_state.pop("service_add_open_v141", None)
            st.rerun()

    if not services:
        st.info(
            ui('Архив пуст.') if archive_mode else ui('Здесь пока нет услуг. Нажмите «Добавить услугу».')
        )
    else:
        group_by_id = {item["id"]: item for item in groups}
        displayed_group_ids: list[int | None] = []
        for service in services:
            group_id = service.get("group_id")
            if group_id not in displayed_group_ids:
                displayed_group_ids.append(group_id)

        for group_id in displayed_group_ids:
            group = group_by_id.get(group_id)
            members = [
                item for item in services if item.get("group_id") == group_id
            ]
            group_name = (
                content_text(group, "name", detected_locale(settings)) if group else ui("Без группы")
            )
            st.markdown(
                f'<div class="scena-service-group-title"><strong>{clean(group_name)}</strong>' + (ui('<span>Группа скрыта от клиентов</span>') if group and (not group['active']) and (not archive_mode) else f"<span>{len(members)}{ui(' услуг</span>')}") + '</div>',
                unsafe_allow_html=True,
            )

            for service in members:
                service_id = int(service["id"])
                status_class, status_text = _service_admin_status(service)
                with st.container(border=True):
                    info_column, status_column = st.columns([4, 1])
                    with info_column:
                        st.markdown(
                            f"""<div class="scena-service-card-copy"><strong>{clean(service_name(service, detected_locale(settings)))}</strong><span>{clean(ui(SERVICE_KINDS[service['kind']]))} · {clean(format_price(service, settings['currency'], detected_locale(settings)))}""" + (f" · {int(service['duration'])}{ui(' мин.')}" if service['kind'] != 'inquiry' else '') + '</span></div>',
                            unsafe_allow_html=True,
                        )
                    with status_column:
                        st.markdown(
                            f'<span class="scena-service-status {status_class}">'
                            f'{clean(ui(status_text))}</span>',
                            unsafe_allow_html=True,
                        )

                    if archive_mode:
                        archive_actions = st.columns(2)
                        with archive_actions[0]:
                            if st.button(
                                ui("Восстановить"),
                                key=f"restore_service_v141_{service_id}",
                                width="stretch",
                            ):
                                restore_service(DB_PATH, service_id)
                                rerun_admin_with_success(
                                    "Услуга восстановлена как скрытая."
                                )
                        request_total = service_request_count(DB_PATH, service_id)
                        with archive_actions[1]:
                            if st.button(
                                ui("Удалить навсегда"),
                                key=f"ask_delete_service_v141_{service_id}",
                                width="stretch",
                                disabled=bool(request_total),
                                help=(
                                    f"{ui('Есть связанные заявки: ')}{request_total}{ui('. Для сохранения истории эту услугу нельзя удалить.')}" if request_total else ui('Удаление необратимо и потребует подтверждения.')
                                ),
                            ):
                                st.session_state["service_delete_id_v141"] = service_id
                                st.rerun()
                        if request_total:
                            st.caption(
                                f"{ui('Связанных заявок: ')}{request_total}{ui('. Услуга хранится в архиве для истории клиентов.')}"
                            )
                    else:
                        actions = st.columns(3)
                        with actions[0]:
                            if st.button(
                                ui("Изменить"),
                                key=f"edit_service_v141_{service_id}",
                                width="stretch",
                            ):
                                st.session_state["service_editor_id_v141"] = service_id
                                st.session_state.pop("service_more_id_v141", None)
                                st.rerun()
                        with actions[1]:
                            if status_class == "draft":
                                visibility_label = "Завершить"
                            elif service["active"]:
                                visibility_label = "Скрыть"
                            else:
                                visibility_label = "Опубликовать"
                            if st.button(
                                ui(visibility_label),
                                key=f"visibility_service_v141_{service_id}",
                                width="stretch",
                            ):
                                if status_class == "draft":
                                    st.session_state["service_editor_id_v141"] = service_id
                                    st.session_state.pop("service_more_id_v141", None)
                                    st.rerun()
                                else:
                                    try:
                                        set_service_active(
                                            DB_PATH,
                                            service_id,
                                            not bool(service["active"]),
                                        )
                                    except RequestValidationError as exc:
                                        st.error(ui(str(exc)))
                                    else:
                                        rerun_admin_with_success(
                                            "Услуга скрыта от клиентов."
                                            if service["active"]
                                            else "Услуга опубликована."
                                        )
                        with actions[2]:
                            if st.button(
                                ui("Ещё"),
                                key=f"more_service_v141_{service_id}",
                                width="stretch",
                            ):
                                current_more = st.session_state.get(
                                    "service_more_id_v141"
                                )
                                st.session_state["service_more_id_v141"] = (
                                    None if current_more == service_id else service_id
                                )
                                st.rerun()
                        if st.session_state.get("service_more_id_v141") == service_id:
                            st.caption(
                                ui("Архив убирает услугу из рабочего списка. Её можно восстановить.")
                            )
                            if st.button(
                                ui("Отправить в архив"),
                                key=f"archive_service_v141_{service_id}",
                                width="stretch",
                            ):
                                archive_service(DB_PATH, service_id)
                                st.session_state.pop("service_more_id_v141", None)
                                st.session_state.pop("service_editor_id_v141", None)
                                rerun_admin_with_success(
                                    "Услуга отправлена в архив."
                                )

    delete_id = st.session_state.get("service_delete_id_v141")
    delete_service_item = next(
        (
            item for item in all_services
            if int(item["id"]) == delete_id and item["archived"]
        ),
        None,
    )
    if archive_mode and delete_service_item:
        st.markdown("<div class='scena-section'></div>", unsafe_allow_html=True)
        st.subheader(ui("Подтверждение удаления"))
        st.error(
            f"«{delete_service_item['name']}{ui('» будет удалена навсегда. Восстановить её после этого невозможно.')}"
        )
        with st.form("delete_service_v141"):
            confirm_delete = st.checkbox(
                f"{ui('Да, удалить «')}{delete_service_item['name']}{ui('» навсегда')}"
            )
            delete_submit = st.form_submit_button(
                ui("Подтвердить удаление"), width="stretch"
            )
        if delete_submit:
            if not confirm_delete:
                st.error(ui("Сначала подтвердите удаление."))
            else:
                try:
                    delete_service(DB_PATH, int(delete_service_item["id"]))
                except RequestValidationError as exc:
                    st.error(ui(str(exc)))
                else:
                    st.session_state.pop("service_delete_id_v141", None)
                    rerun_admin_with_success("Услуга удалена навсегда.")
        if st.button(
            ui("Отмена"),
            key="cancel_delete_service_v141",
            width="stretch",
        ):
            st.session_state.pop("service_delete_id_v141", None)
            st.rerun()

    editor_id = st.session_state.get("service_editor_id_v141")
    current = next(
        (
            item for item in all_services
            if int(item["id"]) == editor_id
            and item["category"] == category
            and not item["archived"]
        ),
        None,
    )
    if not archive_mode and current:
        st.markdown("<div class='scena-section'></div>", unsafe_allow_html=True)
        st.subheader(f"{ui('Изменить: ')}{service_name(current, detected_locale(settings))}")
        st.caption(
            ui("Сохранение не публикует незавершённый черновик. "
            "Для публикации отдельно подтвердите RU и RO.")
        )
        compatible_groups = [
            item for item in groups if item["category"] == current["category"]
        ]
        edit_group_labels = {
            item["id"]: content_text(item, "name", detected_locale(settings)) for item in compatible_groups
        }
        edit_group_ids = list(edit_group_labels)
        current_group_id = int(current["group_id"])
        group_index = (
            edit_group_ids.index(current_group_id)
            if current_group_id in edit_group_ids
            else 0
        )
        with st.form(f"edit_service_v141_form_{int(current['id'])}"):
            edit_group_id = st.selectbox(
                ui("Группа"),
                edit_group_ids,
                index=group_index,
                format_func=edit_group_labels.get,
            )
            edit_kind = st.selectbox(
                ui("Как клиент записывается?"),
                list(SERVICE_KINDS),
                index=list(SERVICE_KINDS).index(current["kind"]),
                format_func=lambda key: ui(SERVICE_KINDS[key]),
            )
            edit_name = st.text_input(
                ui("Название услуги"), value=current["name"]
            )
            edit_description_ru = st.text_area(
                ui("Короткое описание для клиента"),
                value=current["description_ru"],
                height=90,
            )
            edit_columns = st.columns(2)
            with edit_columns[0]:
                edit_price = st.number_input(
                    ui("Цена, 0 = договорная"),
                    min_value=0.0,
                    value=float(current["price"]),
                    step=100.0,
                )
            with edit_columns[1]:
                edit_duration = st.number_input(
                    ui("Продолжительность, мин."),
                    min_value=5,
                    value=int(current["duration"]),
                    step=5,
                )
            edit_buffer = st.number_input(
                ui("Перерыв после записи, мин."),
                min_value=0,
                value=int(current["buffer_minutes"]),
                step=5,
            )
            with st.expander(ui("Перевод и публикация")):
                edit_name_ro = st.text_input(
                    ui("Название услуги на RO"), value=current["name_ro"]
                )
                edit_description_ro = st.text_area(
                    ui("Описание услуги на RO"),
                    value=current["description_ro"],
                    height=90,
                )
                edit_name_en = st.text_input("Service name · EN", value=current.get("name_en", ""))
                edit_description_en = st.text_area("Service description · EN", value=current.get("description_en", ""), height=90)
                edit_approved = st.checkbox(
                    ui("RU и RO проверены"),
                    value=bool(current["translations_approved"]),
                )
            edit_submit = st.form_submit_button(
                ui("Сохранить изменения"), type="primary", width="stretch"
            )
        if edit_submit:
            try:
                update_service(
                    DB_PATH,
                    int(current["id"]),
                    category=current["category"],
                    kind=edit_kind,
                    name=edit_name,
                    name_ro=edit_name_ro, name_en=edit_name_en, description_en=edit_description_en,
                    price=edit_price,
                    duration=edit_duration,
                    buffer_minutes=edit_buffer,
                    description_ru=edit_description_ru,
                    description_ro=edit_description_ro,
                    translations_approved=edit_approved,
                    group_id=edit_group_id,
                )
            except RequestValidationError as exc:
                st.error(ui(str(exc)))
            else:
                st.session_state.pop("service_editor_id_v141", None)
                rerun_admin_with_success("Изменения сохранены.")
        if st.button(
            ui("Закрыть редактор"),
            key="close_service_editor_v141",
            width="stretch",
        ):
            st.session_state.pop("service_editor_id_v141", None)
            st.rerun()

    if not archive_mode:
        st.markdown("<div class='scena-section'></div>", unsafe_allow_html=True)
        with st.expander(ui("Настроить группы")):
            st.caption(
                ui("Группа объединяет похожие услуги на публичной странице. "
                "Её можно переименовать или временно скрыть целиком.")
            )
            if not groups:
                st.info(
                    ui("Первая группа появится автоматически при добавлении услуги.")
                )
            else:
                group_labels = {
                    item["id"]: (
                        content_text(item, "name", detected_locale(settings))
                        + (ui(" · скрыта") if not item["active"] else "")
                    )
                    for item in groups
                }
                selected_group_id = st.selectbox(
                    ui("Выберите группу"),
                    list(group_labels),
                    format_func=group_labels.get,
                    key=f"edit_group_choice_v141_{category}",
                )
                current_group = next(
                    item for item in groups
                    if item["id"] == selected_group_id
                )
                with st.form(
                    f"edit_service_group_v141_{selected_group_id}"
                ):
                    edit_group_name_ru = st.text_input(
                        ui("Название группы"),
                        value=current_group["name_ru"],
                    )
                    edit_group_name_ro = st.text_input(
                        ui("Название группы на RO"),
                        value=current_group["name_ro"],
                    )
                    edit_group_description_ru = st.text_area(
                        ui("Пояснение для клиента — необязательно"),
                        value=current_group["description_ru"],
                        height=80,
                    )
                    edit_group_description_ro = st.text_area(
                        ui("Пояснение на RO — необязательно"),
                        value=current_group["description_ro"],
                        height=80,
                    )
                    edit_group_name_en = st.text_input("Group name · EN", value=current_group.get("name_en", ""))
                    edit_group_description_en = st.text_area("Group description · EN", value=current_group.get("description_en", ""), height=80)
                    update_group_submit = st.form_submit_button(
                        ui("Сохранить группу"), width="stretch"
                    )
                if update_group_submit:
                    try:
                        update_service_group(
                            DB_PATH,
                            selected_group_id,
                            name_ru=edit_group_name_ru,
                            name_ro=edit_group_name_ro, name_en=edit_group_name_en, description_en=edit_group_description_en,
                            description_ru=edit_group_description_ru,
                            description_ro=edit_group_description_ro,
                        )
                    except RequestValidationError as exc:
                        st.error(ui(str(exc)))
                    else:
                        rerun_admin_with_success("Группа сохранена.")
                group_action = (
                    "Скрыть группу"
                    if current_group["active"]
                    else "Показать группу"
                )
                if st.button(
                    ui(group_action),
                    key=f"toggle_group_v141_{selected_group_id}",
                    width="stretch",
                ):
                    set_service_group_active(
                        DB_PATH,
                        selected_group_id,
                        not bool(current_group["active"]),
                    )
                    rerun_admin_with_success(
                        "Группа скрыта вместе со своими услугами."
                        if current_group["active"]
                        else "Группа снова видна клиентам."
                    )


def render_schedule_admin(settings: dict[str, str]) -> None:
    weekday_labels = {0: "Понедельник", 1: "Вторник", 2: "Среда", 3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"}
    selected_days = [int(value) for value in settings["schedule_weekdays"].split(",") if value.strip().isdigit()]
    with st.form("schedule_form"):
        st.subheader(ui("Регулярный график"))
        weekdays = st.multiselect(ui('Рабочие дни'), list(weekday_labels), default=selected_days, format_func=lambda value: ui(weekday_labels[value]))
        cols = st.columns(4)
        with cols[0]:
            start = st.time_input(ui("Начало"), value=time.fromisoformat(settings["schedule_start"]))
        with cols[1]:
            end = st.time_input(ui("Конец"), value=time.fromisoformat(settings["schedule_end"]))
        with cols[2]:
            break_start = st.time_input(ui("Перерыв с"), value=time.fromisoformat(settings["schedule_break_start"]))
        with cols[3]:
            break_end = st.time_input(ui("Перерыв до"), value=time.fromisoformat(settings["schedule_break_end"]))
        params = st.columns(4)
        with params[0]:
            interval = st.number_input(ui("Шаг слотов, мин."), min_value=5, max_value=60, value=int(settings["slot_interval_minutes"]), step=5)
        with params[1]:
            lead = st.number_input(ui("Минимум до записи, ч."), min_value=0, max_value=168, value=int(settings["minimum_lead_hours"]))
        with params[2]:
            horizon = st.number_input(ui("Глубина, дней"), min_value=1, max_value=365, value=int(settings["booking_horizon_days"]))
        with params[3]:
            hold = st.number_input(ui("Удержание, ч."), min_value=1, max_value=168, value=int(settings["pending_hold_hours"]))
        schedule_submit = st.form_submit_button(ui("Сохранить график"), type="primary")
    if schedule_submit:
        if not weekdays or start >= end or break_start >= break_end or break_start <= start or break_end >= end:
            st.error(ui("Проверьте рабочие дни, начало, конец и перерыв."))
        else:
            save_settings(DB_PATH, {
                "schedule_weekdays": ",".join(str(day) for day in sorted(weekdays)),
                "schedule_start": start.strftime("%H:%M"), "schedule_end": end.strftime("%H:%M"),
                "schedule_break_start": break_start.strftime("%H:%M"), "schedule_break_end": break_end.strftime("%H:%M"),
                "slot_interval_minutes": interval, "minimum_lead_hours": lead,
                "booking_horizon_days": horizon, "pending_hold_hours": hold,
            })
            rerun_admin_with_success(
                "График сохранён; кнопки времени пересчитаны автоматически."
            )
    st.subheader(ui("Выходные и дополнительные часы"))
    with st.form("exception_form"):
        exception_date = st.date_input(ui("Дата"), min_value=date.today())
        kind = st.selectbox(ui("Режим"), ["closed", "extra"], format_func=lambda value: ui({"closed": "Закрыть весь день", "extra": "Добавить часы"}[value]))
        extra_cols = st.columns(2)
        with extra_cols[0]:
            extra_start = st.time_input(ui("Дополнительно с"), value=time(18, 0))
        with extra_cols[1]:
            extra_end = st.time_input(ui("Дополнительно до"), value=time(20, 0))
        note = st.text_input(ui("Комментарий"))
        exception_submit = st.form_submit_button(ui("Добавить исключение"))
    if exception_submit:
        try:
            add_schedule_exception(
                DB_PATH, exception_date.isoformat(), kind,
                start_time=extra_start.strftime("%H:%M") if kind == "extra" else "",
                end_time=extra_end.strftime("%H:%M") if kind == "extra" else "",
                note=note,
            )
        except RequestValidationError as exc:
            st.error(ui(str(exc)))
        else:
            rerun_admin_with_success("Исключение графика добавлено.")
    exceptions = list_schedule_exceptions(DB_PATH)
    if exceptions:
        labels = {item["id"]: f"{item['exception_date']} · {ui('выходной') if item['kind'] == 'closed' else item['start_time'] + '–' + item['end_time']}" for item in exceptions}
        delete_id = st.selectbox(ui("Удалить исключение"), list(labels), format_func=labels.get)
        if st.button(ui("Удалить выбранное исключение")):
            delete_schedule_exception(DB_PATH, delete_id)
            rerun_admin_with_success("Исключение графика удалено.")


def render_posts_admin() -> None:
    from scena_publication_ui import render_publication_workspace
    settings = get_settings(DB_PATH)
    render_publication_workspace(DB_PATH, APP_DIR, settings, detected_locale(settings))


def render_sms_admin() -> None:
    messages = list_sms_outbox(DB_PATH)
    st.caption(ui("Журнал уведомлений: статус доставки указан у каждого сообщения."))
    st.write(f"{ui('Подготовлено сообщений: **')}{len(messages)}**")
    if messages:
        display = [{
            "ID": item["id"], "Заявка": item["request_id"], "Событие": item["event"],
            "Получатель": item["recipient"], "Язык": item["locale"].upper(),
            "Статус": item["status"], "Сообщение": item["body"],
        } for item in messages]
        render_data_table(display)


def render_backup() -> None:
    from scena_transfer_ui import render_transfer_workspace
    render_transfer_workspace(DB_PATH, APP_DIR)


def render_pro_status_banner(locale: str) -> None:
    status = get_pro_status(DB_PATH)
    expiry = datetime.fromisoformat(status["expires_at"]).strftime("%d.%m.%Y")
    if status["is_active"]:
        detail = tr(locale, f"Осталось {status['days_remaining']} дней · действует до {expiry}", f"Au rămas {status['days_remaining']} zile · valabil până la {expiry}", f"Remaining: {status['days_remaining']} days · valid until {expiry}")
    else:
        detail = tr(locale, f'Период завершён {expiry} · можно подать новую заявку', f'Perioada s-a încheiat la {expiry} · puteți depune o cerere nouă', f'Period ended on {expiry} · you can submit a new application')
    st.markdown(
        f"""{ui('<div class="scena-pro-banner" role="status" aria-label="Статус подписки PRO"><div><strong>SCENA · ')}{clean(status['label'])}</strong><span>{clean(tr(locale, 'Ваши возможности и срок доступа', 'Posibilitățile și perioada de acces'))}</span></div><div class="scena-pro-days">{clean(detail)}</div></div>""",
        unsafe_allow_html=True,
    )


def _conversation_label(sender: str) -> str:
    return {
        "user": "Вы",
        "assistant": "SCENA Ассистент",
        "admin": "Команда SCENA",
        "system": "SCENA",
    }.get(sender, "SCENA")


def render_conversation_history(*, channels: set[str] | None = None) -> None:
    messages = list_support_messages(DB_PATH)
    if channels is not None:
        messages = [item for item in messages if item["channel"] in channels]
    st.subheader(ui("История общения"))
    if not messages:
        st.caption(ui("Здесь сохраняются ваши вопросы и ответы."))
        return
    blocks = []
    for item in messages:
        delivery = ""
        if item["sender"] == "user" and item["channel"] == "support":
            delivery = {
                "queued": " · сохранено, ещё не доставлено",
                "failed": " · отправка не удалась, можно повторить",
                "sent": " · доставлено команде",
            }.get(item["delivery_status"], "")
        body = item["body"]
        if item["sender"] == "system" and body == 'Вопрос сохранён, но AI-подключение платформы пока не настроено. Вы можете отправить этот вопрос команде SCENA.':
            body = 'Вопрос сохранён. Ассистент пока недоступен. Вы можете написать команде SCENA.'
        blocks.append(
            f'<div class="scena-message {clean(item["sender"])}">'
            f'<small>{clean(_conversation_label(item["sender"]))}{clean(delivery)} · '
            f'{clean(item["created_at"].replace("T", " ")[:16])}</small>'
            f'<p>{clean(body)}</p></div>'
        )
    st.markdown(
        ui('<section class="scena-conversation" aria-label="История общения">') + ''.join(blocks) + '</section>',
        unsafe_allow_html=True,
    )


def _cabinet_recommendations(settings: dict[str, str]) -> list[str]:
    recommendations = []
    if not settings.get("bio", "").strip():
        recommendations.append("Добавьте личный текст в «Мою Сцену».")
    if settings.get("bio_translation_approved") != "1":
        recommendations.append("Проверьте и подтвердите RU/RO для «Моей Сцены».")
    if settings.get("professional_translation_approved") != "1":
        recommendations.append("Завершите перевод профессиональной страницы.")
    if settings.get("model_translation_approved") != "1":
        recommendations.append("Завершите перевод страницы Model.")
    if not list_services(DB_PATH, "Professional"):
        recommendations.append("Добавьте хотя бы одну опубликованную профессиональную услугу.")
    if not recommendations:
        recommendations.append("Основные страницы заполнены. Следующий полезный шаг — проверить их на телефоне.")
    return recommendations


def _integration_status(
    configured: bool,
    channel: str,
    label: str,
    configuration_fingerprint: str,
) -> tuple[str, str]:
    if not configured:
        return "waiting", "Пока недоступен"
    health = get_integration_health(DB_PATH, channel)
    if health.get("configuration_fingerprint") != configuration_fingerprint:
        return "waiting", "Требует проверки"
    if health.get("last_check_status") == "success":
        return "connected", "Связь проверена"
    if health.get("last_check_status") == "failed":
        return "failed", "Не удалось проверить"
    return "waiting", "Требует проверки"


def render_assistant_admin(settings: dict[str, str]) -> None:
    from scena_help_ui import render_assistant
    render_assistant(DB_PATH, APP_DIR, settings, detected_locale(settings))


def render_support_admin() -> None:
    from scena_help_ui import render_support
    render_support(DB_PATH, APP_DIR, detected_locale(get_settings(DB_PATH)))


def render_pro_admin() -> None:
    from scena_pro_ui import render_pro
    settings = get_settings(DB_PATH)
    render_pro(DB_PATH, APP_DIR, settings, detected_locale(settings))


ADMIN_SECTIONS = {
    "work": "Работа",
    "pages": "Страницы",
    "help": "Помощь",
    "pro": "PRO",
    "home": "Главная",
    "promotion": "Продвижение",
    "settings": "Настройки",
}

ADMIN_VIEWS = {
    "pro": {"subscription": "Подписка PRO"},
    "help": {
        "assistant": "SCENA Ассистент",
        "support": "Команда SCENA",
        "pro": "PRO",
    },
    "pages": {
        "scene": "Моя Сцена",
        "professional": "Professional",
        "model": "Model",
        "shop": "Market",
    },
    "work": {
        "overview": "Обзор",
        "requests": "Заявки",
        "services": "Услуги",
        "schedule": "График",
    },
    "promotion": {
        "posts": "Публикации",
        "qr": "QR-коды",
        "prompts": "Промпты",
    },
    "settings": {
        "connections": "Подключения",
        "sms": "SMS",
        "backup": "Резервная копия",
    },
}

ADMIN_VIEW_COPY = {
    ("work", "overview"): ("Ваша работа сегодня", "Записи, услуги и заказы — начните с важного."),
    ("pro", "subscription"): ("SCENA PRO", "Ваш образ, ваш магазин, ваши возможности."),
    ("pages", "shop"): ("Ваш Market", "Товары, которые вы рекомендуете. Заказы от ваших клиентов."),
    ("promotion", "prompts"): ("Промпты для вашего образа", "Выберите сцену, добавьте свои детали и сохраните задание для ИИ."),
    ("settings", "connections"): ("Подключения", "Настройка ассистента и связи с командой."),
    ("home", ""): (
        "Что сделаем сегодня?",
        "Заявки, ваши страницы и идеи для продвижения — всё под рукой.",
    ),
    ("help", "assistant"): (
        "SCENA Ассистент",
        "Задайте вопрос о кабинете или получите конкретные рекомендации по заполнению страниц.",
    ),
    ("help", "support"): (
        "Команда SCENA",
        "Напишите запрос и следите за ответом в одной сохранённой переписке.",
    ),
    ("help", "pro"): (
        "Подписка PRO",
        "Срок действия, возможности PRO и история заявок на активацию.",
    ),
    ("pages", "scene"): (
        "Моя Сцена",
        "Имя, история, главное фото и ссылки на ваши направления.",
    ),
    ("pages", "professional"): (
        "Профессиональная страница",
        "Название, описание и фотографии. Цены и услуги редактируются отдельно в разделе «Работа».",
    ),
    ("pages", "model"): (
        "Страница Model",
        "Знакомство, ваши образы и личные фразы.",
    ),
    ("work", "requests"): (
        "Заявки",
        "Все обращения клиентов, статусы и детали — в одном месте.",
    ),
    ("work", "services"): (
        "Группы и услуги",
        "Объединяйте похожие услуги в группы, задавайте способ записи и управляйте публикацией.",
    ),
    ("work", "schedule"): (
        "График",
        "Рабочие дни, свободное время, перерывы и исключения.",
    ),
    ("promotion", "posts"): (
        "Публикации",
        "Истории и новости для «Моей Сцены», Professional и Model.",
    ),
    ("promotion", "qr"): (
        "QR-коды",
        "Готовые QR-коды на каждую публичную страницу — без сторонних сервисов.",
    ),
    ("settings", "sms"): (
        "SMS",
        "Подготовленные сообщения и результаты отправки.",
    ),
    ("settings", "backup"): (
        "Резервная копия",
        "Скачайте копию данных кабинета перед крупными изменениями.",
    ),
}


def render_admin_navigation(locale: str, section: str, view: str) -> None:
    section_keys = tuple(key for key in ADMIN_SECTIONS if key != "home")
    with st.container(key="scena_admin_main_nav"):
        selected_section = st.segmented_control(
            ui("Раздел кабинета"),
            section_keys,
            default=section,
            format_func=lambda key: ui(ADMIN_SECTIONS[key]),
            key=f"admin_section_navigation_{section}",
            label_visibility="collapsed",
            width="stretch",
            wrap=True,
        )
    if selected_section and selected_section != section:
        set_admin_route(locale, selected_section)
        st.rerun()
    if section in ADMIN_VIEWS:
        view_keys = tuple(ADMIN_VIEWS[section])
        with st.container(key="scena_admin_subnav"):
            selected_view = st.pills(
                ui("Подраздел"),
                view_keys,
                default=view,
                format_func=lambda key: ui(ADMIN_VIEWS[section][key]),
                key=f"admin_view_navigation_{section}_{view}",
                label_visibility="collapsed",
                width="stretch",
                wrap=True,
            )
        if selected_view and selected_view != view:
            set_admin_route(locale, section, selected_view)
            st.rerun()


def render_admin_heading(locale: str, section: str, view: str) -> None:
    if section == "home" or (section == "work" and view == "overview"):
        crumbs = ''
    else:
        section_label = ui(ADMIN_SECTIONS[section])
        view_label = ui(ADMIN_VIEWS[section][view])
        crumbs = (
            f'<strong>{clean(section_label)}</strong><span>›</span>'
            f'<strong>{clean(view_label)}</strong>'
        )
    title, lead = map(ui, ADMIN_VIEW_COPY[(section, view)])
    st.markdown(
        (f'<div class="scena-breadcrumbs">{crumbs}</div>' if crumbs else '') +
        f'<h1 class="scena-admin-title">{clean(title)}</h1>'
        f'<p class="scena-admin-lead">{clean(lead)}</p>',
        unsafe_allow_html=True,
    )


def render_admin_home(locale: str) -> None:
    from scena_workspace_ui import render_dashboard
    render_dashboard(DB_PATH, APP_DIR, get_settings(DB_PATH), locale, set_admin_route)


def render_admin(settings: dict[str, str], locale: str) -> None:
    require_admin(locale)
    render_header("admin", locale, admin=True)
    section = str(st.query_params.get("section", "work"))
    if section not in ADMIN_SECTIONS or section == "home":
        section = "work"
    views = ADMIN_VIEWS.get(section, {})
    view = str(st.query_params.get("view", ""))
    if views and view not in views:
        view = next(iter(views))
    if not views:
        view = ""

    with st.container(key="scena_admin_identity_actions"):
        _, exit_col = st.columns([5, 1])
        with exit_col:
            if st.button(ui("Выйти"), width="stretch"):
                st.session_state["scena_admin_authenticated"] = False
                st.rerun()

    legacy_success = st.session_state.pop("scena_admin_success", "")
    notice = st.session_state.pop("scena_admin_notice", None)
    if legacy_success and not notice:
        notice = ("success", legacy_success)
    if notice:
        kind, message = notice
        getattr(st, kind if kind in {"success", "warning", "error", "info"} else "info")(ui(message))

    render_admin_navigation(locale, section, view)
    render_admin_heading(locale, section, view)

    if section == "home" or (section == "work" and view == "overview"):
        render_admin_home(locale)
    elif section == "help" and view == "assistant":
        render_assistant_admin(settings)
    elif section == "help" and view == "support":
        render_support_admin()
    elif section == "pro" or (section == "help" and view == "pro"):
        render_pro_admin()
    elif section == "pages" and view == "shop":
        from scena_shop import render_shop_admin
        render_shop_admin(DB_PATH, APP_DIR, settings, locale)
    elif section == "promotion" and view == "prompts":
        from scena_prompts import render_prompts
        render_prompts(DB_PATH, APP_DIR, settings, locale)
    elif section == "settings" and view == "connections":
        from scena_connect_setup import render_connections
        render_connections(DB_PATH, APP_DIR, locale)
    elif section == "pages" and view == "scene":
        render_scene_admin(settings)
    elif section == "pages" and view == "professional":
        render_professional_admin(settings)
    elif section == "pages" and view == "model":
        render_model_admin(settings)
    elif section == "work" and view == "requests":
        render_crm()
    elif section == "work" and view == "services":
        render_services_admin(settings)
    elif section == "work" and view == "schedule":
        render_schedule_admin(settings)
    elif section == "promotion" and view == "posts":
        render_posts_admin()
    elif section == "promotion" and view == "qr":
        render_qr_admin(settings)
    elif section == "settings" and view == "sms":
        render_sms_admin()
    elif section == "settings" and view == "backup":
        render_backup()
    render_pro_status_banner(locale)


def run() -> None:
    global DB_PATH
    DB_PATH = Path(os.environ.get("SCENA_DB_PATH", APP_DIR / "scena_master.db"))
    st.set_page_config(
        page_title="SCENA — Моя Сцена", page_icon="✦", layout="wide",
        initial_sidebar_state="collapsed",
    )
    init_db(DB_PATH)
    expire_pending_requests(DB_PATH)
    apply_styles()
    apply_editorial_styles()
    settings = get_settings(DB_PATH)
    locale = detected_locale(settings)
    st.session_state["scena_ui_locale"] = locale
    from scena_workspace_ui import apply_workspace_styles
    apply_workspace_styles(APP_DIR, settings)
    page = str(st.query_params.get("page", "scene"))
    if str(st.query_params.get("admin", "")) == "1":
        page = "admin"
    allowed_pages = {
        "scene", "portfolio", "professional", "model", "booking",
        "course", "join-model", "invite-model", "admin", "post", "posts", "shop",
    }
    if page not in allowed_pages:
        page = "scene"
    if page == "admin":
        render_admin(settings, locale)
        return
    if page == "model":
        render_model(settings, locale)
        return
    render_header(page, locale)
    if page == "scene":
        render_scene(settings, locale)
    elif page == "shop":
        from scena_shop import render_shop
        render_shop(DB_PATH, APP_DIR, settings, locale)
    elif page == "portfolio":
        render_portfolio_page(settings, locale)
    elif page == "professional":
        render_professional(settings, locale)
    elif page == "booking":
        render_booking(settings, locale)
    elif page == "course":
        render_course(settings, locale)
    elif page == "join-model":
        render_join_model(locale)
    elif page == "invite-model":
        render_invite_model(settings, locale)
    elif page == "post":
        from scena_publication_ui import render_post_page
        render_post_page(DB_PATH, APP_DIR, settings, locale, st.query_params.get('post', ''))
    elif page == "posts":
        from scena_publication_ui import render_feed
        render_feed(DB_PATH, APP_DIR, settings, locale, st.query_params.get('destination', 'scene'), all_posts=True)
    render_footer(locale)
