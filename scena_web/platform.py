"""SCENA platform public documents, isolated from MB Studio settings and data.

The reviewed QR page is retained as a source artifact. Only deployment metadata,
URL language selection and the offline preview wrapper change at response time.
"""
from functools import lru_cache
import hashlib
import html
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode

from tornado.routing import Matcher, Rule
from tornado.web import RequestHandler

ORIGIN = 'https://scena.life'
ROOT = Path(__file__).resolve().parents[1] / 'public' / 'platform' / 'index.html'
INDEX = 'index, follow, max-image-preview:large'
NOINDEX = 'noindex, follow'
PAGES = {'/': 'ro', '/ru/': 'ru'}
DESCRIPTIONS = {
    'ro': 'SCENA.LIFE — un spațiu pentru frumusețe, conexiuni și afacerea ta. Descoperă platforma și creează gratuit Scena mea — image card personală, fără înregistrare.',
    'ru': 'SCENA.LIFE — пространство для образа, знакомств и дела. Познакомьтесь с платформой и создайте свою личную image card бесплатно, без регистрации.',
}


class PlatformReadMatcher(Matcher):
    def match(self, request):
        if request.method not in ('GET', 'HEAD'):
            return None
        # Retain explicit legacy salon/query links and private actions.
        query = dict(parse_qsl(request.query, keep_blank_values=True))
        if request.path == '/' and (query.get('page', 'scene') != 'scene' or query.get('admin') == '1'):
            return None
        if request.path in ('/', '/robots.txt', '/sitemap.xml', '/llms.txt') or re.fullmatch(r'/(ro|ru|en)(/newcard)?/?', request.path):
            return {}
        return None


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Reviewed platform artifact changed; rebuild and review the integration')
    return text.replace(old, new, 1)


@lru_cache(maxsize=2)
def document(locale):
    path = '/ru/' if locale == 'ru' else '/'
    source = ROOT.read_bytes()
    if hashlib.sha256(source).hexdigest() != 'ffde651f189c785475e68b207683130a9e16b1b58e80485fd73567cabbc400dc':
        raise RuntimeError('Platform source differs from the reviewed QR v1 artifact')
    markup = source.decode('utf-8')
    markup = replace_once(markup, '<html lang="ro">', f'<html lang="{locale}">')
    markup = replace_once(markup, 'content="noindex,follow"', f'content="{INDEX}"')
    markup = replace_once(markup, '<link rel="canonical" href="https://scena.life/newcard">', '<link rel="canonical" href="'+ORIGIN+path+'">')
    markup = replace_once(markup, '<meta property="og:url" content="https://scena.life/newcard">', '<meta property="og:url" content="'+ORIGIN+path+'">')
    markup = re.sub(r'<meta name="description" content="[^"]*">', '<meta name="description" content="'+html.escape(DESCRIPTIONS[locale], quote=True)+'">', markup, count=1)
    title = 'SCENA.LIFE — у каждого своя сцена' if locale == 'ru' else 'SCENA.LIFE — fiecare are scena sa'
    markup = re.sub(r'<title>[^<]*</title>', '<title>'+title+'</title>', markup, count=1)
    markup = re.sub(r'<meta property="og:title" content="[^"]*">', '<meta property="og:title" content="'+title+'">', markup, count=1)
    markup = re.sub(r'<meta name="twitter:title" content="[^"]*">', '<meta name="twitter:title" content="'+title+'">', markup, count=1)
    markup = re.sub(r'<meta property="og:description" content="[^"]*">', '<meta property="og:description" content="'+html.escape(DESCRIPTIONS[locale],quote=True)+'">', markup, count=1)
    markup = re.sub(r'<meta name="twitter:description" content="[^"]*">', '<meta name="twitter:description" content="'+html.escape(DESCRIPTIONS[locale],quote=True)+'">', markup, count=1)
    markup = markup.replace('content="ro_MD"', 'content="ru_MD"' if locale == 'ru' else 'content="ro_MD"', 1)
    alternates = ''.join(f'<link rel="alternate" hreflang="{lang}" href="{ORIGIN}{url}">' for lang,url in [('ro','/'),('ru','/ru/'),('x-default','/')])
    # Exported-card templates also contain a closing head tag inside JS strings.
    markup = markup.replace('</head>', alternates+'</head>', 1)
    # Production uses the existing same-origin intake API, never a mocked success.
    start = markup.index('<script>window.__SCENA_PREVIEW__=true;')
    finish = markup.index('"use strict";', start)
    markup = markup[:start] + '<script>' + markup[finish:]
    markup = markup.replace("connect-src 'none';", "connect-src 'self';", 1)
    markup = replace_once(markup,
        'function eC(){try{return localStorage.getItem(Zg)==="ru"?"ru":"ro"}catch{return"ro"}}',
        'function eC(){return document.documentElement.lang==="ru"?"ru":"ro"}')
    markup = replace_once(markup, 'value:{locale:a,setLocale:t,t:(l,u)=>ot(a,l,u)}',
        'value:{locale:a,setLocale:l=>window.location.assign(l==="ru"?"/ru/":"/"),t:(l,u)=>ot(a,l,u)}')
    # Keep the React mount empty so a slow script cannot expose a text-only page.
    heading = 'Всегда на сцене' if locale == 'ru' else 'Mereu pe scenă'
    instruction = ('Включите JavaScript, чтобы создать свою image card.' if locale == 'ru'
                   else 'Activează JavaScript pentru a crea image card personală.')
    fallback = (
        f'<noscript><main><h1>{heading}</h1><p>{html.escape(DESCRIPTIONS[locale])}</p>'
        f'<p>{instruction}</p><nav aria-label="Language">'
        '<a href="/" lang="ro" hreflang="ro">Română</a> '
        '<a href="/ru/" lang="ru" hreflang="ru">Русский</a></nav></main></noscript>'
    )
    markup = replace_once(markup,
        '<noscript>Activează JavaScript pentru a descoperi SCENA.LIFE și a crea image card personală.</noscript>',
        fallback)
    return markup.encode('utf-8')


class PlatformDocument(RequestHandler):
    def get(self):
        path = self.request.path
        self.set_header('X-Content-Type-Options', 'nosniff')
        self.set_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.set_header('Cache-Control', 'public, max-age=0, must-revalidate')
        self.set_header('X-Robots-Tag', NOINDEX)
        query = dict(parse_qsl(self.request.query, keep_blank_values=True))
        if path in ('/ro', '/ro/') or path == '/ru':
            target = '/ru/' if path == '/ru' else '/'
            self.redirect(target + ('?' + self.request.query if self.request.query else ''), status=308)
            return
        if path == '/' and query.get('lang') in ('ro', 'ru'):
            target = '/ru/' if query['lang'] == 'ru' else '/'
            remaining = [(k,v) for k,v in parse_qsl(self.request.query,keep_blank_values=True) if k != 'lang']
            self.redirect(target + ('?' + urlencode(remaining) if remaining else ''), status=308)
            return
        if path == '/robots.txt':
            self.set_header('Content-Type', 'text/plain; charset=utf-8')
            self.finish('User-agent: *\nAllow: /\nDisallow: /auth/\nDisallow: /api/\nDisallow: /scena-download/\nDisallow: /scena-upload\nDisallow: /scena-photo/\nDisallow: /scena-telegram\nDisallow: /healthz\nDisallow: /newcard/photos/\nDisallow: /*?*page=admin\nDisallow: /*?*admin=1\n\nSitemap: '+ORIGIN+'/sitemap.xml\n')
            return
        if path == '/sitemap.xml':
            self.set_header('Content-Type', 'application/xml; charset=utf-8')
            alternates = ''.join(f'<xhtml:link rel="alternate" hreflang="{lang}" href="{ORIGIN}{url}" />' for lang,url in [('ro','/'),('ru','/ru/'),('x-default','/')])
            self.finish('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">'+''.join('<url><loc>'+ORIGIN+url+'</loc>'+alternates+'</url>' for url in PAGES)+'<url><loc>'+ORIGIN+'/newcard</loc></url></urlset>')
            return
        if path == '/llms.txt':
            self.set_header('Content-Type', 'text/plain; charset=utf-8')
            self.finish('# SCENA.LIFE\n\nPlatforma SCENA.LIFE.\n\n- [Română]('+ORIGIN+'/)\n- [Русский]('+ORIGIN+'/ru/)\n- [New card]('+ORIGIN+'/newcard)\n')
            return
        if path not in PAGES:
            # No fictitious English translation or duplicate localized intake page.
            self.set_status(404)
            self.set_header('Content-Type', 'text/html; charset=utf-8')
            self.finish('<!doctype html><html lang="en"><head><meta name="robots" content="noindex,follow"><title>SCENA.LIFE</title></head><body><h1>Page not available</h1><a href="/">Română</a> <a href="/ru/">Русский</a></body></html>')
            return
        self.set_header('Content-Type', 'text/html; charset=utf-8')
        self.set_header('X-Robots-Tag', INDEX)
        self.finish(document(PAGES[path]))

    def head(self):
        self.get()


def platform_rules():
    return [Rule(PlatformReadMatcher(), PlatformDocument)]
