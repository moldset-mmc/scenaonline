"""Reversible public URL mapping. Private routes keep their query-based contract."""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

LANGUAGES = ('ru', 'ro', 'en')
SLUGS = {
    'scene': ('', '', ''),
    'professional': ('makiyazh', 'machiaj', 'makeup'),
    'model': ('model', 'model', 'model'),
    'booking': ('zapis', 'programare', 'booking'),
    'join-model': ('stat-modelyu', 'devino-model', 'become-a-model'),
    'invite-model': ('priglasit-model', 'invita-modelul', 'invite-a-model'),
    'shop': ('market', 'market', 'market'),
    'portfolio': ('portfolio', 'portofoliu', 'portfolio'),
    'posts': ('publikatsii', 'publicatii', 'publications'),
    'post': ('istoriya', 'poveste', 'story'),
    'course': ('kurs', 'curs', 'course'),
}


def enabled(settings):
    return str(settings.get('seo_pretty_urls', '0')) == '1'


def public_path(query):
    values = {str(k): str(v) for k, v in query.items() if v is not None}
    page, lang = values.get('page', 'scene'), values.get('lang')
    if page not in SLUGS or lang not in LANGUAGES or values.get('admin') == '1':
        return '/?' + urlencode(values)
    slug = SLUGS[page][LANGUAGES.index(lang)]
    parts = [lang] + ([slug] if slug else [])
    used = {'page', 'lang'}
    if page in ('portfolio', 'posts'):
        key = 'view' if page == 'portfolio' else 'destination'
        value = values.get(key, 'professional' if page == 'portfolio' else 'scene')
        if value not in (('professional', 'model') if page == 'portfolio' else ('scene', 'professional', 'model')):
            return '/?' + urlencode(values)
        parts.append(value)
        used.add(key)
    if page in ('course', 'post') or (page == 'booking' and values.get('service')):
        key = 'post' if page == 'post' else 'service'
        value = values.get(key, '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
            return '/?' + urlencode(values)
        parts.append(value)
        used.add(key)
    extra = urlencode({k: v for k, v in values.items() if k not in used})
    return '/' + '/'.join(parts) + '/' + ('?' + extra if extra else '')


def query_from_path(path):
    parts = path.strip('/').split('/')
    if not parts or parts[0] not in LANGUAGES:
        return None
    lang, rest = parts[0], parts[1:]
    if not rest:
        return {'page': 'scene', 'lang': lang}
    page = next((p for p, slugs in SLUGS.items() if slugs[LANGUAGES.index(lang)] == rest[0]), None)
    if not page:
        return None
    query = {'page': page, 'lang': lang}
    if page in ('portfolio', 'posts') and len(rest) == 2:
        choices = ('professional', 'model') if page == 'portfolio' else ('scene', 'professional', 'model')
        if rest[1] not in choices:
            return None
        query['view' if page == 'portfolio' else 'destination'] = rest[1]
    elif page in ('course', 'post', 'booking') and len(rest) == 2:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', rest[1]):
            return None
        query['post' if page == 'post' else 'service'] = rest[1]
    elif len(rest) != 1 or page in ('portfolio', 'posts', 'course', 'post'):
        return None
    return query


def rewrite_link(url, base=''):
    value = html.unescape(str(url))
    parsed = urlsplit(value)
    if parsed.netloc and parsed.netloc != urlsplit(base).netloc:
        return value
    if parsed.path not in ('', '/') or not parsed.query:
        return value
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if 'page' not in query:
        return value
    return public_path(query) + ('#' + parsed.fragment if parsed.fragment else '')


def rewrite_links(document, base=''):
    # Attribute values only, never script contents, form values or user text.
    chunks = re.split(r'(<script\b[^>]*>.*?</script\s*>|<style\b[^>]*>.*?</style\s*>)', document, flags=re.I | re.S)
    for i in range(0, len(chunks), 2):
        chunks[i] = re.sub(r'\bhref=([\"\'])(.*?)\1',
                          lambda m: 'href=' + m[1] + html.escape(rewrite_link(m[2], base), quote=True) + m[1],
                          chunks[i], flags=re.I)
    return ''.join(chunks)
