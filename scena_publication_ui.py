"""Public stories and a small, persistent publication workspace."""
from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import streamlit as st
from scena_i18n import localized_name, tr as translate

from model_landing import image_uri, resolve_media_path
from scena_publications import (
    PublicationValidationError, archive_publication, get_draft, get_publication,
    list_publications, list_versions, publish_local, restore_version, save_draft,
    store_publication_image, restyle_publication_image, render_publication_image, managed_original,
)


_EN = {
    "Публикации": "Publications", "Все публикации": "All publications", "Открыть её Сцену": "Open her Scene",
    "Создайте публикацию, проверьте её и покажите на своей Сцене.": "Create a post, review it, and share it on your Scene.",
    "+ Новая публикация": "+ New post", "1. Материал": "1. Your story", "2. Проверка и публикация": "2. Review and publish",
    "Предпросмотр показывает последнюю сохранённую версию.": "The preview shows your latest saved version.",
    "Открыть предпросмотр": "Open preview", "Эта страница пока не опубликована.": "This page is not published.",
    "Здесь появятся фотографии, истории и новые проекты.": "A place for photographs, stories and new projects.",
    "История": "Story", "Публикация недоступна": "Publication unavailable", "Публикация в архиве": "Archived publication",
    "Автор сняла эту публикацию с показа.": "The author has archived this publication.", "Фотография": "Photograph",
    "JPG, PNG или WEBP до 20 МБ. Короткая сторона — от 600 px, рекомендуем от 1080 px. Оригинал сохраняется; для поста создаётся отдельная копия с лейблом SCENA без обрезки.": "JPG, PNG or WEBP up to 20 MB. Short edge: at least 600 px, ideally 1080 px. Your original is saved; a separate SCENA-labelled copy is prepared without cropping.",
    "Тип публикации": "Post type", "Цена — обязательна для предложения": "Price — required for an offer",
    "Сохранить черновик": "Save draft", "Проверила сохранённый материал. Опубликовать на выбранных страницах.": "I reviewed the saved post. Publish it on the selected pages.",
    "Опубликовать на Сцене": "Publish on my Scene", "Посмотреть опубликованную версию": "View published version",
    "История и архив": "History and archive", "Сохранённая версия": "Saved version", "Вернуть эту версию в черновик": "Restore this version as a draft",
    "3. Подготовить для Facebook или Instagram": "3. Prepare for Facebook or Instagram", "Подробнее": "Learn more", "Публикация": "Publication",
    "Нажмите «Новая публикация», чтобы начать.": "Choose New post to get started.",
    "Этот черновик изменён в другом окне. Скопируйте свои несохранённые правки и загрузите свежую версию.": "This draft changed in another window. Copy your unsaved changes and load the latest version.",
    "Загрузить свежую версию": "Load latest version", "Кнопка и места показа": "Button and visibility", "Адрес для кнопки «Подробнее»": "Link for the Learn more button",
    "Сохранённая фотография и оригинал": "Saved photograph and original", "Версия восстановлена в новый черновик. Проверьте её перед публикацией.": "The version was restored as a new draft. Review it before publishing.",
    "Снять фото и текст с показа, оставить страницу архива с моим именем": "Hide the photograph and text; keep an archive page with my name",
    "Убрать в архив": "Archive", "Открыть публикацию": "Open publication", "Черновик сохранён. Теперь можно проверить и опубликовать.": "Draft saved. You can now review and publish it.",
    "Эта фотография пока не подходит для публикации. Загрузите замену.": "This photograph does not meet the publishing requirements. Upload a replacement.",
    "Скачать оригинал": "Download original", "Публикация появилась на Сцене.": "Your post is now on your Scene.",
    "Публикация в архиве. По прежней ссылке видны только имя и переход на Сцену.": "Post archived. Its link shows only your name and a link to your Scene.",
    "Карусель публикаций": "Publication carousel", "Предложение с ценой": "Offer with price", "Следующая публикация": "Next post", "Предыдущая публикация": "Previous post",
    "Истории и предложения": "Stories and offers",
}


def tr(locale, ru, ro, en=None):
    return translate(locale, ru, ro, en or _EN.get(ru))


def post_text(post, field, locale):
    """Never put a different-language body into a field labelled English."""
    return str(post.get(field+'_'+locale, '') or '')


def post_url(public_id, locale='ru'):
    return '?' + urlencode({'page': 'post', 'post': public_id, 'lang': locale})


def safe_image(app_dir, value):
    """Public posts can expose image media only, never arbitrary app files."""
    value = str(value or '')
    parsed = urlsplit(value)
    if parsed.scheme in {'http', 'https'}:
        return value if parsed.hostname and not parsed.username and not parsed.password else None
    path = resolve_media_path(Path(app_dir), value)
    if path and path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}:
        try:
            path.relative_to((Path(app_dir) / 'media').resolve())
        except ValueError:
            return None
        return image_uri(Path(app_dir), value)
    return None


def _public_posts(db_path, destination):
    flag = {'scene': 'show_scene', 'professional': 'show_professional', 'model': 'show_model'}.get(destination)
    result = []
    for draft in list_publications(db_path, include_archived=False):
        post = get_publication(db_path, draft['public_id'])
        if post and post['status'] == 'published' and (not flag or post.get(flag)):
            result.append(post)
    return result


def render_feed(db_path, app_dir, settings, locale, destination='scene', *, all_posts=False):
    if settings.get('profile_published', '1') != '1':
        return
    if destination not in {'scene', 'professional', 'model'}:
        destination = 'scene'
    if destination != 'scene' and settings.get(destination + '_published', '1') != '1':
        st.info(tr(locale, 'Эта страница пока не опубликована.', 'Această pagină nu este încă publicată.'))
        return
    st.header(tr(locale, 'Публикации', 'Publicații'))
    posts = _public_posts(db_path, destination)
    if not posts:
        st.info(tr(locale, 'Здесь появятся фотографии, истории и новые проекты.', 'Aici vor apărea fotografii, istorii și proiecte noi.'))
        return
    if all_posts:
        for post in posts:
            with st.container(border=True):
                _render_content(post, app_dir, locale)
                st.link_button(tr(locale, 'Открыть публикацию', 'Deschide publicația'), post_url(post['public_id'], locale))
        return
    cards = []
    esc = html.escape
    for post in posts:
        src = safe_image(app_dir, post.get('image_url'))
        photo = f'<img src="{esc(src, quote=True)}" alt="" loading="lazy">' if src else '<div class="empty">SCENA</div>'
        title = post_text(post, 'title', locale) or tr(locale, 'История', 'Poveste')
        body = post_text(post, 'body', locale)
        price = f'<strong>{esc(post["price_text"])}</strong>' if post.get('price_text') else ''
        cards.append(f'<article tabindex="0">{photo}<div class="copy"><h3>{esc(title)}</h3><p>{esc(body[:180])}</p>{price}<a href="{esc(post_url(post["public_id"], locale), quote=True)}" target="_blank" rel="noopener noreferrer">{tr(locale,"Открыть публикацию","Deschide publicația")} ↗</a></div></article>')
    st.iframe('''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
    *{box-sizing:border-box}body{margin:0;color:#293b33;font:15px Arial,sans-serif;background:transparent}
    .controls{display:flex;justify-content:space-between;align-items:center;margin:0 0 12px}.buttons{display:flex;gap:8px}
    button{background:#f5f2e9;border:1px solid #c8c5b9;border-radius:50%;width:42px;height:42px;color:#293b33;font-size:23px;cursor:pointer}
    button:disabled{opacity:.35;cursor:default}button:focus-visible,a:focus-visible,article:focus-visible{outline:3px solid #9e8c54;outline-offset:2px}
    .track{display:flex;gap:18px;overflow-x:auto;scroll-snap-type:x mandatory;padding:4px 2px 12px;scrollbar-width:thin}
    article{flex:0 0 calc((100% - 36px)/3);min-width:240px;height:520px;display:flex;flex-direction:column;scroll-snap-align:start;border:1px solid #ded7ca;border-radius:18px;background:linear-gradient(145deg,#fffdf8,#f3eddf);overflow:hidden}
    img,.empty{display:block;width:100%;height:310px;flex-shrink:0;object-fit:contain;background:#f5f1e8}.empty{display:grid;place-items:center;letter-spacing:6px;font:30px Georgia;color:#9b835b}
    .copy{padding:16px;display:flex;flex-direction:column;flex:1;min-height:0}h3{margin:0 0 10px;font:23px/1.15 Georgia;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}p{line-height:1.5;margin:0 0 10px;height:45px;overflow:hidden}strong{display:block;margin-bottom:4px}a{color:#365745;text-underline-offset:4px;display:inline-block;padding:5px 0;margin-top:auto}
    @media(max-width:650px){article{flex-basis:88%;min-width:0}.track{gap:12px}h3{font-size:22px}}
    @media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
    </style></head><body><div class="controls"><span>''' + tr(locale, 'Истории и предложения', 'Povești și oferte') + '''</span><div class="buttons"><button id="prev" aria-label="''' + tr(locale, 'Предыдущая публикация', 'Publicația precedentă') + '''">‹</button><button id="next" aria-label="''' + tr(locale, 'Следующая публикация', 'Publicația următoare') + '''">›</button></div></div><section class="track" aria-label="''' + tr(locale, 'Карусель публикаций', 'Carusel de publicații') + '''">''' + ''.join(cards) + '''</section><script>
    const track=document.querySelector('.track'),prev=document.querySelector('#prev'),next=document.querySelector('#next');
    function state(){prev.disabled=track.scrollLeft<4;next.disabled=track.scrollLeft+track.clientWidth>=track.scrollWidth-4}
    function move(dir){track.scrollBy({left:dir*(track.querySelector('article').offsetWidth+18),behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'})}
    prev.onclick=()=>move(-1);next.onclick=()=>move(1);track.addEventListener('scroll',state);window.addEventListener('resize',state);
    track.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();move(e.key==='ArrowRight'?1:-1)}});state();
    </script></body></html>''', height=585)
    st.link_button(tr(locale, 'Все публикации', 'Toate publicațiile'), '?' + urlencode({'page': 'posts', 'lang': locale, 'destination': destination}))


def _render_content(post, app_dir, locale):
    if post.get('title_' + locale):
        st.subheader(post['title_' + locale])
    src = safe_image(app_dir, post.get('image_url'))
    if src:
        st.image(src, width='stretch')
    st.text(post.get('body_' + locale, ''))
    if post.get('price_text'):
        st.write(post['price_text'])
    link = post.get('cta_url') or post.get('link_url', '')
    parsed = urlsplit(link)
    if parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username and not parsed.password:
        st.link_button(post.get('cta_label_' + locale) or tr(locale, 'Подробнее', 'Detalii'), link)


def render_post_page(db_path, app_dir, settings, locale, public_id):
    post = get_publication(db_path, public_id)
    visible = bool(post) and (post['status'] == 'archived' or any(
        post.get('show_' + place) and settings.get('profile_published' if place == 'scene' else place + '_published', '1') == '1'
        for place in ('scene', 'professional', 'model')))
    if not visible or settings.get('profile_published', '1') != '1':
        st.title(tr(locale, 'Публикация недоступна', 'Publicația nu este disponibilă'))
        return
    st.caption(localized_name(settings, locale))
    if post['status'] == 'archived':
        st.title(tr(locale, 'Публикация в архиве', 'Publicația este arhivată'))
        st.write(tr(locale, 'Автор сняла эту публикацию с показа.', 'Autoarea a retras această publicație.'))
    else:
        st.title(post.get('title_' + locale) or tr(locale, 'Публикация', 'Publicație'))
        content = dict(post)
        content['title_' + locale] = ''
        _render_content(content, app_dir, locale)
    st.link_button(tr(locale, 'Открыть её Сцену', 'Deschide Scena ei'), '?' + urlencode({'page': 'scene', 'lang': locale}), type='primary')


def _notice(text):
    st.session_state['publication_notice'] = text
    st.rerun()


def _reset_editor(post_id):
    for key in list(st.session_state):
        if key.startswith('post_') and key.endswith('_' + str(post_id)):
            del st.session_state[key]


def render_publication_workspace(db_path, app_dir, settings, locale):
    st.markdown("""<style>
    [class*='st-key-post_frame_'] button{min-height:48px!important;padding:10px 18px!important;font-size:16px!important}
    [class*='st-key-post_frame_'] button[aria-pressed='true'],[class*='st-key-post_frame_'] [aria-checked='true']{box-shadow:0 5px 14px #aa894027!important;font-weight:700!important}
    </style>""", unsafe_allow_html=True)
    st.write(tr(locale, 'Создайте публикацию, проверьте её и покажите на своей Сцене.', 'Creează o publicație, verific-o și afișeaz-o pe Scena ta.'))
    if st.session_state.get('publication_notice'):
        st.success(st.session_state['publication_notice'])
    if st.button(tr(locale, '+ Новая публикация', '+ Publicație nouă'), key='publications_create', type='primary'):
        _reset_editor('new')
        st.session_state['publication_edit_id'] = 'new'
        st.session_state.pop('publication_notice', None)
        st.rerun()
    drafts = list_publications(db_path)
    selected = st.session_state.get('publication_edit_id')
    labels = {'draft': tr(locale,'Черновик','Ciornă','Draft'), 'published': tr(locale,'На Сцене','Pe Scenă','On my Scene'), 'archived': tr(locale,'В архиве','În arhivă','Archived')}
    with st.expander(tr(locale, f'Мои публикации · {len(drafts)}', f'Publicațiile mele · {len(drafts)}', f'My publications · {len(drafts)}'), expanded=selected is None):
        if not drafts:
            st.caption(tr(locale, 'Нажмите «Новая публикация», чтобы начать.', 'Apasă «Publicație nouă» pentru a începe.'))
        for item in drafts:
            label = f"{item.get('title_' + locale) or item.get('body_' + locale,'')[:35] or tr(locale,'Без названия','Fără titlu','Untitled')} · {labels[item['status']]}"
            if item['status'] == 'published' and item['has_unpublished_changes']:
                label += tr(locale,' · есть черновик изменений',' · modificări în ciornă',' · draft changes')
            if st.button(label, key=f"publication_open_{item['id']}", width='stretch'):
                _reset_editor(item['id'])
                st.session_state['publication_edit_id'] = item['id']
                st.session_state.pop('publication_preview_revision', None)
                st.rerun()
    if selected is None:
        return
    current = get_draft(db_path, selected) if selected != 'new' else {}
    suffix = str(selected)
    revision_key = 'post_loaded_revision_' + suffix
    if current:
        if revision_key not in st.session_state:
            st.session_state[revision_key] = current['revision']
        if st.session_state[revision_key] != current['revision']:
            st.warning(tr(locale, 'Этот черновик изменён в другом окне. Скопируйте свои несохранённые правки и загрузите свежую версию.', 'Ciorna a fost modificată în altă fereastră. Copiază modificările nesalvate și încarcă versiunea nouă.'))
            if st.button(tr(locale, 'Загрузить свежую версию', 'Încarcă versiunea nouă'), key='post_reload_' + suffix):
                _reset_editor(selected)
                st.rerun()
    st.subheader(tr(locale, '1. Материал', '1. Conținut'))
    styles = {'auto': tr(locale, 'По фотографии', 'După fotografie', 'Match photo'),
              'ivory': tr(locale, 'Белый', 'Alb', 'Ivory'), 'sand': tr(locale, 'Песочный', 'Nisipiu', 'Sand'),
              'mist': tr(locale, 'Шалфей', 'Salvie', 'Sage'), 'noir': tr(locale, 'Чёрный', 'Negru', 'Noir')}
    formats = {'portrait': tr(locale, 'Лента · 4:5', 'Feed · 4:5', 'Feed · 4:5'),
               'tall': tr(locale, 'Фото · 3:4', 'Foto · 3:4', 'Photo · 3:4'),
               'square': tr(locale, 'Квадрат · 1:1', 'Pătrat · 1:1', 'Square · 1:1')}
    frame_style = st.pills(tr(locale, 'Оформление фотографии', 'Aspectul fotografiei', 'Photo frame'), list(styles),
                          default=current.get('frame_style', 'auto'), format_func=styles.get,
                          selection_mode='single', key='post_frame_style_'+suffix) or current.get('frame_style', 'auto')
    current_format = current.get('frame_format', 'portrait')
    frame_format = st.pills(tr(locale, 'Формат публикации', 'Formatul publicației', 'Post format'), list(formats),
                           default=current_format if current_format in formats else 'portrait', format_func=formats.get,
                           selection_mode='single', key='post_frame_format_'+suffix) or 'portrait'
    if current.get('original_image_path'):
        try:
            raw = managed_original(app_dir, current['original_image_path']).read_bytes()
            st.image(render_publication_image(app_dir, raw, frame_style=frame_style, frame_format=frame_format), width=330)
        except (OSError, PublicationValidationError):
            pass
    with st.form('publication_editor_' + suffix):
        values = {'frame_style': frame_style, 'frame_format': frame_format}
        for tab, language in zip(st.tabs(['RU', 'RO', 'EN']), ('ru', 'ro', 'en')):
            with tab:
                title_label = {'ru':'Заголовок RU','ro':'Titlu RO','en':'Title EN'}[language]
                body_label = {'ru':'Текст RU','ro':'Text RO','en':'Text EN'}[language]
                values['title_'+language] = st.text_input(title_label, value=current.get('title_'+language, ''), key='post_title_'+language+'_'+suffix)
                values['body_'+language] = st.text_area(body_label, value=current.get('body_'+language, ''), key='post_body_'+language+'_'+suffix, height=150)
                if language == 'en':
                    st.caption(tr(locale, 'Добавьте английский текст для международной аудитории.', 'Adaugă textul în engleză pentru publicul internațional.', 'Add English copy for an international audience.'))
        uploaded = st.file_uploader(tr(locale, 'Фотография', 'Fotografie'), type=['jpg', 'jpeg', 'png', 'webp'], key='post_photo_' + suffix)
        st.caption(tr(locale, 'JPG, PNG или WEBP до 20 МБ. Короткая сторона — от 600 px, рекомендуем от 1080 px. Оригинал сохраняется; для поста создаётся отдельная копия с лейблом SCENA без обрезки.', 'JPG, PNG sau WEBP, maximum 20 MB. Latura scurtă: minimum 600 px, recomandat 1080 px. Originalul se păstrează; copia pentru postare primește eticheta SCENA, fără decupare.'))
        values['kind'] = st.selectbox(tr(locale, 'Тип публикации', 'Tipul publicației'), ['story', 'offer'], index=1 if current.get('kind') == 'offer' else 0, format_func=lambda k: tr(locale, 'История', 'Poveste') if k == 'story' else tr(locale, 'Предложение с ценой', 'Ofertă cu preț'), key='post_kind_' + suffix)
        values['price_text'] = st.text_input(tr(locale, 'Цена — обязательна для предложения', 'Preț — obligatoriu pentru ofertă'), value=current.get('price_text', ''), placeholder='450 MDL', key='post_price_' + suffix)
        with st.expander(tr(locale, 'Кнопка и места показа', 'Buton și pagini de afișare')):
            values['cta_url'] = st.text_input(tr(locale, 'Адрес для кнопки «Подробнее»', 'Adresa butonului «Detalii»'), value=current.get('cta_url') or current.get('link_url', ''), key='post_cta_' + suffix)
            for destination, label in [('scene', tr(locale,'Моя Сцена','Scena mea','My Scene')), ('professional', tr(locale,'Профессиональная','Profesional','Professional')), ('model', 'Model')]:
                field = 'show_' + destination
                values[field] = st.checkbox(label, value=bool(current.get(field, destination == 'scene')), key='post_' + field + '_' + suffix)
        values['translations_approved'] = st.checkbox(tr(locale, 'Я проверила все заполненные языковые версии', 'Am verificat toate versiunile completate', 'I reviewed every completed language version'), value=bool(current.get('translations_approved', False)), key='post_approved_' + suffix)
        save = st.form_submit_button(tr(locale, 'Сохранить черновик', 'Salvează ciorna'), key='post_save_' + suffix, type='primary')
    if save:
        try:
            photo_warning = ''
            if uploaded:
                photo = store_publication_image(app_dir, uploaded.getvalue(), uploaded.name, frame_style=frame_style, frame_format=frame_format)
                if not photo['publication_allowed']:
                    photo_warning = ' '.join(photo['warnings'])
                values['image_url'] = photo['image_url'] if photo['publication_allowed'] else ''
                values['original_image_path'] = photo['original_image_path']
            elif current.get('original_image_path') and (current.get('needs_frame_refresh') or frame_style != current.get('frame_style') or frame_format != current.get('frame_format')):
                values.update(restyle_publication_image(app_dir, current['original_image_path'], frame_style=frame_style, frame_format=frame_format))
            saved = save_draft(db_path, None if selected == 'new' else selected, expected_revision=st.session_state.get(revision_key), **values)
        except (PublicationValidationError, OSError) as error:
            st.error(str(error))
        else:
            st.session_state['publication_edit_id'] = saved['id']
            st.session_state['post_loaded_revision_' + str(saved['id'])] = saved['revision']
            st.session_state.pop('publication_preview_revision', None)
            _notice(photo_warning + ' Оригинал сохранён в черновике; замените фото перед публикацией.' if photo_warning else tr(locale, 'Черновик сохранён. Теперь можно проверить и опубликовать.', 'Ciorna a fost salvată. Acum o poți verifica și publica.'))
    if not current:
        return
    src = safe_image(app_dir, current.get('image_url'))
    original = resolve_media_path(Path(app_dir), current.get('original_image_path'))
    if src or original:
        with st.expander(tr(locale, 'Сохранённая фотография и оригинал', 'Fotografia salvată și originalul')):
            if src:
                st.image(src, width=280)
            else:
                st.warning(tr(locale, 'Эта фотография пока не подходит для публикации. Загрузите замену.', 'Această fotografie nu este potrivită pentru publicare. Încarcă un înlocuitor.'))
            if original and safe_image(app_dir, current.get('original_image_path')):
                st.download_button(tr(locale, 'Скачать оригинал', 'Descarcă originalul'), original.read_bytes(), file_name=original.name)
    st.subheader(tr(locale, '2. Проверка и публикация', '2. Verificare și publicare'))
    st.caption(tr(locale, 'Предпросмотр показывает последнюю сохранённую версию.', 'Previzualizarea arată ultima versiune salvată.'))
    if st.button(tr(locale, 'Открыть предпросмотр', 'Deschide previzualizarea'), key='post_preview_' + suffix):
        st.session_state['publication_preview_revision'] = (current['id'], current['revision'])
        st.session_state['post_preview_confirm_' + suffix] = False
    if st.session_state.get('publication_preview_revision') == (current['id'], current['revision']):
        languages = ['ru','ro'] + (['en'] if current.get('body_en') else [])
        for tab, language in zip(st.tabs([language.upper() for language in languages]), languages):
            with tab:
                with st.container(border=True):
                    _render_content(current, app_dir, language)
        approved = st.checkbox(tr(locale, 'Проверила сохранённый материал. Опубликовать на выбранных страницах.', 'Am verificat conținutul salvat. Publică pe paginile selectate.'), key='post_preview_confirm_' + suffix)
        if st.button(tr(locale, 'Опубликовать на Сцене', 'Publică pe Scena mea'), key='post_publish_' + suffix, disabled=not approved, type='primary'):
            try:
                publish_local(db_path, selected, current['revision'], media_root=app_dir)
            except PublicationValidationError as error:
                st.error(str(error))
            else:
                st.session_state.pop('publication_preview_revision', None)
                _notice(tr(locale, 'Публикация появилась на Сцене.', 'Publicația a apărut pe Scena ta.'))
    if current['status'] == 'published':
        st.link_button(tr(locale, 'Посмотреть опубликованную версию', 'Vezi versiunea publicată'), post_url(current['public_id'], locale))
    with st.expander(tr(locale, 'История и архив', 'Istoric și arhivă')):
        versions = list_versions(db_path, selected)
        version = st.selectbox(tr(locale, 'Сохранённая версия', 'Versiune salvată'), versions, format_func=lambda v: f"{v['created_at'][:16].replace('T', ' ')} UTC · v{v['revision']}", key='post_version_' + suffix)
        if st.button(tr(locale, 'Вернуть эту версию в черновик', 'Restabilește această versiune în ciornă'), key='post_restore_' + suffix):
            restore_version(db_path, selected, version['revision'])
            _reset_editor(selected)
            st.session_state.pop('publication_preview_revision', None)
            _notice(tr(locale, 'Версия восстановлена в новый черновик. Проверьте её перед публикацией.', 'Versiunea a fost restabilită într-o ciornă nouă. Verific-o înainte de publicare.'))
        if current['status'] == 'published':
            confirmed = st.checkbox(tr(locale, 'Снять фото и текст с показа, оставить страницу архива с моим именем', 'Retrage fotografia și textul, păstrează pagina arhivei cu numele meu'), key='post_archive_confirm_' + suffix)
            if st.button(tr(locale, 'Убрать в архив', 'Arhivează'), disabled=not confirmed, key='post_archive_' + suffix):
                archive_publication(db_path, selected)
                _notice(tr(locale, 'Публикация в архиве. По прежней ссылке видны только имя и переход на Сцену.', 'Publicația este arhivată. Linkul arată doar numele și accesul la Scena ta.'))
    with st.expander(tr(locale, '3. Подготовить для Facebook или Instagram', '3. Pregătește pentru Facebook sau Instagram')):
        from scena_social_ui import render_social_workspace
        render_social_workspace(db_path, app_dir, settings, locale, selected)
