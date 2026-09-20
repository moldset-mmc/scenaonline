"""Serve the approved, public MBStudio card without touching owner data."""
from pathlib import Path

from tornado.web import RequestHandler, StaticFileHandler


CARD_ROOT = Path(__file__).resolve().parents[1] / 'public' / 'card'


class CardRedirect(RequestHandler):
    def get(self):
        query = '?' + self.request.query if self.request.query else ''
        self.redirect('/card/' + query, status=308)

    def head(self):
        self.get()


class BusinessCardAssets(StaticFileHandler):
    def set_extra_headers(self, path):
        # These are stable filenames, so they must revalidate after an update.
        self.set_header('Cache-Control', 'public, max-age=0, must-revalidate')
        self.set_header('X-Content-Type-Options', 'nosniff')
        self.set_header('X-Robots-Tag', 'noindex, follow')
        self.set_header('Content-Security-Policy',
                        "default-src 'self'; img-src 'self' data:; "
                        "script-src 'self'; style-src 'self'; "
                        "object-src 'none'; base-uri 'none'; "
                        "frame-ancestors 'none'; connect-src 'self'; "
                        "worker-src 'self'; manifest-src 'self'")
        suffix = Path(path).suffix.lower()
        if suffix == '.webmanifest':
            self.set_header('Content-Type', 'application/manifest+json; charset=utf-8')
        elif suffix == '.vcf':
            self.set_header('Content-Type', 'text/vcard; charset=utf-8')
        elif suffix == '.webp':
            # Minimal production containers may lack the system MIME database.
            self.set_header('Content-Type', 'image/webp')
        if Path(path).name == 'sw.js':
            self.set_header('Service-Worker-Allowed', '/card/')


def card_routes():
    return [
        (r'/card', CardRedirect),
        (r'/card/(.*)', BusinessCardAssets,
         {'path': str(CARD_ROOT), 'default_filename': 'index.html'}),
    ]
