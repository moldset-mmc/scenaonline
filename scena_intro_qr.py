"""Independent destination and image-relative placement for the introduction QR."""
from __future__ import annotations

import base64
import html
import json
import math
import os
import sqlite3
from functools import lru_cache
from pathlib import Path

DEFAULT_QR_SETTINGS = {
    'model_intro_qr_destination': 'model',
    'model_intro_qr_x': '',
    'model_intro_qr_y': '',
    'model_intro_qr_size': '',
}
DESTINATIONS = (
    ('model', 'Model', 'Model', 'Model'),
    ('professional', 'Мастер · Professional', 'Specialist · Professional', 'Specialist · Professional'),
    ('booking', 'Запись на услуги', 'Programare la servicii', 'Book a service'),
    ('scene', 'Моя Сцена', 'Scena mea', 'My Scene'),
    ('shop', 'shopping', 'shopping', 'shopping'),
    ('course', 'Курс', 'Curs', 'Course'),
    ('portfolio-model', 'Портфолио Model', 'Portofoliu Model', 'Model portfolio'),
    ('portfolio-professional', 'Портфолио мастера', 'Portofoliul specialistului', 'Professional portfolio'),
)


@lru_cache(maxsize=64)
def _qr_uri(address):
    from scena_qr import qr_png_bytes
    return 'data:image/png;base64,' + base64.b64encode(qr_png_bytes(address)).decode('ascii')


def qr_config(settings):
    """Known starter portraits supply defaults only; every photo supports editing."""
    from scena_qr import QR_SURFACES
    surfaces = {'media/qr-scenes/' + page + '.png': value for page, value in QR_SURFACES.items()}
    x, y, size = surfaces.get(settings.get('model_intro_image'), QR_SURFACES['model'])
    defaults = {'x': (x + size / 2) / 1024 * 100, 'y': (y + size / 2) / 1536 * 100, 'size': size / 1024 * 100}
    result = {}
    for field, default in defaults.items():
        try:
            value = float(settings.get('model_intro_qr_' + field, ''))
        except (TypeError, ValueError):
            value = default
        low, high = (5, 60) if field == 'size' else (0, 100)
        result[field] = min(high, max(low, value)) if math.isfinite(value) else default
    return result


def qr_destination(settings, locale):
    from model_landing import public_page_url
    from scena_i18n import tr
    key = settings.get('model_intro_qr_destination', 'model')
    row = next((row for row in DESTINATIONS if row[0] == key), DESTINATIONS[0])
    page, _, view = row[0].partition('-')
    return public_page_url(settings, page, locale=locale, **({'view': view} if view else {})), tr(locale, *row[1:])


def validate_qr(values):
    if values.get('model_intro_qr_destination', 'model') not in {row[0] for row in DESTINATIONS}:
        raise ValueError('Выберите страницу для QR-кода.')
    for field in ('x', 'y', 'size'):
        raw = values.get('model_intro_qr_' + field, '')
        if raw == '':
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError('Проверьте положение и размер QR-кода.') from exc
        low, high = (5, 60) if field == 'size' else (0, 100)
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Проверьте положение и размер QR-кода.')


def save_qr(db_path, values, *, expected):
    from scena_core import get_settings
    from scena_database import connect
    updates = {key: str(values.get(key, default)).strip() for key, default in DEFAULT_QR_SETTINGS.items()}
    validate_qr(updates)
    with connect(db_path, timeout=15) as connection:
        connection.execute('BEGIN IMMEDIATE')
        actual = dict(connection.execute('SELECT key,value FROM profile_settings'))
        # Coordinates must refer to the photo the owner actually adjusted.
        for key, default in {**DEFAULT_QR_SETTINGS, 'model_intro_image': ''}.items():
            if actual.get(key, default) != expected.get(key, default):
                raise ValueError('Фотография или QR-код уже изменены. Обновите редактор QR-кода.')
        connection.executemany('INSERT INTO profile_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', updates.items())
    return get_settings(db_path)


def qr_button(settings, locale, *, dialog_id='qr-dialog'):
    from scena_i18n import tr
    address, label = qr_destination(settings, locale)
    code = _qr_uri(address)
    config = qr_config(settings)
    attrs = ' '.join(f'data-qr-{key}="{value:.8f}"' for key, value in config.items())
    show = tr(locale, 'Увеличить QR-код', 'Mărește codul QR', 'Enlarge QR code')
    button = f'<button class="cube-qr" type="button" {attrs} data-qr-open="{dialog_id}" data-qr-show="{html.escape(show, quote=True)}" aria-haspopup="dialog" aria-label="{html.escape(show + ': ' + label, quote=True)}"><img src="{code}" alt="QR — {html.escape(label, quote=True)}"></button>'
    close = tr(locale, 'Закрыть', 'Închide', 'Close')
    open_label = tr(locale, 'Открыть страницу', 'Deschide pagina', 'Open page')
    download = tr(locale, 'Скачать QR PNG', 'Descarcă QR PNG', 'Download QR PNG')
    dialog = f'<dialog class="qr-dialog" id="{dialog_id}" aria-label="QR — {html.escape(label, quote=True)}"><button type="button" data-qr-close aria-label="{close}">×</button><img src="{code}" alt="QR — {html.escape(label, quote=True)}"><p data-qr-title>{html.escape(label)}</p><a data-qr-link href="{html.escape(address, quote=True)}" target="_blank" rel="noopener">{open_label}</a><a data-qr-download download="SCENA-QR.png" href="{code}">{download}</a></dialog>'
    return button, dialog


def render_qr_editor(db_path, app_dir, settings, locale):
    from scena_ui import st
    from scena_i18n import tr
    from model_landing import image_uri
    def t(ru, ro, en):
        return tr(locale, ru, ro, en)
    state_key = 'scena_intro_qr_editor'
    source = st.session_state.setdefault(state_key, {key: settings.get(key, default) for key, default in {**DEFAULT_QR_SETTINGS, 'model_intro_image': ''}.items()})
    revision = st.session_state.get(state_key + '_revision', 0)
    if notice := st.session_state.pop(state_key + '_notice', None):
        st.success(t('QR-код сохранён.', 'Codul QR a fost salvat.', 'QR code saved.'))
    with st.expander(t('QR-код · ссылка и положение', 'Cod QR · destinație și poziție', 'QR code · destination and position'), expanded=True):
        with st.form(state_key + '_' + str(revision)):
            with st.container(key='intro_qr_editor'):
                labels = {row[0]: t(*row[1:]) for row in DESTINATIONS}
                choices = list(labels)
                source_key = source['model_intro_qr_destination']
                values = {}
                with st.container(key='intro_qr_destination'):
                    values['model_intro_qr_destination'] = st.selectbox(t('Куда ведёт QR-код', 'Destinația codului QR', 'QR code destination'), choices, index=choices.index(source_key) if source_key in choices else 0, format_func=labels.get)
                st.caption(t('Ссылка меняется отдельно от фотографии. Нажмите QR-код, чтобы увеличить и проверить переход.', 'Destinația se schimbă independent de fotografie. Apasă codul QR pentru a-l mări și a verifica linkul.', 'The destination changes independently of the photo. Tap the QR code to enlarge it and check the link.'))
                preview_settings = {**settings, **source, **values}
                photo = image_uri(Path(app_dir), source['model_intro_image'])
                if photo:
                    button, dialog = qr_button(preview_settings, locale, dialog_id='intro-qr-preview-dialog')
                    options = []
                    for choice in choices:
                        url, label = qr_destination({**settings, 'model_intro_qr_destination': choice}, locale)
                        code = _qr_uri(url)
                        options.append({'url': url, 'label': label, 'code': code})
                    data = html.escape(json.dumps(options, ensure_ascii=False), quote=True)
                    markup = f'<div class="qr-editor-preview" data-qr-photo data-qr-options="{data}"><img class="qr-portrait" src="{html.escape(photo, quote=True)}" alt="{t("Положение QR на фотографии", "Poziția QR pe fotografie", "QR position on the photo")}">{button}</div>{dialog}'
                    if os.environ.get('SCENA_NATIVE_WEB') == '1':
                        st.markdown(markup, unsafe_allow_html=True)
                    else:
                        assets = Path(__file__).parent / 'scena_web/static'
                        st.iframe('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>' + (assets/'intro-qr.css').read_text() + '</style><body>' + markup + '<script>' + (assets/'intro-qr.js').read_text() + '</script></body>', height=430)
                with st.expander(t('Совместить QR с квадратом на фото', 'Aliniază QR cu pătratul din fotografie', 'Align QR with the square in the photo')):
                    st.caption(t('Нажмите в центр квадрата на фотографии. Размер можно изменить ниже. Настройка действует на телефоне и компьютере.', 'Apasă centrul pătratului din fotografie. Ajustează dimensiunea mai jos. Poziția se aplică pe telefon și computer.', 'Tap the centre of the square in the photo. Adjust the size below. Placement applies on phone and computer.'))
                    config = qr_config(source)
                    for field, label in [('x', t('Центр по горизонтали, %', 'Centru pe orizontală, %', 'Horizontal centre, %')), ('y', t('Центр по вертикали, %', 'Centru pe verticală, %', 'Vertical centre, %')), ('size', t('Размер QR, % от короткой стороны фото', 'Dimensiune QR, % din latura scurtă a fotografiei', 'QR size, % of the short photo edge'))]:
                        with st.container(key='intro_qr_' + field):
                            low, high = (5.0, 60.0) if field == 'size' else (0.0, 100.0)
                            values['model_intro_qr_' + field] = str(st.number_input(label, min_value=low, max_value=high, value=round(config[field], 2), step=0.01))
                submitted = st.form_submit_button(t('Сохранить QR-код', 'Salvează codul QR', 'Save QR code'), type='primary', width='stretch')
        if submitted:
            try:
                saved = save_qr(db_path, values, expected=source)
            except (ValueError, OSError, sqlite3.Error) as exc:
                if isinstance(exc, ValueError):
                    st.error(t(str(exc), 'Fotografia sau codul QR s-a schimbat. Reîncarcă editorul QR și verifică poziția.', 'The photo or QR settings changed. Reload the QR editor and check the position.'))
                else:
                    st.error(t('Не удалось сохранить QR-код. Повторите попытку.', 'Codul QR nu a putut fi salvat. Încearcă din nou.', 'Could not save the QR code. Please try again.'))
            else:
                st.session_state.pop(state_key, None)
                st.session_state[state_key + '_revision'] = revision + 1
                st.session_state[state_key + '_notice'] = True
                # Keep the independent text/photo editor's optimistic snapshot current.
                if intro_source := st.session_state.get('scena_intro_editor_source'):
                    intro_source.update({key: saved[key] for key in DEFAULT_QR_SETTINGS})
                st.rerun()
        if st.button(t('Обновить редактор QR-кода', 'Reîncarcă editorul QR', 'Reload QR editor')):
            st.session_state.pop(state_key, None)
            st.session_state[state_key + '_revision'] = revision + 1
            st.rerun()
