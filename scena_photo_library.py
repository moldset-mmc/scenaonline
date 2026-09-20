"""One owner catalog over existing media, with explicit, guarded assignments.

Originals are never overwritten or deleted. Catalog reads only paths/metadata;
image bytes are materialized only for a selected original or an assignment.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import uuid
from contextlib import nullcontext

from scena_database import connect, cloud_database
from scena_i18n import tr

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def photo_id(path):
    return hashlib.sha256(str(path).encode()).hexdigest()


def _safe_path(root, value):
    root = Path(root).resolve()
    value = str(value)
    parts = PurePosixPath(value).parts
    if (not value.startswith('media/') or '\\' in value or '..' in parts
            or any(part.startswith('.') for part in parts)
            or str(PurePosixPath(value)) != value
            or Path(value).suffix.lower() not in EXTENSIONS):
        raise ValueError('Недопустимая фотография.')
    path = root / value
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != root and parent.is_relative_to(root)):
        raise ValueError('Недопустимая фотография.')
    if not path.resolve().is_relative_to(root / 'media'):
        raise ValueError('Недопустимая фотография.')
    return path


def _rows(connection, sql):
    cursor = connection.execute(sql)
    keys = [column[0] for column in cursor.description]
    return [dict(zip(keys, row)) for row in cursor.fetchall()]


def _files(db, app_dir):
    root = Path(app_dir).resolve()
    files = {}
    for directory, subdirs, names in os.walk(root / 'media', followlinks=False):
        subdirs[:] = [name for name in subdirs if not name.startswith('.') and not (Path(directory) / name).is_symlink()]
        for name in names:
            relative = (Path(directory) / name).relative_to(root).as_posix()
            try:
                path = _safe_path(root, relative)
                if path.is_file():
                    files[relative] = {'size': path.stat().st_size, 'source': 'local'}
            except ValueError:
                continue
    if cloud_database(db):
        with connect(db) as con:
            for path, size in con.execute('SELECT path,bytes FROM scena_media_files').fetchall():
                try:
                    _safe_path(root, path)
                    files[path] = {'size': size, 'source': 'cloud'}
                except ValueError:
                    continue
    return files


def _targets(settings, products, locale='ru'):
    from scena_portfolio import effective_slots
    items = []
    def add(key, label, path, group, deps=None, product=None):
        state = deps or {key: settings.get(key, '')}
        items.append({'id': key, 'label': label, 'path': path or '', 'group': group,
                      'version': photo_id(json.dumps(state, sort_keys=True)), 'product': product})

    scene = settings.get('avatar_url', '').strip() or settings.get('scene_hero_image', '')
    cover = settings.get('professional_cover_image', '').strip() or settings.get('beauty_image_1', '').strip() or settings.get('professional_hero_image', '')
    add('avatar_url', tr(locale, 'Моя Сцена · главное фото', 'Scena mea · fotografia principală', 'My Scene · main photo'), scene, 'scene',
        {key: settings.get(key, '') for key in ('avatar_url', 'scene_hero_image')})
    add('professional_cover_image', tr(locale, 'Professional · обложка', 'Professional · copertă', 'Professional · cover'), cover, 'professional',
        {key: settings.get(key, '') for key in ('professional_cover_image', 'beauty_image_1', 'professional_hero_image')})
    add('professional_hero_image', tr(locale, 'Запись на услуги · обложка', 'Programare · copertă', 'Booking · cover'), settings.get('professional_hero_image', ''), 'professional')
    add('course_cover_image', tr(locale, 'Курсы · обложка', 'Cursuri · copertă', 'Courses · cover'), settings.get('course_cover_image') or settings.get('professional_hero_image', ''), 'professional',
        {key: settings.get(key, '') for key in ('course_cover_image', 'professional_hero_image')})
    add('model_intro_image', tr(locale, 'Model · визитка', 'Model · prezentare', 'Model · introduction'), settings.get('model_intro_image', ''), 'model')
    for index in range(1, 6):
        key = f'model_slide_{index}_image'
        add(key, tr(locale, f'Model · образ {index}', f'Model · imaginea {index}', f'Model · look {index}'), settings.get(key, ''), 'model')
    for prefix, title, group in (('beauty', 'Professional', 'professional'), ('model', 'Model', 'model')):
        slots = effective_slots(settings, prefix)
        for index, path in slots.items():
            key = f'{prefix}_image_{index}'
            add(key, tr(locale, f'{title} · портфолио {index}', f'{title} · portofoliu {index}', f'{title} · portfolio {index}'), path, group,
                {'stored': settings.get(key, ''), 'effective': path, 'customized': settings.get(f'{prefix}_portfolio_customized', '')})
    for product in products:
        if product['status'] == 'archived':
            continue
        name = product.get('name_' + locale) or product.get('name_ru') or 'shopping'
        for index, field in enumerate(('image', 'image_2', 'image_3'), 1):
            add('product:' + product['id'] + ':' + field,
                tr(locale, f'shopping · {name} · фото {index}', f'shopping · {name} · foto {index}', f'shopping · {name} · photo {index}'),
                product.get(field, ''), 'shop', {'revision': product['revision']}, {'id': product['id'], 'field': field, 'revision': product['revision']})
    return items


def targets(db, locale='ru'):
    with connect(db) as con:
        settings = dict(con.execute('SELECT key,value FROM profile_settings').fetchall())
        products = _rows(con, 'SELECT * FROM shop_products ORDER BY updated_at DESC,id')
    return _targets(settings, products, locale)


def _references(value):
    if isinstance(value, str):
        if value.startswith('media/'):
            yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _references(item)
    elif isinstance(value, list):
        for item in value:
            yield from _references(item)


def catalog(db, app_dir, locale='ru', *, include_trashed=False, connection=None):
    files = _files(db, app_dir)
    aliases = {}
    for path in files:
        candidate = PurePosixPath(path)
        if path.startswith('media/publications/') and candidate.name.startswith('scena-publication'):
            original = next((str(candidate.parent / ('original' + ext)) for ext in sorted(EXTENSIONS)
                             if str(candidate.parent / ('original' + ext)) in files), None)
            if original:
                aliases[path] = original
    items = {path: {'id': photo_id(path), 'path': path, 'name': re.sub(r'^[a-f0-9]{32}-', '', Path(path).name),
                    'uses': [], 'history': [], **metadata} for path, metadata in files.items() if path not in aliases}
    def mark(path, label, group, target='', historical=False):
        path = aliases.get(path, path)
        if path in items:
            usage = {'label': label, 'group': group, 'target': target}
            collection = items[path]['history' if historical else 'uses']
            if usage not in collection:
                collection.append(usage)
    def snapshot_refs(snapshot):
        # Reframing a publication creates a rendition in a different folder.
        # Its saved snapshot is the authoritative link back to the original.
        original, rendered = snapshot.get('original_image_path'), snapshot.get('image_url')
        if original in items and rendered in files and original != rendered:
            aliases[rendered] = original
            previous = items.pop(rendered, None)
            if previous:
                for key in ('uses', 'history'):
                    items[original][key].extend(use for use in previous[key] if use not in items[original][key])
        return set(_references(snapshot))
    with (nullcontext(connection) if connection is not None else connect(db)) as con:
        settings = dict(con.execute('SELECT key,value FROM profile_settings').fetchall())
        card_photo = con.execute("SELECT value FROM business_card_settings WHERE key='photo'").fetchone()
        if card_photo and card_photo[0]:
            mark(card_photo[0], tr(locale, 'Визитка · фото', 'Carte de vizită · foto', 'Business card · photo'), 'card')
        products = _rows(con, 'SELECT * FROM shop_products ORDER BY updated_at DESC,id')
        for item in _targets(settings, products, locale):
            mark(item['path'], item['label'], item['group'], item['id'])
        for product in products:
            name = product.get('name_' + locale) or product.get('name_ru') or 'shopping'
            for value in json.loads(product.get('photo_history') or '[]'):
                mark(value, 'shopping · ' + name, 'shop', historical=True)
            if product['status'] == 'archived':
                for key in ('image', 'image_2', 'image_3'):
                    mark(product.get(key), 'shopping · ' + name, 'shop', historical=True)
        for row in _rows(con, 'SELECT post_id,status,draft_json,published_json FROM publication_records'):
            for field, state in (('draft_json', tr(locale, 'черновик', 'ciornă', 'draft')), ('published_json', tr(locale, 'публикация', 'publicat', 'published'))):
                if not row[field]:
                    continue
                for path in snapshot_refs(json.loads(row[field])):
                    mark(path, tr(locale, f'Публикация №{row["post_id"]} · {state}', f'Postarea {row["post_id"]} · {state}', f'Post {row["post_id"]} · {state}'), 'posts', historical=row['status'] == 'archived')
        for row in _rows(con, 'SELECT post_id,snapshot_json FROM publication_versions'):
            for path in snapshot_refs(json.loads(row['snapshot_json'])):
                mark(path, tr(locale, f'История публикации №{row["post_id"]}', f'Istoricul postării {row["post_id"]}', f'Post {row["post_id"]} history'), 'posts', historical=True)
        designs = _rows(con, 'SELECT id,status,design_json,snapshot_json FROM model_designs') if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='model_designs'").fetchone() else []
        for row in designs:
            for key in ('design_json', 'snapshot_json'):
                for path in set(_references(json.loads(row[key] or '{}'))):
                    mark(path, tr(locale, f'Оформление Model №{row["id"]}', f'Design Model {row["id"]}', f'Model design {row["id"]}'), 'model', historical=row['status'] != 'draft')
    for item in items.values():
        # A restored page/version can reuse an original. It becomes visible again.
        item['trashed'] = bool(settings.get('photo_trash:' + item['id'])) and not item['uses']
    return sorted((item for item in items.values() if include_trashed or not item['trashed']), key=lambda item: (not bool(item['uses']), item['uses'][0]['label'] if item['uses'] else item['name'], item['path']))


def trash_photo(db, app_dir, relative):
    """Remove an unused photo from the catalog, preserving recoverable originals."""
    _safe_path(app_dir, relative)
    with connect(db) as con:
        con.execute('BEGIN IMMEDIATE')
        item = next((row for row in catalog(db, app_dir, include_trashed=True, connection=con) if row['path'] == relative), None)
        if not item:
            raise ValueError('Фотография не найдена. Обновите каталог.')
        if item['uses']:
            raise ValueError('Фото используется. Сначала замените или уберите его со всех страниц.')
        con.execute('INSERT INTO profile_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', ('photo_trash:' + item['id'], relative))


def restore_photo(db, app_dir, relative):
    _safe_path(app_dir, relative)
    with connect(db) as con:
        con.execute('DELETE FROM profile_settings WHERE key=?', ('photo_trash:' + photo_id(relative),))


def original_path(db, app_dir, relative):
    path = _safe_path(app_dir, relative)
    if relative not in _files(db, app_dir):
        raise ValueError('Фотография не найдена. Обновите каталог.')
    from scena_media import ensure_local
    ensure_local(app_dir, relative)
    if not path.is_file():
        raise ValueError('Оригинал пока недоступен. Повторите позже.')
    return path


def upload_photo(db, app_dir, data, filename):
    from scena_model_intro import _original
    from scena_media import persist
    extension = _original(data)
    root = Path(app_dir).resolve()
    name = re.sub(r'[^\w.-]+', '-', Path(filename).stem, flags=re.UNICODE).strip('.-')[:60] or 'photo'
    relative = 'media/library/' + uuid.uuid4().hex + '-' + name + '.' + extension
    destination = _safe_path(root, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.upload-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        persist(destination, root, public=False)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        Path(temporary).unlink(missing_ok=True)
    return relative


def assign_photo(db, app_dir, target_id, relative, expected_version):
    from scena_media import publish_reference
    from scena_model_intro import _original
    from scena_portfolio import effective_slots
    _original(original_path(db, app_dir, relative).read_bytes())
    with connect(db) as con:
        con.execute('BEGIN IMMEDIATE')
        settings = dict(con.execute('SELECT key,value FROM profile_settings').fetchall())
        if settings.get('photo_trash:' + photo_id(relative)):
            if not any(row['path'] == relative and row['uses'] for row in catalog(db, app_dir, include_trashed=True, connection=con)):
                raise ValueError('Фото в корзине. Сначала восстановите его.')
        products = _rows(con, 'SELECT * FROM shop_products')
        item = next((item for item in _targets(settings, products) if item['id'] == target_id), None)
        if item is None or item['version'] != expected_version:
            raise ValueError('Фото в этом месте уже изменилось. Обновите страницу и выберите его заново.')
        if item['product']:
            # The product service owns revisions, history, and publication rules.
            product = item['product']
        else:
            product = None
            updates = {target_id: relative}
            if target_id.startswith('model_slide_') or target_id.startswith('model_image_'):
                # Freeze implicit portfolio slots before changing their source.
                if settings.get('model_portfolio_customized') != '1' and not any(settings.get(f'model_image_{i}') for i in range(1, 13)):
                    updates.update({f'model_image_{i}': path for i, path in effective_slots(settings, 'Model').items()})
                    updates['model_portfolio_customized'] = '1'
                    updates[target_id] = relative
            if target_id in ('beauty_image_1', 'professional_hero_image') and not settings.get('professional_cover_image'):
                updates['professional_cover_image'] = settings.get('beauty_image_1') or settings.get('professional_hero_image', '')
            if target_id == 'professional_hero_image' and not settings.get('course_cover_image'):
                updates['course_cover_image'] = settings.get('professional_hero_image', '')
            if target_id.startswith('beauty_image_'):
                updates['beauty_portfolio_customized'] = '1'
            publish_reference(app_dir, relative, connection=con)
            con.executemany('INSERT INTO profile_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', list(updates.items()))
    if product:
        from scena_shop import save_product
        save_product(db, app_dir, {product['field']: relative}, product_id=product['id'], expected_revision=product['revision'])
    return relative
