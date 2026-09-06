"""Safe Model scene builder: drafts, two previews and immutable design history."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid
from datetime import datetime, timezone


PRESETS = {
    'gloss': {'theme': 'gloss', 'accent': '#c8bdab', 'background': '#050505', 'layout': 'editorial', 'animation': 'recede', 'show_location': True, 'show_manifesto': True, 'show_portfolio': True},
    'club': {'theme': 'club', 'accent': '#d6b8c9', 'background': '#100a10', 'layout': 'editorial', 'animation': 'fade', 'show_location': True, 'show_manifesto': True, 'show_portfolio': True},
    'editorial': {'theme': 'editorial', 'accent': '#d9d8ca', 'background': '#11110f', 'layout': 'portrait-left', 'animation': 'recede', 'show_location': True, 'show_manifesto': True, 'show_portfolio': True},
    'custom': {'theme': 'custom', 'accent': '#c8c8c8', 'background': '#050505', 'layout': 'editorial', 'animation': 'none', 'show_location': False, 'show_manifesto': False, 'show_portfolio': True},
}


def _luminance(color):
    values = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    return sum(weight * (value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4)
               for weight, value in zip((.2126, .7152, .0722), values))


def validate_design(value):
    if not isinstance(value, dict) or set(value) - set(PRESETS['gloss']):
        raise ValueError('Выберите оформление из настроек конструктора.')
    design = {**PRESETS['gloss'], **value}
    if design['theme'] not in PRESETS or design['layout'] not in {'editorial', 'portrait-left'} or design['animation'] not in {'recede', 'fade', 'none'}:
        raise ValueError('Проверьте сценарий, композицию и переход.')
    for key in ('accent', 'background'):
        if not isinstance(design[key], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', design[key]):
            raise ValueError('Выберите цвет в палитре.')
        design[key] = design[key].lower()
    if _luminance(design['background']) > .075:
        raise ValueError('Для сцены выберите тёмный фон: так фотографии сливаются со страницей.')
    if (_luminance(design['accent']) + .05) / (_luminance(design['background']) + .05) < 4.5:
        raise ValueError('Сделайте цвет акцента светлее, чтобы текст легко читался.')
    for key in ('show_location', 'show_manifesto', 'show_portfolio'):
        if not isinstance(design[key], bool):
            raise ValueError('Проверьте выбранные блоки.')
    return design


def parse_model_design(value):
    try:
        return validate_design(json.loads(value)) if value else dict(PRESETS['gloss'])
    except (ValueError, TypeError):
        return dict(PRESETS['gloss'])


def init_model_builder(db_path):
    with sqlite3.connect(db_path, timeout=15) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS model_designs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, design_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft','published','archived')) DEFAULT 'draft',
            revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            published_at TEXT NOT NULL DEFAULT '', preview_hash TEXT NOT NULL DEFAULT '', restored_from INTEGER, snapshot_json TEXT NOT NULL DEFAULT '{}')''')
        if 'snapshot_json' not in {row[1] for row in c.execute('PRAGMA table_info(model_designs)')}:
            c.execute("ALTER TABLE model_designs ADD COLUMN snapshot_json TEXT NOT NULL DEFAULT '{}'")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS model_one_published_design ON model_designs(status) WHERE status='published'")


def _connection(db_path):
    c = sqlite3.connect(db_path, timeout=15)
    c.row_factory = sqlite3.Row
    return c


def _require_pro(db_path):
    from scena_cabinet import get_pro_status
    if not get_pro_status(db_path)['is_active']:
        raise ValueError('Создание и изменение оформления доступны в PRO. Опубликованная Сцена сохраняется.')


def _require_live_pro(connection):
    row = connection.execute("SELECT status,expires_at FROM pro_subscriptions WHERE owner_key='master'").fetchone()
    if row is None or row['status'] not in {'trial', 'active'} or datetime.fromisoformat(row['expires_at']).astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise ValueError('Продлите PRO, чтобы изменить оформление.')


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _title(value):
    value = str(value).strip()
    if not value or len(value) > 100:
        raise ValueError('Назовите сценарий: от 1 до 100 символов.')
    return value


def list_model_designs(db_path):
    init_model_builder(db_path)
    with _connection(db_path) as c:
        return [dict(row) for row in c.execute('SELECT * FROM model_designs ORDER BY updated_at DESC,id DESC')]


def published_model_design(db_path):
    try:
        with _connection(db_path) as c:
            row = c.execute("SELECT design_json FROM model_designs WHERE status='published'").fetchone()
            return parse_model_design(row['design_json']) if row else dict(PRESETS['gloss'])
    except sqlite3.OperationalError:
        return dict(PRESETS['gloss'])


def create_model_design(db_path, title, preset='gloss', *, restored_from=None, app_dir=None):
    _require_pro(db_path)
    init_model_builder(db_path)
    if preset not in PRESETS:
        raise ValueError('Выберите сценарий SCENA.')
    with _connection(db_path) as c:
        c.execute('BEGIN IMMEDIATE')
        _require_live_pro(c)
        if c.execute("SELECT count(*) FROM model_designs WHERE status='draft'").fetchone()[0] >= 20:
            raise ValueError('Сохранено 20 черновиков. Удалите ненужный, чтобы создать новый.')
        design = dict(PRESETS[preset])
        snapshot = _snapshot(dict(c.execute('SELECT key,value FROM profile_settings').fetchall()))
        if restored_from is not None:
            row = c.execute("SELECT design_json,snapshot_json FROM model_designs WHERE id=? AND status IN ('published','archived')", (restored_from,)).fetchone()
            if row is None:
                raise ValueError('Версия оформления не найдена.')
            design = parse_model_design(row['design_json'])
            snapshot = json.loads(row['snapshot_json']) or snapshot
            if app_dir is not None:
                from model_landing import resolve_media_path
                for key in snapshot:
                    if key.endswith('_image') and snapshot[key] and not resolve_media_path(Path(app_dir), snapshot[key]):
                        snapshot[key] = ''
        now = _now()
        cursor = c.execute('INSERT INTO model_designs(title,design_json,created_at,updated_at,restored_from,snapshot_json) VALUES(?,?,?,?,?,?)',
                           (_title(title), json.dumps(design), now, now, restored_from, json.dumps(snapshot, ensure_ascii=False)))
        return cursor.lastrowid


def update_model_design(db_path, design_id, title, value, expected_revision):
    _require_pro(db_path)
    design = validate_design(value)
    with _connection(db_path) as c:
        c.execute('BEGIN IMMEDIATE')
        _require_live_pro(c)
        cursor = c.execute("UPDATE model_designs SET title=?,design_json=?,revision=revision+1,updated_at=?,preview_hash='' WHERE id=? AND status='draft' AND revision=?",
                           (_title(title), json.dumps(design), _now(), design_id, expected_revision))
        if cursor.rowcount != 1:
            raise ValueError('Черновик изменён в другом окне. Откройте его заново.')


def delete_model_draft(db_path, design_id):
    _require_pro(db_path)
    with _connection(db_path) as c:
        c.execute('BEGIN IMMEDIATE')
        _require_live_pro(c)
        c.execute("DELETE FROM model_designs WHERE id=? AND status='draft'", (design_id,))


SNAPSHOT_KEY = re.compile(r"model_(?:intro_(?:enabled|image|translations_approved|(?:title|text|details|alt)_(?:ru|ro|en)|(?:desktop|mobile)_[xy])|slide_[1-5]_(?:image|visible|translations_approved|(?:manifesto|alt)_(?:ru|ro|en)|order|duration_seconds|(?:desktop|mobile)_[xy])|slider_(?:enabled|autoplay|first)|title(?:_(?:ro|en))?)$")


def _snapshot(settings):
    return {key: str(value) for key, value in settings.items() if SNAPSHOT_KEY.fullmatch(key)}


def _validate_snapshot_media(snapshot, app_dir):
    from model_landing import resolve_media_path
    required = []
    if snapshot.get('model_intro_enabled') == '1':
        required.append(('model_intro_image', 'Знакомство'))
    if snapshot.get('model_slider_enabled', '1') == '1':
        for i in range(1, 6):
            if snapshot.get(f'model_slide_{i}_visible') == '1':
                required.append((f'model_slide_{i}_image', f'Образ {i}'))
    for key, label in required:
        path = resolve_media_path(Path(app_dir), snapshot.get(key))
        if path is None or path.suffix.lower() not in {'.png', '.webp', '.jpg', '.jpeg'}:
            raise ValueError(f'{label}: фотография была удалена или не выбрана. Добавьте замену в черновик перед публикацией.')


def update_model_snapshot(db_path, design_id, values, expected_revision):
    _require_pro(db_path)
    if not isinstance(values, dict) or set(values) != set(_snapshot(values)) or any(len(str(v)) > 6000 for v in values.values()):
        raise ValueError('Проверьте содержимое сценария.')
    with _connection(db_path) as c:
        c.execute('BEGIN IMMEDIATE')
        _require_live_pro(c)
        row = c.execute("SELECT snapshot_json FROM model_designs WHERE id=? AND status='draft' AND revision=?", (design_id, expected_revision)).fetchone()
        if row is None:
            raise ValueError('Черновик изменён. Откройте его заново.')
        snapshot = {**json.loads(row['snapshot_json']), **_snapshot(values)}
        c.execute("UPDATE model_designs SET snapshot_json=?,revision=revision+1,preview_hash='',updated_at=? WHERE id=?", (json.dumps(snapshot, ensure_ascii=False), _now(), design_id))


def save_model_draft_photo(db_path, design_id, field, data, app_dir, expected_revision):
    from scena_model_intro import _original
    if not re.fullmatch(r'model_(?:intro|slide_[1-5])_image', field):
        raise ValueError('Выберите фотографию сценария.')
    _require_pro(db_path)
    extension = _original(data)
    root = Path(app_dir).resolve()
    folder = (root / 'media' / 'model-designs').resolve()
    folder.relative_to(root)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f'{uuid.uuid4().hex}.{extension}'
    try:
        with destination.open('xb') as handle:
            handle.write(data)
        update_model_snapshot(db_path, design_id, {field: destination.relative_to(root).as_posix()}, expected_revision)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _preview_hash(c, row, app_dir):
    from model_landing import model_intro_from_settings, model_slides_from_settings
    settings = dict(c.execute('SELECT key,value FROM profile_settings').fetchall())
    # The draft can be reviewed before making the public Model page visible.
    snapshot = json.loads(row['snapshot_json']) or _snapshot(settings)
    ready = {**settings, **snapshot, 'model_published': '1'}
    _validate_snapshot_media(ready, app_dir)
    intro = model_intro_from_settings(ready, Path(app_dir))
    slides = model_slides_from_settings(ready, Path(app_dir))
    if ready.get('model_intro_enabled') == '1' and intro is None:
        raise ValueError('Проверьте текст и языковые версии знакомства перед публикацией.')
    if ready.get('model_slider_enabled', '1') == '1':
        expected_slides = sum(ready.get(f'model_slide_{i}_visible') == '1' for i in range(1, 6))
        if len(slides) != expected_slides:
            raise ValueError('Заполните подписи и описания фото на обоих языках, затем подтвердите версии образов.')
    if not intro and (not slides or ready.get('model_slider_enabled') == '0'):
        raise ValueError('Добавьте фотографию знакомства или готовый образ перед публикацией.')
    signature = json.dumps({'design': row['design_json'], 'revision': row['revision'],
                            'intro': intro, 'slides': slides, 'snapshot': snapshot,
                            'name': {key: val for key, val in settings.items() if key.startswith('master_name')},
                            'renderer_settings': {key: val for key, val in settings.items() if (key.startswith('model_') and key != 'model_design_json') or key in {'location', 'location_ru', 'location_ro', 'location_en', 'public_base_url'}}}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(signature.encode()).hexdigest(), ready


def prepare_model_preview(db_path, design_id, app_dir):
    _require_pro(db_path)
    with _connection(db_path) as c:
        c.execute('BEGIN IMMEDIATE')
        _require_live_pro(c)
        row = c.execute("SELECT * FROM model_designs WHERE id=? AND status='draft'", (design_id,)).fetchone()
        if row is None:
            raise ValueError('Черновик не найден.')
        fingerprint, settings = _preview_hash(c, row, app_dir)
        c.execute('UPDATE model_designs SET preview_hash=? WHERE id=?', (fingerprint, design_id))
        return fingerprint, {**settings, 'model_design_json': row['design_json']}


def publish_model_design(db_path, design_id, app_dir, preview_hash, *, desktop_confirmed=False, mobile_confirmed=False):
    _require_pro(db_path)
    if not desktop_confirmed or not mobile_confirmed:
        raise ValueError('Проверьте оба просмотра: компьютер и телефон.')
    with _connection(db_path) as c:
        c.execute('BEGIN IMMEDIATE')
        _require_live_pro(c)
        row = c.execute("SELECT * FROM model_designs WHERE id=? AND status='draft'", (design_id,)).fetchone()
        if row is None:
            raise ValueError('Черновик уже опубликован или изменён.')
        current_hash, _ = _preview_hash(c, row, app_dir)
        if not preview_hash or row['preview_hash'] != preview_hash or current_hash != preview_hash:
            raise ValueError('После просмотра содержимое изменилось. Проверьте компьютер и телефон ещё раз.')
        c.execute("UPDATE model_designs SET status='archived' WHERE status='published'")
        c.execute("UPDATE model_designs SET status='published',published_at=?,updated_at=?,preview_hash='' WHERE id=?", (_now(), _now(), design_id))
        snapshot = _snapshot(json.loads(row['snapshot_json']))
        c.executemany('INSERT INTO profile_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', snapshot.items())
        c.execute("INSERT INTO profile_settings(key,value) VALUES('model_design_json',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (row['design_json'],))


def render_model_builder(db_path, settings, app_dir, locale='ru'):
    import streamlit as st
    from model_landing import build_model_landing_html
    from scena_cabinet import get_pro_status
    from scena_i18n import tr
    t = lambda ru, ro, en: tr(locale, ru, ro, en)
    st.subheader(t('Ваш сценарий Model', 'Scenariul tău Model', 'Your Model scene'))
    st.caption(t('Выберите настроение, композицию и свет. Сначала черновик, затем просмотр и ваш выход.',
                 'Alege atmosfera, compoziția și lumina. Mai întâi o schiță, apoi previzualizarea și apariția ta.',
                 'Choose a mood, composition and light. Draft it, preview it, then take the stage.'))
    if 'model_design_selected_next' in st.session_state:
        st.session_state['model_design_selected'] = st.session_state.pop('model_design_selected_next')
    active = get_pro_status(db_path)['is_active']
    rows = list_model_designs(db_path)
    labels = {'gloss': t('Глянец', 'Luciu', 'Gloss'), 'club': t('Клубная атмосфера', 'Atmosferă de club', 'Club atmosphere'),
              'editorial': t('Редакционная обложка', 'Copertă editorială', 'Editorial cover'), 'custom': t('С чистого листа', 'De la zero', 'Start from scratch')}
    cols = st.columns(3)
    for column, key, body in zip(cols, ('gloss', 'club', 'editorial'), (
        t('Чёрная сцена, мягкое серебро и плавный выход.', 'Scenă neagră, argint discret și o apariție lină.', 'A black stage, soft silver and a smooth entrance.'),
        t('Глубокий сливовый свет и атмосфера премьеры.', 'Lumină prună profundă și atmosferă de premieră.', 'Deep plum lighting and premiere atmosphere.'),
        t('Архитектурная композиция и журнальная выразительность.', 'Compoziție arhitecturală și expresivitate editorială.', 'Architectural composition and editorial presence.'))):
        with column:
            st.markdown(f'**{labels[key]}**')
            st.write(body)
    if active:
        with st.form('new_model_design'):
            preset = st.selectbox(t('Начать с', 'Începe cu', 'Start with'), list(labels), format_func=labels.get)
            title = st.text_input(t('Название сценария', 'Numele scenariului', 'Scene name'), value=t('Мой новый выход', 'Noua mea apariție', 'My new entrance'))
            if st.form_submit_button(t('Создать черновик', 'Creează schița', 'Create draft')):
                try:
                    st.session_state['model_design_selected'] = create_model_design(db_path, title, preset)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    else:
        st.info(t('Продлите PRO, чтобы создать новый сценарий. Ваше опубликованное оформление остаётся с вами.',
                  'Reînnoiește PRO pentru un scenariu nou. Designul publicat rămâne al tău.',
                  'Renew PRO to create a new scene. Your published design stays yours.'))
    drafts = [row for row in rows if row['status'] == 'draft']
    if drafts and active:
        by_id = {row['id']: row for row in drafts}
        selected = st.selectbox(t('Мои черновики', 'Schițele mele', 'My drafts'), list(by_id),
                                format_func=lambda key: by_id[key]['title'], key='model_design_selected')
        row = by_id[selected]
        design = parse_model_design(row['design_json'])
        rev = row['revision']
        with st.form(f'edit_model_design_{selected}_{rev}'):
            title = st.text_input(t('Название', 'Denumire', 'Name'), value=row['title'])
            left, right = st.columns(2)
            with left:
                design['accent'] = st.color_picker(t('Свет и акцент', 'Lumină și accent', 'Light and accent'), design['accent'])
                design['background'] = st.color_picker(t('Фон сцены', 'Fundalul scenei', 'Stage background'), design['background'])
                design['layout'] = st.selectbox(t('Композиция', 'Compoziție', 'Composition'), ['editorial', 'portrait-left'], index=['editorial', 'portrait-left'].index(design['layout']),
                    format_func=lambda val: t('Фото справа', 'Fotografia în dreapta', 'Photo on the right') if val == 'editorial' else t('Фото слева', 'Fotografia în stânga', 'Photo on the left'))
            with right:
                animations = {'recede': t('Отдаление и размытие', 'Retragere și estompare', 'Recede and blur'), 'fade': t('Мягкое растворение', 'Tranziție lină', 'Soft fade'), 'none': t('Без анимации', 'Fără animație', 'No animation')}
                design['animation'] = st.selectbox(t('Смена образов', 'Schimbarea imaginilor', 'Image transitions'), list(animations), index=list(animations).index(design['animation']), format_func=animations.get)
                for key, label in [('show_location', t('Показывать город', 'Arată orașul', 'Show location')), ('show_manifesto', t('Личные фразы', 'Mesaje personale', 'Personal phrases')), ('show_portfolio', t('Кнопка портфолио', 'Butonul portofoliu', 'Portfolio button'))]:
                    design[key] = st.checkbox(label, value=design[key])
            if st.form_submit_button(t('Сохранить оформление', 'Salvează designul', 'Save design')):
                try:
                    update_model_design(db_path, selected, title, design, rev)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        with st.expander(t('Фотографии и текст этого сценария', 'Fotografiile și textul acestui scenariu', 'Photos and text in this scene')):
            snapshot = json.loads(row['snapshot_json']) or _snapshot(settings)
            fields = {'model_intro_image': t('Знакомство', 'Prezentare', 'Introduction'), **{f'model_slide_{i}_image': f'Model {i}' for i in range(1, 6)}}
            field = st.selectbox(t('Фотография', 'Fotografie', 'Photo'), list(fields), format_func=fields.get, key=f'draft_photo_slot_{selected}')
            from model_landing import resolve_media_path
            current_photo = resolve_media_path(Path(app_dir), snapshot.get(field))
            if current_photo:
                st.image(str(current_photo), width=200)
            else:
                st.info(t('Эта фотография была удалена. Выберите замену для черновика.', 'Fotografia a fost ștearsă. Alege o înlocuire pentru schiță.', 'This photo was deleted. Choose a replacement for the draft.'))
            upload = st.file_uploader(t('Заменить в черновике', 'Înlocuiește în schiță', 'Replace in this draft'), type=['jpg', 'jpeg', 'png', 'webp'], key=f'draft_upload_{selected}_{rev}_{field}')
            if upload and st.button(t('Сохранить фотографию', 'Salvează fotografia', 'Save photo'), key=f'draft_save_photo_{selected}_{rev}_{field}'):
                try:
                    save_model_draft_photo(db_path, selected, field, upload.getvalue(), app_dir, rev)
                    st.session_state.pop('model_design_preview', None)
                    st.rerun()
                except (ValueError, OSError) as exc:
                    st.error(str(exc))
            prefix = field[:-6]
            with st.form(f'draft_content_{selected}_{rev}_{prefix}'):
                changes = {}
                tabs = st.tabs(['RU', 'RO', 'EN'])
                for tab, language in zip(tabs, ('ru', 'ro', 'en')):
                    with tab:
                        if prefix == 'model_intro':
                            items = [('title', t('Заголовок', 'Titlu', 'Title')), ('text', t('Знакомство', 'Prezentare', 'Introduction')), ('details', t('Дополнительно', 'Mai multe', 'More about me'))]
                        else:
                            items = [('manifesto', t('Личная фраза', 'Mesaj personal', 'Personal phrase'))]
                        for suffix, label in items:
                            key = f'{prefix}_{suffix}_{language}'
                            changes[key] = st.text_area(label + ' ' + language.upper(), value=snapshot.get(key, ''), max_chars=2400 if suffix == 'text' else 1600, height=90)
                        key = f'{prefix}_alt_{language}'
                        changes[key] = st.text_input(t('Описание фото', 'Descrierea fotografiei', 'Photo description') + ' ' + language.upper(), value=snapshot.get(key, ''), max_chars=240)
                approved = st.checkbox(t('Языковые версии проверены', 'Versiunile lingvistice sunt verificate', 'Language versions checked'), value=snapshot.get(prefix + '_translations_approved') == '1')
                changes[prefix + '_translations_approved'] = '1' if approved else '0'
                for view, label in [('desktop', t('Компьютер', 'Calculator', 'Desktop')), ('mobile', t('Телефон', 'Telefon', 'Phone'))]:
                    cols = st.columns(2)
                    for column, axis, axis_label in zip(cols, ('x', 'y'), (t('Горизонталь', 'Orizontal', 'Horizontal'), t('Вертикаль', 'Vertical', 'Vertical'))):
                        key = f'{prefix}_{view}_{axis}'
                        with column:
                            changes[key] = str(st.slider(f'{label} · {axis_label}', 0, 100, int(snapshot.get(key) or 50)))
                if st.form_submit_button(t('Сохранить текст и кадрирование', 'Salvează textul și încadrarea', 'Save text and framing')):
                    try:
                        update_model_snapshot(db_path, selected, changes, rev)
                        st.session_state.pop('model_design_preview', None)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
        if st.button(t('Просмотреть перед публикацией', 'Previzualizează înainte de publicare', 'Preview before publishing'), key=f'preview_design_{selected}_{rev}'):
            try:
                fingerprint, preview_settings = prepare_model_preview(db_path, selected, app_dir)
                st.session_state['model_design_preview'] = (selected, fingerprint, preview_settings)
            except ValueError as exc:
                st.error(str(exc))
        preview = st.session_state.get('model_design_preview')
        if preview and preview[0] == selected:
            _, fingerprint, preview_settings = preview
            st.caption(t('Компьютер', 'Calculator', 'Desktop'))
            st.iframe(build_model_landing_html(preview_settings, locale, Path(app_dir)), height=800, width='stretch')
            desktop = st.checkbox(t('Просмотр на компьютере проверен', 'Am verificat versiunea desktop', 'Desktop preview checked'), key=f'design_desktop_{fingerprint}')
            st.caption(t('Телефон', 'Telefon', 'Phone'))
            st.iframe(build_model_landing_html(preview_settings, locale, Path(app_dir)), height=780, width=390)
            mobile = st.checkbox(t('Просмотр на телефоне проверен', 'Am verificat versiunea mobilă', 'Mobile preview checked'), key=f'design_mobile_{fingerprint}')
            if st.button(t('Опубликовать этот сценарий', 'Publică acest scenariu', 'Publish this scene'), type='primary', key=f'publish_design_{fingerprint}'):
                try:
                    publish_model_design(db_path, selected, app_dir, fingerprint, desktop_confirmed=desktop, mobile_confirmed=mobile)
                    st.session_state.pop('model_design_preview', None)
                    st.session_state.pop('model_design_selected', None)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        with st.expander(t('Удалить черновик', 'Șterge schița', 'Delete draft')):
            confirmed = st.checkbox(t('Удалить только этот черновик', 'Șterge doar această schiță', 'Delete this draft only'), key=f'delete_confirm_{selected}')
            if st.button(t('Удалить', 'Șterge', 'Delete'), disabled=not confirmed, key=f'delete_design_{selected}'):
                delete_model_draft(db_path, selected)
                st.session_state.pop('model_design_selected', None)
                st.session_state.pop('model_design_preview', None)
                st.rerun()
    history = [row for row in rows if row['status'] != 'draft']
    if history:
        st.subheader(t('История оформления', 'Istoricul designului', 'Design history'))
        for row in history:
            with st.container(border=True):
                st.write(f"{row['title']} · {row['published_at'][:16].replace('T', ' ')}")
                st.caption(t('На вашей Сцене', 'Pe Scena ta', 'On your Scene') if row['status'] == 'published' else t('Предыдущая версия', 'Versiunea anterioară', 'Previous version'))
                if st.button(t('Вернуть эту версию', 'Revino la această versiune', 'Restore this version'), key=f'restore_design_{row["id"]}', disabled=not active):
                    try:
                        st.session_state['model_design_selected_next'] = create_model_design(db_path, row['title'], restored_from=row['id'], app_dir=app_dir)
                        st.session_state.pop('model_design_preview', None)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
