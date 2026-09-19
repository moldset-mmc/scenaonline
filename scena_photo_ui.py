"""Phone-first photo browser using the existing cabinet form boundary."""
from html import escape
import os
from pathlib import Path

from scena_i18n import tr, translate_literaltext
from scena_mobile_ui import cabinet_url
from scena_photo_library import catalog, targets, photo_id, upload_photo, assign_photo, original_path, trash_photo, restore_photo
from scena_ui import st


def photo_url(locale, **params):
    return cabinet_url(locale, 'photos', 'library', **{key: value for key, value in params.items() if value})


def _source(app_dir, path):
    if os.environ.get('SCENA_NATIVE_WEB') == '1':
        from scena_web.media import reference
        return reference(app_dir, path) or ''
    from scena_portfolio import _source as source
    return source(Path(app_dir), path) or ''


def _notice(locale, error):
    from scena_shop import ShopError, _t
    if isinstance(error, ShopError):
        st.error(_t(error.code, locale))
    else:
        st.error(translate_literaltext(locale, str(error)))


def _complete(locale, path, message):
    for key in list(st.session_state):
        if str(key).startswith('photo_snapshot:'):
            del st.session_state[key]
    st.session_state['photo_notice'] = message
    for key in ('mode', 'target'):
        st.query_params.pop(key, None)
    st.query_params['photo'] = photo_id(path)
    if os.environ.get('SCENA_NATIVE_WEB') == '1':
        from scena_web.context import current
        current.get().manifest = None
    st.rerun()


def _version(item):
    key = 'photo_snapshot:' + item['id']
    if key not in st.session_state:
        st.session_state[key] = item['version']
    return st.session_state[key]


def render_photo_library(db, app_dir, locale):
    text = lambda ru, ro, en: tr(locale, ru, ro, en)
    st.markdown('<style>' + (Path(__file__).parent / 'scena_web/static/photos.css').read_text() + '</style>', unsafe_allow_html=True)
    group_labels = {'all': text('Все фото', 'Toate fotografiile', 'All photos'), 'scene': text('Моя Сцена', 'Scena mea', 'My Scene'),
                    'professional': 'Professional', 'model': 'Model', 'shop': 'shopping', 'posts': text('Публикации', 'Publicații', 'Posts'),
                    'saved': text('Сохранённые', 'Salvate', 'Saved'), 'trash': text('Корзина', 'Coș', 'Trash')}
    if message := st.session_state.pop('photo_notice', None):
        st.success(message)
    rows = catalog(db, app_dir, locale, include_trashed=True)
    destinations = targets(db, locale)
    by_target = {item['id']: item for item in destinations}
    chosen = next((row for row in rows if row['id'] == st.query_params.get('photo')), None)
    destination = by_target.get(str(st.query_params.get('target', '')))
    mode = st.query_params.get('mode', '')
    def link(label, **params):
        return '<a data-cabinet-nav href="' + escape(photo_url(locale, **params), quote=True) + '">' + escape(label) + '</a>'
    if chosen or mode == 'upload':
        st.markdown('<nav class="scena-photo-actions">' + link('← ' + text('Все фото', 'Toate fotografiile', 'All photos')) + '</nav>', unsafe_allow_html=True)
    if mode == 'upload':
        st.subheader(text('Добавить фото', 'Adaugă o fotografie', 'Add a photo'))
        st.caption(text('Оригинал сохранится здесь. Затем выберите, где его использовать.', 'Originalul va fi păstrat aici. Apoi alegeți unde să îl folosiți.', 'Your original will be saved here. Then choose where to use it.'))
        with st.form('photo_library_upload'):
            upload = st.file_uploader(text('Фотография', 'Fotografie', 'Photo'), type=['jpg', 'jpeg', 'png', 'webp'])
            st.caption(text('До 20 МБ · JPG, PNG, WebP · от 600 × 400 px', 'Până la 20 MB · JPG, PNG, WebP · de la 600 × 400 px', 'Up to 20 MB · JPG, PNG, WebP · at least 600 × 400 px'))
            save = st.form_submit_button(text('Сохранить фото', 'Salvează fotografia', 'Save photo'), type='primary')
        if save:
            if upload is None:
                st.warning(text('Выберите фотографию.', 'Alegeți o fotografie.', 'Choose a photo.'))
            else:
                try:
                    path = upload_photo(db, app_dir, upload.getvalue(), upload.name)
                except (ValueError, OSError) as error:
                    _notice(locale, error)
                else:
                    _complete(locale, path, text('Фото сохранено. Выберите место на сайте.', 'Fotografia a fost salvată. Alegeți locul pe site.', 'Photo saved. Choose where to use it.'))
        return
    if chosen:
        src = _source(app_dir, chosen['path'])
        title = chosen['uses'][0]['label'] if chosen['uses'] else chosen['name']
        st.markdown('<figure class="scena-photo-preview"><img src="' + escape(src, quote=True) + '" alt="' + escape(title, quote=True) + '"></figure>', unsafe_allow_html=True)
        if chosen['trashed']:
            st.info(text('Фото в корзине. Восстановите его, чтобы снова использовать.', 'Fotografia este în coș. Restabiliți-o pentru a o folosi din nou.', 'This photo is in Trash. Restore it to use it again.'))
            with st.form('photo_restore_' + chosen['id']):
                restore = st.form_submit_button(text('Восстановить фото', 'Restabilește fotografia', 'Restore photo'), type='primary')
            if restore:
                restore_photo(db, app_dir, chosen['path'])
                _complete(locale, chosen['path'], text('Фото восстановлено.', 'Fotografia a fost restabilită.', 'Photo restored.'))
            return
        st.subheader(text('Где используется', 'Unde este folosită', 'Where it is used'))
        if chosen['uses']:
            st.markdown('<ul class="scena-photo-uses">' + ''.join('<li>' + escape(use['label']) + '</li>' for use in chosen['uses']) + '</ul>', unsafe_allow_html=True)
        else:
            st.caption(text('Сохранено. В текущих страницах не используется.', 'Salvată. Nu este folosită în paginile curente.', 'Saved. Not used on current pages.'))
        if os.environ.get('SCENA_NATIVE_WEB') == '1':
            st.markdown('<nav class="scena-photo-actions"><a href="/scena-photo/' + chosen['id'] + '" download>' + escape(text('Скачать оригинал', 'Descarcă originalul', 'Download original')) + '</a></nav>', unsafe_allow_html=True)
        elif st.button(text('Подготовить оригинал', 'Pregătește originalul', 'Prepare original')):
            try:
                original = original_path(db, app_dir, chosen['path'])
                st.download_button(text('Скачать оригинал', 'Descarcă originalul', 'Download original'), original.read_bytes(), file_name=chosen['name'])
            except (ValueError, OSError) as error:
                _notice(locale, error)
        with st.expander(text('Использовать на странице', 'Folosește pe o pagină', 'Use on a page'), expanded=bool(destination)):
            if destination:
                item = destination
            else:
                groups = ['', 'scene', 'professional', 'model', 'shop']
                group = st.selectbox(text('Страница', 'Pagina', 'Page'), groups, format_func=lambda value: group_labels.get(value, text('Выберите страницу', 'Alegeți pagina', 'Choose a page')), key='photo_destination_group')
                options = [''] + [item['id'] for item in destinations if item['group'] == group]
                target = st.selectbox(text('Место на странице', 'Locul pe pagină', 'Place on page'), options, format_func=lambda value: by_target[value]['label'] if value else text('Выберите место', 'Alegeți locul', 'Choose a place'), key='photo_destination')
                item = by_target.get(target)
            if item:
                st.write(item['label'])
                expected = _version(item)
                if item['path'] and item['path'] != chosen['path']:
                    current_source = _source(app_dir, item['path'])
                    if current_source:
                        st.image(current_source, width=110, caption=text('Сейчас здесь', 'Acum aici', 'Currently here'))
                same = item['path'] == chosen['path']
                with st.form('photo_assignment_' + photo_id(item['id'])):
                    st.caption(text('Изменится только выбранное место. Предыдущее фото останется в каталоге.', 'Se modifică doar locul ales. Fotografia precedentă rămâne în catalog.', 'Only this placement changes. The previous photo stays in the catalog.'))
                    apply = st.form_submit_button(text('Уже используется здесь', 'Este deja folosită aici', 'Already used here') if same else text('Использовать здесь', 'Folosește aici', 'Use here'), disabled=same, type='primary')
                if apply:
                    try:
                        assign_photo(db, app_dir, item['id'], chosen['path'], expected)
                    except (ValueError, OSError) as error:
                        _notice(locale, error)
                    else:
                        _complete(locale, chosen['path'], text('Фото на странице обновлено.', 'Fotografia de pe pagină a fost actualizată.', 'Photo on the page updated.'))
        used_targets = [use['target'] for use in chosen['uses'] if use['target'] in by_target]
        if used_targets:
            with st.expander(text('Заменить фото', 'Înlocuiește fotografia', 'Replace photo')):
                target = st.selectbox(text('Где заменить', 'Unde o înlocuim', 'Where to replace'), used_targets, format_func=lambda value: by_target[value]['label'], key='photo_replace_target')
                item = by_target[target]
                expected = _version(item)
                st.markdown(link(text('Выбрать из всех фото', 'Alege din toate fotografiile', 'Choose from all photos'), target=target), unsafe_allow_html=True)
                with st.form('photo_replacement_' + photo_id(target)):
                    upload = st.file_uploader(text('Новая фотография', 'Fotografia nouă', 'New photo'), type=['jpg', 'jpeg', 'png', 'webp'])
                    save = st.form_submit_button(text('Сохранить замену', 'Salvează înlocuirea', 'Save replacement'))
                if save:
                    if upload is None:
                        st.warning(text('Выберите фотографию.', 'Alegeți o fotografie.', 'Choose a photo.'))
                    else:
                        try:
                            path = upload_photo(db, app_dir, upload.getvalue(), upload.name)
                            assign_photo(db, app_dir, target, path, expected)
                        except (ValueError, OSError) as error:
                            _notice(locale, error)
                        else:
                            _complete(locale, path, text('Фото заменено. Старый оригинал сохранён.', 'Fotografia a fost înlocuită. Originalul anterior a fost păstrat.', 'Photo replaced. The previous original is preserved.'))
        if any(use['group'] == 'posts' for use in chosen['uses']):
            st.link_button(text('Редактировать публикации', 'Editează publicațiile', 'Edit posts'), cabinet_url(locale, 'promotion', 'posts'))
        with st.expander(text('Файл и история', 'Fișier și istoric', 'File and history')):
            st.caption(chosen['name'] + ' · ' + f'{chosen["size"] / 1024 / 1024:.1f} MB')
            for use in chosen['history']:
                st.write(use['label'])
        with st.expander(text('Удалить фото', 'Șterge fotografia', 'Delete photo')):
            if chosen['uses']:
                st.caption(text('Сначала замените или уберите фото со всех мест, перечисленных выше.', 'Înlocuiți sau eliminați mai întâi fotografia din toate locurile enumerate mai sus.', 'First replace or remove the photo from every placement listed above.'))
            else:
                st.caption(text('Фото переместится в корзину. Его можно восстановить; история публикаций и заказов сохранится.', 'Fotografia va fi mutată în coș și poate fi restabilită. Istoricul publicațiilor și comenzilor se păstrează.', 'The photo moves to Trash and can be restored. Post and order history is preserved.'))
            with st.form('photo_trash_' + chosen['id']):
                remove = st.form_submit_button(text('Переместить в корзину', 'Mută în coș', 'Move to Trash'), disabled=bool(chosen['uses']))
            if remove:
                try:
                    trash_photo(db, app_dir, chosen['path'])
                except (ValueError, OSError) as error:
                    _notice(locale, error)
                else:
                    _complete(locale, chosen['path'], text('Фото перемещено в корзину.', 'Fotografia a fost mutată în coș.', 'Photo moved to Trash.'))
        return

    if st.query_params.get('photo'):
        st.warning(text('Фото не найдено. Выберите другое в каталоге.', 'Fotografia nu a fost găsită. Alegeți alta din catalog.', 'Photo not found. Choose another from the catalog.'))
    active_count = sum(not row['trashed'] for row in rows)
    st.markdown('<div class="scena-photo-toolbar"><span>' + escape(text(f'Фотографий: {active_count}', f'Fotografii: {active_count}', f'Photos: {active_count}')) + '</span>' + link('+ ' + text('Добавить', 'Adaugă', 'Add'), mode='upload') + link(text('Корзина', 'Coș', 'Trash') + ' · ' + str(len(rows)-active_count), filter='trash') + '</div>', unsafe_allow_html=True)
    if destination:
        st.info(text('Выберите фото для: ', 'Alegeți fotografia pentru: ', 'Choose a photo for: ') + destination['label'])
    initial_group = str(st.query_params.get('filter', 'all'))
    if initial_group not in group_labels:
        initial_group = 'all'
    if st.session_state.get('photo_filter_route') != initial_group:
        st.session_state['photo_filter'] = initial_group
        st.session_state['photo_filter_route'] = initial_group
        st.session_state.pop('photo_catalog_page', None)
    group = st.selectbox(text('Показать', 'Afișează', 'Show'), list(group_labels), index=list(group_labels).index(initial_group), format_func=group_labels.get, key='photo_filter')
    st.query_params['filter'] = group
    visible = [row for row in rows if row['trashed'] == (group == 'trash') and (group in ('all', 'trash') or (group == 'saved' and not row['uses']) or any(use['group'] == group for use in row['uses'] + row['history']))]
    pages = max(1, (len(visible) + 11) // 12)
    page = st.selectbox(text('Страница каталога', 'Pagina catalogului', 'Catalog page'), list(range(1, pages + 1)), format_func=lambda value: f'{value} / {pages}', key='photo_catalog_page') if pages > 1 else 1
    cards = []
    for row in visible[(page - 1) * 12:page * 12]:
        title = row['uses'][0]['label'] if row['uses'] else row['name']
        count = len(row['uses'])
        detail = text('В корзине', 'În coș', 'In Trash') if row['trashed'] else text(f'Мест использования: {count}', f'Locuri de utilizare: {count}', f'Used in {count} places') if count else text('Сохранённое фото', 'Fotografie salvată', 'Saved photo')
        source = _source(app_dir, row['path'])
        cards.append('<a class="scena-photo-card" data-cabinet-nav href="' + escape(photo_url(locale, photo=row['id'], target=destination['id'] if destination else ''), quote=True) + '"><img src="' + escape(source, quote=True) + '" alt="' + escape(title, quote=True) + '" loading="lazy" width="240" height="300"><strong>' + escape(title) + '</strong><span>' + escape(detail) + '</span></a>')
    st.markdown('<div class="scena-photo-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)
    if not visible:
        st.info(text('Здесь пока нет фотографий.', 'Încă nu există fotografii aici.', 'No photos here yet.'))
