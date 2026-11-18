"""Template sites: one system, many visual worlds.

Every template is a directory under `public/templates/<name>/` with an
`index.html` that talks to the platform API (booking, cards). Templates share
the system and differ only in style, so a new salon is a new skin, not a new
build.
"""
from __future__ import annotations

from pathlib import Path

from tornado.web import RequestHandler

ROOT = Path(__file__).resolve().parents[1] / 'public' / 'templates'
TEMPLATES = {'tulip'}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
       "form-action 'self'; frame-ancestors 'self'")


class TemplatePage(RequestHandler):
    def initialize(self, name):
        self.name = name

    def get(self):
        if self.name not in TEMPLATES:
            raise self._not_found()
        index = ROOT / self.name / 'index.html'
        if not index.is_file():
            raise self._not_found()
        self.set_header('Content-Type', 'text/html; charset=utf-8')
        self.set_header('Cache-Control', 'public, max-age=0, must-revalidate')
        self.set_header('X-Robots-Tag', 'noindex, nofollow')
        self.set_header('X-Content-Type-Options', 'nosniff')
        self.set_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.set_header('Content-Security-Policy', CSP)
        self.finish(index.read_bytes())

    def head(self):
        self.get()

    def _not_found(self):
        self.set_status(404)
        self.set_header('Content-Type', 'text/plain; charset=utf-8')
        self.finish('Template not found')


def template_routes():
    return [(rf'/{name}/?', TemplatePage, {'name': name}) for name in sorted(TEMPLATES)]
