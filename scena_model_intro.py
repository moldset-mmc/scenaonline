"""Independent Model business card content and original-photo persistence."""
from __future__ import annotations

import io
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid
import warnings


DEFAULT_INTRO_SETTINGS = {
    'model_intro_enabled': '1',
    'model_intro_image': 'media/qr-scenes/model.png',
    'model_intro_title_ru': 'За каждым образом — я.',
    'model_intro_title_en': 'Behind every look, there is me.',
    'model_intro_title_ro': 'În spatele fiecărei imagini sunt eu.',
    'model_intro_text_ru': 'Здесь начинается моя модельная история. В этой подборке — творческие образы, подготовленные для меня: настроение, характер и движение. Через них я рассказываю о себе.',
    'model_intro_text_ro': 'Aici începe povestea mea ca model. Această selecție cuprinde imagini creative pregătite pentru mine: stare, caracter și mișcare. Prin ele povestesc despre mine.',
    'model_intro_text_en': 'This is where my model story begins. These creative looks were prepared for me: mood, character and movement. Through them, I tell my story.',
    'model_intro_details_en': '',
    'model_intro_alt_en': 'A portrait introducing the model',
    'model_intro_details_ru': '',
    'model_intro_details_ro': '',
    'model_intro_alt_ru': 'Портрет для знакомства с моделью',
    'model_intro_alt_ro': 'Portret de prezentare a modelului',
    'model_intro_translations_approved': '1',
    'model_intro_desktop_x': '50',
    'model_intro_desktop_y': '35',
    'model_intro_mobile_x': '50',
    'model_intro_mobile_y': '28',
}


def _original(data: bytes) -> str:
    from PIL import Image, UnidentifiedImageError
    if not data or len(data) > 20 * 1024 * 1024:
        raise ValueError('Выберите фотографию размером до 20 МБ.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as photo:
                ext = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(photo.format)
                if not ext or getattr(photo, 'is_animated', False):
                    raise ValueError('Нужна обычная фотография JPG, PNG или WebP.')
                if min(photo.size) < 400 or max(photo.size) < 600:
                    raise ValueError('Фотография слишком маленькая. Нужна короткая сторона от 400 px, длинная — от 600 px.')
                photo.verify()
        return ext
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('Не удалось открыть фотографию. Выберите другой оригинал.') from exc


def _local_image(app_dir: Path, value: str) -> Path | None:
    try:
        media = (app_dir / 'media').resolve()
        media.relative_to(app_dir.resolve())
        candidate = (app_dir / value).resolve()
        candidate.relative_to(media)
        return candidate if candidate.is_file() else None
    except (ValueError, OSError):
        return None


def saved_portraits(app_dir: Path) -> list[str]:
    folder = app_dir / 'media' / 'model-intro'
    if not folder.is_dir() or folder.is_symlink():
        return []
    return [p.relative_to(app_dir).as_posix() for p in sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in {'.jpg', '.png', '.webp'}]


def save_intro(db_path, app_dir, values, *, upload: bytes | None = None, expected=None):
    """One atomic update; a stale editor cannot silently replace a newer card."""
    from scena_core import get_settings
    app_dir = Path(app_dir)
    settings = get_settings(db_path)
    current = {key: settings.get(key, default) for key, default in DEFAULT_INTRO_SETTINGS.items()}
    updates = {key: str(value).strip() for key, value in values.items() if key in DEFAULT_INTRO_SETTINGS}
    merged = {**current, **updates}
    for key in ('model_intro_enabled', 'model_intro_translations_approved'):
        if merged[key] not in {'0', '1'}:
            raise ValueError('Проверьте настройки визитки.')
    for view in ('desktop', 'mobile'):
        for axis in ('x', 'y'):
            key = f'model_intro_{view}_{axis}'
            try:
                number = int(merged[key])
            except (ValueError, TypeError) as exc:
                raise ValueError('Положение фотографии задаётся числом от 0 до 100.') from exc
            if not 0 <= number <= 100:
                raise ValueError('Положение фотографии задаётся числом от 0 до 100.')
    for field, limit in [('title', 160), ('text', 2400), ('details', 1600), ('alt', 240)]:
        for lang in ('ru', 'ro', 'en'):
            if len(merged[f'model_intro_{field}_{lang}']) > limit:
                raise ValueError(f'Текст слишком длинный: максимум {limit} символов в этом поле.')
    if merged['model_intro_enabled'] == '1':
        if merged['model_intro_translations_approved'] != '1' or any(not merged[f'model_intro_{field}_{lang}'] for field in ('title', 'text', 'alt') for lang in ('ru', 'ro')):
            raise ValueError('Заполните заголовок, текст и описание фото на RU/RO и подтвердите обе версии.')
        if bool(merged['model_intro_details_ru']) != bool(merged['model_intro_details_ro']):
            raise ValueError('Дополнительные сведения заполните на обоих языках или оставьте оба поля пустыми.')
    extension = _original(upload) if upload is not None else None
    if upload is None and merged['model_intro_enabled'] == '1' and not _local_image(app_dir, merged['model_intro_image']):
        raise ValueError('Выберите фотографию для визитки.')
    destination = None
    temporary = None
    try:
        if upload is not None:
            folder = (app_dir / 'media' / 'model-intro').resolve()
            folder.relative_to((app_dir / 'media').resolve())
            folder.relative_to(app_dir.resolve())
            folder.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix='.photo-', dir=folder)
            temporary = Path(name)
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(upload)
                handle.flush()
                os.fsync(handle.fileno())
            destination = folder / f'{uuid.uuid4().hex}.{extension}'
            os.replace(temporary, destination)
            updates['model_intro_image'] = destination.relative_to(app_dir.resolve()).as_posix()
        with sqlite3.connect(db_path, timeout=15) as connection:
            connection.execute('BEGIN IMMEDIATE')
            actual = dict(connection.execute('SELECT key,value FROM profile_settings'))
            if expected is not None and any(actual.get(k, default) != expected.get(k, default) for k, default in DEFAULT_INTRO_SETTINGS.items()):
                raise ValueError('Визитка уже изменена в другом окне. Обновите редактор перед сохранением.')
            connection.executemany('INSERT INTO profile_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', updates.items())
    except Exception:
        if temporary:
            temporary.unlink(missing_ok=True)
        if destination:
            destination.unlink(missing_ok=True)
        raise
    return get_settings(db_path)


def render_intro_editor(db_path, app_dir, settings):
    import streamlit as st
    from scena_i18n import normalize_locale, translate_literaltext
    locale = normalize_locale(st.session_state.get("scena_ui_locale", "ru"))
    def ui(value):
        return translate_literaltext(locale, value)
    app_dir = Path(app_dir)
    key = 'scena_intro_editor'
    if message := st.session_state.pop(key + '_notice', None):
        st.success(ui(message))
    if key + '_source' not in st.session_state:
        st.session_state[key + '_source'] = {k: settings.get(k, v) for k, v in DEFAULT_INTRO_SETTINGS.items()}
    source = st.session_state[key + '_source']
    revision = st.session_state.get(key + '_revision', 0)
    st.subheader(ui('Знакомство — первая страница Model'))
    st.caption(ui('Здесь можно рассказать о себе, увлечениях, поездках и идее ваших образов. Посетитель сначала знакомится с вами, затем сам открывает показ.'))
    values = {}
    with st.form(f'{key}_{revision}'):
        values['model_intro_enabled'] = '1' if st.checkbox(ui('Начинать Model со знакомства'), value=source['model_intro_enabled'] == '1') else '0'
        left, right = st.columns([1, 1.7])
        with left:
            current = _local_image(app_dir, source['model_intro_image'])
            if current:
                st.image(str(current), width=260, caption=ui('Фотография знакомства'))
            upload = st.file_uploader(ui('Отдельная фотография для знакомства'), type=['jpg', 'jpeg', 'png', 'webp'])
            st.caption(ui('До 20 МБ. Для чёткого портрета рекомендуем длинную сторону от 1600 px. Оригиналы сохраняются.'))
            originals = saved_portraits(app_dir)
            initial = DEFAULT_INTRO_SETTINGS['model_intro_image']
            options = ['', *([initial] if _local_image(app_dir, initial) and initial not in originals else []), *originals]
            selected = st.selectbox(ui('Вернуть сохранённый портрет'), options,
                format_func=lambda item: ui('Оставить текущую фотографию') if not item else ui('Начальный портрет') if item == initial else f"{ui('Сохранённый портрет ')}{originals.index(item) + 1}")
            values['model_intro_image'] = selected or source['model_intro_image']
        with right:
            ru, ro, en = st.tabs(['RU', 'RO', 'EN'])
            for tab, lang in ((ru, 'ru'), (ro, 'ro'), (en, 'en')):
                with tab:
                    for field, label, max_chars in [('title', 'Заголовок', 160), ('text', 'О себе и своих образах', 2400), ('details', 'Что ещё важно обо мне — необязательно', 1600), ('alt', 'Описание фотографии', 240)]:
                        setting_key = f'model_intro_{field}_{lang}'
                        widget = st.text_area if field in {'text', 'details'} else st.text_input
                        args = {'height': 130 if field == 'text' else 90} if field in {'text', 'details'} else {}
                        values[setting_key] = widget(ui(f'{label} {lang.upper()}'), value=source[setting_key], max_chars=max_chars, **args)
            values['model_intro_translations_approved'] = '1' if st.checkbox(ui('Языковые версии проверены'), value=source['model_intro_translations_approved'] == '1') else '0'
        with st.expander(ui('Положение фотографии на компьютере и телефоне')):
            desktop, mobile = st.columns(2)
            for column, view, label in ((desktop, 'desktop', 'Компьютер'), (mobile, 'mobile', 'Телефон')):
                with column:
                    st.caption(ui(label))
                    for axis, axis_label in [('x', 'Горизонталь'), ('y', 'Вертикаль')]:
                        setting_key = f'model_intro_{view}_{axis}'
                        values[setting_key] = str(st.slider(f'{ui(label)} · {ui(axis_label)}', 0, 100, int(source[setting_key])))
        submitted = st.form_submit_button(ui('Сохранить визитку'), type='primary', width='stretch')
    if submitted:
        try:
            saved = save_intro(db_path, app_dir, values, upload=upload.getvalue() if upload else None, expected=source)
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(ui(str(exc) if isinstance(exc, ValueError) else 'Не удалось сохранить визитку. Повторите попытку.'))
        else:
            st.session_state[key + '_source'] = {k: saved[k] for k in DEFAULT_INTRO_SETTINGS}
            st.session_state[key + '_revision'] = revision + 1
            st.session_state[key + '_notice'] = 'Визитка сохранена.'
            st.rerun()
    if st.button(ui('Обновить редактор'), key=key + '_reload'):
        st.session_state.pop(key + '_source', None)
        st.session_state[key + '_revision'] = revision + 1
        st.rerun()
    st.link_button(ui('Посмотреть знакомство'), f'?page=model&lang={locale}')
