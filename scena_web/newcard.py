"""Independent SCENA platform card; no salon database or session bootstrap."""
from functools import lru_cache
from pathlib import Path

from tornado.web import RequestHandler, StaticFileHandler

ROOT = Path(__file__).resolve().parents[1] / 'public' / 'newcard'
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'self'; form-action 'self'")


def headers(handler):
    handler.set_header('X-Content-Type-Options', 'nosniff')
    handler.set_header('X-Robots-Tag', 'noindex, follow')
    handler.set_header('Referrer-Policy', 'strict-origin-when-cross-origin')
    handler.set_header('Content-Security-Policy', CSP)


@lru_cache(maxsize=1)
def document():
    return (ROOT / 'index.html').read_bytes()


class NewCard(RequestHandler):
    def get(self):
        if self.request.path.endswith('/'):
            query = '?' + self.request.query if self.request.query else ''
            self.redirect('/newcard' + query, status=308)
            return
        headers(self)
        self.set_header('Content-Type', 'text/html; charset=utf-8')
        self.set_header('Cache-Control', 'public, max-age=0, must-revalidate')
        self.finish(document())

    def head(self):
        self.get()


class NewCardAssets(StaticFileHandler):
    def set_extra_headers(self, path):
        headers(self)
        self.set_header('Cache-Control', 'public, max-age=31536000, immutable')


class NewCardGallery(RequestHandler):
    def get(self, identifier=None):
        headers(self)
        self.set_header('Cache-Control', 'no-store')
        self.set_header('X-Robots-Tag', 'noindex, nofollow')
        self.set_header('Referrer-Policy', 'no-referrer')
        name = 'gallery.html' if identifier else 'gallery.js'
        self.set_header('Content-Type', 'text/html; charset=utf-8' if identifier else 'text/javascript; charset=utf-8')
        self.finish((ROOT / name).read_bytes())


def newcard_routes():
    return [
        (r'/newcard/?', NewCard),
        (r'/newcard/photos/([a-f0-9-]{36})', NewCardGallery),
        (r'/newcard/gallery.js', NewCardGallery),
        (r'/newcard/assets/(.*)', NewCardAssets, {'path': str(ROOT / 'assets')}),
    ]
