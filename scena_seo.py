"""Public-only search metadata and discovery documents. No writes or network calls.

URLs are rebuilt from an allowlist, never from a request Host/header or a saved
form. Structured data contains the same published copy as public pages; drafts,
orders, contacts submitted by clients, and private media are never queried.
"""
from __future__ import annotations

import html
import ipaddress
import json
import re
import sqlite3
from urllib.parse import urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from scena_database import connect
from scena_i18n import LOCALES, content_text, localized_name, normalize_locale, service_description, service_name, tr

PUBLIC_PAGES = frozenset(('scene', 'professional', 'model', 'portfolio', 'booking', 'course',
                          'join-model', 'invite-model', 'posts', 'post', 'shop'))
INDEX = 'index, follow, max-image-preview:large'
NOINDEX = 'noindex, nofollow'
PAGE_NAMES = {
    'scene': ('Моя Сцена', 'Scena mea', 'My Scene'),
    'professional': ('Макияж и услуги', 'Machiaj și servicii', 'Makeup and services'),
    'model': ('Модель · знакомство', 'Model · prezentare', 'Model · introduction'),
    'portfolio': ('Портфолио', 'Portofoliu', 'Portfolio'),
    'booking': ('Запись на услуги', 'Programare la servicii', 'Book a service'),
    'course': ('Курс', 'Curs', 'Course'),
    'join-model': ('Стать моделью', 'Devino model', 'Become a model'),
    'invite-model': ('Пригласить модель', 'Invită modelul', 'Invite the model'),
    'posts': ('Публикации', 'Publicații', 'Publications'),
    'post': ('Публикация', 'Publicație', 'Publication'),
    'shop': ('Market · косметика и инструменты', 'Market · cosmetice și instrumente', 'Market · cosmetics and tools'),
}


def public_base(settings):
    """Accept only a configured public HTTPS origin/path; invalid is fail closed."""
    value = str(settings.get('public_base_url') or '').strip()
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ''
        port = parsed.port
        if (parsed.scheme != 'https' or not host or parsed.username or parsed.password
                or port not in (None, 443) or '\\' in value or re.search(r'[\x00-\x20]', value)
                or host in ('localhost', 'localhost.localdomain') or '.' not in host
                or host.endswith(('.localhost', '.local', '.internal'))):
            return ''
        try:
            if not ipaddress.ip_address(host).is_global:
                return ''
        except ValueError:
            pass
        if any(part in ('.', '..') for part in parsed.path.split('/')):
            return ''
        return urlunsplit(('https', parsed.netloc.lower(), parsed.path.rstrip('/'), '', ''))
    except (ValueError, TypeError):
        return ''


def _text(value, limit=180):
    # Owner copy remains text, not executable markup or a second metadata tag.
    value = html.unescape(re.sub(r'<[^>]*>', ' ', str(value or '')))
    value = ' '.join(value.split())
    return value if len(value) <= limit else value[:limit - 1].rsplit(' ', 1)[0].rstrip(' .,;:') + '…'


def _url(base, page, locale, params=None, *, pretty=False):
    if not base:
        return ''
    query = {'page': page, 'lang': locale, **(params or {})}
    if pretty:
        from scena_urls import public_path
        return base + public_path(query)
    return base + '/?' + urlencode(query)


def _published(settings, area):
    prefix = 'profile' if area == 'scene' else area
    return str(settings.get(prefix + '_published', '1')) == '1'


def _enabled(settings, area):
    prefix = 'profile' if area == 'scene' else area
    return _published(settings, area) and str(settings.get(prefix + '_indexed', '1')) == '1'


def _read_public(db_path):
    result = {'services': [], 'posts': []}
    if db_path is None:
        return result
    con = connect(db_path, timeout=10)
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('services','service_groups','publication_records','posts')")}
        if {'services', 'service_groups'} <= tables:
            cursor = con.execute("""SELECT s.* FROM services s LEFT JOIN service_groups g ON g.id=s.group_id
                WHERE s.active=1 AND s.archived=0 AND (g.id IS NULL OR g.active=1)
                ORDER BY s.sort_order,s.id""")
            keys = [column[0] for column in cursor.description]
            result['services'] = [dict(zip(keys, row)) for row in cursor]
        if {'publication_records', 'posts'} <= tables:
            # updated_at can reflect an unpublished draft. Do not use it as a
            # public dateModified or sitemap lastmod. No invented timestamps.
            cursor = con.execute("""SELECT r.public_id,r.published_json,p.created_at FROM publication_records r
                JOIN posts p ON p.id=r.post_id WHERE r.status='published' AND r.public_revision>0
                AND r.published_json IS NOT NULL ORDER BY r.public_id""")
            for public_id, snapshot, created in cursor:
                try:
                    post = json.loads(snapshot)
                except (ValueError, TypeError):
                    continue
                if not isinstance(post, dict):
                    continue
                # Explicit public projection: never propagate originals or new
                # private fields merely because they appear in a snapshot.
                fields = ('title_ru', 'title_ro', 'title_en', 'body_ru', 'body_ro', 'body_en',
                          'image_url', 'show_scene', 'show_professional', 'show_model')
                result['posts'].append({**{key: post.get(key, '') for key in fields},
                                        'public_id': str(public_id), 'created_at': created})
        return result
    finally:
        con.close()


def _post_visible(settings, post):
    return bool(post) and _published(settings, 'scene') and any(
        post.get('show_' + area) and _published(settings, area) for area in ('scene', 'professional', 'model'))


def _image_url(value, base, resolver=None):
    value = str(value or '').strip()
    if resolver and value:
        value = str(resolver(value) or '')
    if value.startswith('/') and not value.startswith('//'):
        value = base + value
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            return ''
        if re.search(r'[\x00-\x20<>\\]', value) or parsed.fragment:
            return ''
        # Signed original/owner endpoints are not social images.
        if '/scena-photo/' in parsed.path or '/private' in parsed.path:
            return ''
        return value
    except ValueError:
        return ''


def _safe_same_as(settings):
    return [url for key in ('instagram_url', 'telegram_url')
            if (url := _image_url(settings.get(key), ''))]


def _descriptor(settings, query, locale, data, resolver=None):
    lang = normalize_locale(locale)
    base = public_base(settings)
    from scena_urls import enabled
    route = lambda page, lang, params=None: _url(base, page, lang, params, pretty=enabled(settings))
    page = str(query.get('page', 'scene'))
    known = page in PUBLIC_PAGES and str(query.get('admin', '')) != '1'
    safe_page = page if known else 'scene'
    params = {}
    area = 'scene'
    invalid = False
    if page in ('professional', 'booking', 'course'):
        area = 'professional'
    elif page in ('model', 'join-model', 'invite-model'):
        area = 'model'
    elif page == 'portfolio':
        area = str(query.get('view', 'professional'))
        invalid = area not in ('professional', 'model')
        if not invalid:
            params['view'] = area
    elif page == 'posts':
        area = str(query.get('destination', 'scene'))
        invalid = area not in ('scene', 'professional', 'model')
        if not invalid:
            params['destination'] = area
    course = None
    post = None
    if page == 'course':
        course = next((row for row in data['services'] if str(row['id']) == str(query.get('service'))
                       and row['category'] == 'Professional' and row['kind'] == 'course'), None)
        invalid = not course
        if course:
            params['service'] = str(course['id'])
    if page == 'post':
        post = next((row for row in data['posts'] if row['public_id'] == str(query.get('post'))), None)
        invalid = not _post_visible(settings, post)
        if post:
            params['post'] = post['public_id']
    # Tracking is intentionally dropped; private/form/context data is never
    # advertised as a separate searchable URL or copied into canonical URLs.
    allowed = {'page', 'lang', 'view', 'destination', 'service', 'post', 'utm_source',
               'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'gclid', 'fbclid', '_ym_debug'}
    private_query = any(key not in allowed for key in query)
    visible = known and not invalid and _published(settings, area)
    if page in ('post', 'posts'):
        visible = visible and _published(settings, 'scene')
    if page == 'shop':
        visible = known and not invalid and str(settings.get('shop_enabled', '1')) == '1'
    status = 200 if visible or page == 'admin' or str(query.get('admin', '')) == '1' else 404
    indexable = bool(base and visible and not private_query and _enabled(settings, area))
    if page in ('posts', 'post'):
        indexable = indexable and _enabled(settings, 'scene')
    if page == 'post' and post:
        indexable = indexable and any(post.get('show_' + place) and _enabled(settings, place)
                                      for place in ('scene', 'professional', 'model'))
    if page == 'shop':
        indexable = indexable and str(settings.get('shop_enabled', '1')) == '1'
    if settings.get('seo_empty_sections_noindex') == '1':
        if page == 'posts':
            indexable = indexable and any(p.get('show_' + area) and _text(p.get('body_' + lang)) for p in data['posts'])
        elif page == 'portfolio' and not invalid:
            from scena_portfolio import effective_slots
            indexable = indexable and any(effective_slots(settings, area).values())
    name = _text(localized_name(settings, lang), 100)
    place = _text(content_text(settings, 'location', lang), 80)
    label = tr(lang, *PAGE_NAMES[safe_page])
    description = ''
    image = ''
    if known and not invalid:
        if page == 'scene':
            description = content_text(settings, 'bio', lang)
            image = settings.get('avatar_url') or settings.get('scene_hero_image')
        elif page in ('professional', 'portfolio'):
            description = content_text(settings, 'model_desc' if area == 'model' else 'beauty_desc', lang)
            if page == 'professional':
                label = content_text(settings, 'beauty_title', lang) or label
            else:
                label += ' · ' + tr(lang, 'Model' if area == 'model' else 'Макияж', 'Model' if area == 'model' else 'Machiaj', 'Model' if area == 'model' else 'Makeup')
                description = tr(lang,
                    f'Модельное портфолио {name}: фотографии и образы для знакомства перед съёмкой.' if area == 'model' else f'Портфолио макияжа {name}: опубликованные образы для выбора перед записью.',
                    f'Portofoliul de model al {name}: fotografii pentru a o cunoaște înaintea unei ședințe foto.' if area == 'model' else f'Portofoliul de machiaj al {name}: lookuri publicate pentru alegerea imaginii înainte de programare.',
                    f'Modelling portfolio of {name}: photographs and looks to explore before a shoot.' if area == 'model' else f'Makeup portfolio of {name}: published looks to explore before booking.')
            image = (settings.get('model_image_1') or settings.get('model_intro_image')) if area == 'model' else (settings.get('professional_cover_image') or settings.get('beauty_image_1') or settings.get('professional_hero_image'))
        elif page == 'model':
            description = content_text(settings, 'model_intro_text', lang) if settings.get('model_intro_enabled', '1') == '1' else content_text(settings, 'model_desc', lang)
            image = settings.get('model_intro_image') or settings.get('model_slide_1_image')
        elif page == 'booking':
            description = content_text(settings, 'booking_description', lang)
            image = settings.get('professional_hero_image')
        elif page == 'course' and course:
            label, description = service_name(course, lang), service_description(course, lang)
            image = settings.get('course_cover_image') or settings.get('professional_hero_image')
        elif page == 'join-model':
            description = tr(lang, 'Анкета модели: город, опыт и контакты для связи.', 'Formular de model: oraș, experiență și date de contact.', 'Model application: city, experience and contact details.')
        elif page == 'invite-model':
            description = tr(lang, 'Предложите модели съёмку или проект. Укажите формат, сроки и контакты.', 'Propuneți modelului o ședință foto sau un proiect. Indicați formatul, perioada și contactele.', 'Invite the model to a shoot or project. Share the format, dates and contact details.')
        elif page == 'posts':
            label += ' · ' + tr(lang, *PAGE_NAMES[area])
            descriptions = {
                'scene': ('Личные истории, фотографии и новости', 'Povești personale, fotografii și noutăți', 'Personal stories, photographs and updates'),
                'professional': ('Макияж, рабочие образы и новости мастера', 'Machiaj, lookuri și noutățile specialistului', 'Makeup looks and updates from the artist'),
                'model': ('Модельные образы, съёмки и творческие проекты', 'Lookuri de model, ședințe foto și proiecte creative', 'Modelling looks, shoots and creative projects'),
            }
            description = tr(lang, *descriptions[area]) + ' · ' + name + '.'
        elif page == 'post' and post:
            label = post.get('title_' + lang) or label
            description = post.get('body_' + lang, '')
            image = post.get('image_url')
        elif page == 'shop':
            label = content_text(settings, 'shop_title', lang) or label
            description = content_text(settings, 'shop_description', lang)
    title = _text(' · '.join(str(part) for part in (label, name, place) if part), 120)
    description = _text(' '.join(str(part) for part in (description, place) if part), 180)
    locales = tuple(language for language in LOCALES if not post or _text(post.get('body_' + language)))
    if post and lang not in locales:
        indexable = False
    canonical = route(safe_page, lang, params) if known and not invalid else ''
    alternates = {language: route(safe_page, language, params) for language in locales} if indexable else {}
    if alternates:
        default = normalize_locale(settings.get('default_locale', 'ro'))
        alternates['x-default'] = alternates.get(default) or next(iter(alternates.values()))
    if not visible or not known or private_query:
        # Avoid disclosure on hidden/private routes, while a published page
        # with owner-disabled indexing keeps its useful browser title.
        title = tr(lang, 'SCENA · Страница', 'SCENA · Pagină', 'SCENA · Page')
        description, image = '', ''
    image = _image_url(image, base, resolver) if indexable else ''
    metadata = {'page': safe_page, 'locale': lang, 'params': params, 'title': title,
                'description': description, 'canonical': canonical, 'alternates': alternates,
                'robots': INDEX if indexable else NOINDEX, 'indexable': indexable, 'status': status,
                'image': image, 'json_ld': {}}
    if not indexable:
        return metadata
    person = {'@type': 'Person', '@id': base + '/#person', 'name': name}
    if _enabled(settings, 'scene'):
        person['url'] = route('scene', lang)
    if _safe_same_as(settings):
        person['sameAs'] = _safe_same_as(settings)
    if image and page in ('scene', 'model'):
        person['image'] = image
    schema_type = 'ProfilePage' if page in ('scene', 'model') else 'CollectionPage' if page in ('portfolio', 'posts', 'shop') else 'WebPage'
    webpage = {'@type': schema_type, '@id': canonical + '#webpage', 'url': canonical,
               'name': title, 'description': description, 'inLanguage': lang}
    if place:
        webpage['spatialCoverage'] = {'@type': 'Place', 'name': place}
    website = {'@type': 'WebSite', '@id': base + '/#website', 'url': route('scene', lang), 'name': content_text(settings, 'beauty_title', lang) or name, 'inLanguage': list(LOCALES)}
    webpage['isPartOf'] = {'@id': website['@id']}
    breadcrumb = {'@type': 'BreadcrumbList', '@id': canonical + '#breadcrumb', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': tr(lang, 'Моя Сцена', 'Scena mea', 'My Scene'), 'item': route('scene', lang)}]}
    if page != 'scene':
        breadcrumb['itemListElement'].append({'@type': 'ListItem', 'position': 2, 'name': label, 'item': canonical})
    webpage['breadcrumb'] = {'@id': breadcrumb['@id']}
    graph = [website, person, webpage, breadcrumb]
    if page in ('scene', 'model'):
        webpage['mainEntity'] = {'@id': person['@id']}
    else:
        webpage['about'] = {'@id': person['@id']}
    if image:
        webpage['primaryImageOfPage'] = {'@type': 'ImageObject', 'url': image}
    if page == 'post' and post:
        article = {'@type': 'Article', '@id': canonical + '#article', 'headline': _text(label, 160),
                   'articleBody': str(post.get('body_' + lang) or ''), 'inLanguage': lang,
                   'author': {'@id': person['@id']}, 'mainEntityOfPage': {'@id': webpage['@id']}}
        if image:
            article['image'] = image
        # created_at is draft creation time, not first publication time. Omit.
        webpage['mainEntity'] = {'@id': article['@id']}
        graph.append(article)
    if page in ('professional', 'booking', 'course'):
        services = [course] if course else [row for row in data['services'] if row['category'] == 'Professional' and (page != 'booking' or row['kind'] == 'appointment')]
        for row in services:
            item = {'@type': 'Service', '@id': base + '/#service-' + str(row['id']),
                    'name': service_name(row, lang), 'description': service_description(row, lang),
                    'provider': {'@id': person['@id']},
                    'url': route('course' if row['kind'] == 'course' else 'booking', lang, {'service': row['id']})}
            if place:
                item['areaServed'] = {'@type': 'Place', 'name': place}
            graph.append(item)
        if services:
            webpage['mainEntity'] = [{'@id': base + '/#service-' + str(row['id'])} for row in services]
    metadata['json_ld'] = {'@context': 'https://schema.org', '@graph': graph}
    return metadata


def build_metadata(settings, query, locale, *, db_path=None, image_resolver=None):
    """Metadata for one route. Caller supplies real final locale after rendering."""
    page = str(query.get('page', 'scene'))
    data = _read_public(db_path) if page in ('course', 'post', 'posts', 'professional', 'booking') else {'services': [], 'posts': []}
    return _descriptor(settings, query, locale, data, image_resolver)


def render_head(metadata):
    esc = lambda value: html.escape(str(value), quote=True)
    tags = ['<title>' + esc(metadata['title']) + '</title>',
            '<meta name="robots" content="' + esc(metadata['robots']) + '">']
    for key, value in metadata.get('verification', {}).items():
        if key in ('google-site-verification', 'msvalidate.01', 'yandex-verification') and re.fullmatch(r'[A-Za-z0-9_-]{8,256}', str(value)):
            tags.append('<meta name="' + key + '" content="' + esc(value) + '">')
    if metadata['description']:
        tags.append('<meta name="description" content="' + esc(metadata['description']) + '">')
    if metadata['canonical']:
        tags.append('<link rel="canonical" href="' + esc(metadata['canonical']) + '">')
    for lang, url in metadata['alternates'].items():
        tags.append('<link rel="alternate" hreflang="' + esc(lang) + '" href="' + esc(url) + '">')
    if metadata['indexable']:
        properties = {'og:type': 'article' if metadata['page'] == 'post' else 'website',
                      'og:title': metadata['title'], 'og:description': metadata['description'],
                      'og:url': metadata['canonical'], 'og:site_name': 'SCENA',
                      'og:locale': {'ru': 'ru_MD', 'ro': 'ro_MD', 'en': 'en_US'}[metadata['locale']]}
        if metadata['image']:
            properties['og:image'] = metadata['image']
        tags += ['<meta property="' + esc(key) + '" content="' + esc(value) + '">' for key, value in properties.items()]
        twitter = {'twitter:card': 'summary_large_image' if metadata['image'] else 'summary',
                   'twitter:title': metadata['title'], 'twitter:description': metadata['description']}
        if metadata['image']:
            twitter['twitter:image'] = metadata['image']
        tags += ['<meta name="' + esc(key) + '" content="' + esc(value) + '">' for key, value in twitter.items()]
        payload = json.dumps(metadata['json_ld'], ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        tags.append('<script type="application/ld+json">' + payload + '</script>')
    return '\n'.join(tags)


def public_catalog(settings, *, db_path=None, image_resolver=None):
    data = _read_public(db_path)
    queries = [{'page': page} for page in ('scene', 'professional', 'model', 'booking', 'join-model', 'invite-model', 'shop')]
    queries += [{'page': 'portfolio', 'view': area} for area in ('professional', 'model')]
    queries += [{'page': 'posts', 'destination': area} for area in ('scene', 'professional', 'model')]
    queries += [{'page': 'course', 'service': str(row['id'])} for row in data['services'] if row['category'] == 'Professional' and row['kind'] == 'course']
    queries += [{'page': 'post', 'post': row['public_id']} for row in data['posts'] if _post_visible(settings, row)]
    return [item for query in queries for lang in LOCALES
            if (item := _descriptor(settings, query, lang, data, image_resolver))['indexable']]


def sitemap_xml(settings, *, db_path=None):
    ns, xhtml = 'http://www.sitemaps.org/schemas/sitemap/0.9', 'http://www.w3.org/1999/xhtml'
    ET.register_namespace('', ns)
    ET.register_namespace('xhtml', xhtml)
    root = ET.Element('{' + ns + '}urlset')
    for item in public_catalog(settings, db_path=db_path):
        node = ET.SubElement(root, '{' + ns + '}url')
        ET.SubElement(node, '{' + ns + '}loc').text = item['canonical']
        for lang, url in item['alternates'].items():
            ET.SubElement(node, '{' + xhtml + '}link', {'rel': 'alternate', 'hreflang': lang, 'href': url})
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode')


def robots_txt(settings):
    # Wildcard group applies to Google/Bing and AI search agents alike. Robots
    # controls crawling only: server authorization + noindex protect private URLs.
    lines = ['User-agent: *', 'Allow: /', 'Disallow: /auth/login', 'Disallow: /auth/logout',
             'Disallow: /scena-photo/', 'Disallow: /scena-download/',
             'Disallow: /scena-upload', 'Disallow: /scena-telegram', 'Disallow: /healthz',
             'Disallow: /*?*page=admin', 'Disallow: /*?*admin=1', '']
    base = public_base(settings)
    if base:
        lines.append('Sitemap: ' + base + '/sitemap.xml')
    return '\n'.join(lines) + '\n'


def llms_txt(settings, *, db_path=None):
    """Optional public directory, not a promise of AI inclusion or a standard gate."""
    catalog = public_catalog(settings, db_path=db_path)
    lines = ['# SCENA', '', '> Public page directory. Public content is available at the links below.', '']
    for lang in LOCALES:
        entries = [row for row in catalog if row['locale'] == lang]
        if entries:
            lines += ['## ' + lang.upper(), '']
        for item in entries:
            label = re.sub(r'[\[\]\\]', '', item['title'])
            lines.append('- [' + label + '](' + item['canonical'] + '): ' + item['description'])
        if entries:
            lines.append('')
    return '\n'.join(lines)
