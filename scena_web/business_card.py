"""Public card routes read only the independent, owner-approved card data."""
import asyncio
import os
from pathlib import Path

from tornado.web import HTTPError, RequestHandler, StaticFileHandler
from tornado.httpclient import AsyncHTTPClient, HTTPClientError

from scena_business_card import get_card, photo_source, portrait_bytes, render_card, vcard

CARD_ROOT = Path(__file__).resolve().parents[1] / 'public' / 'card'
CSP = ("default-src 'self'; img-src 'self' data: https://*.public.blob.vercel-storage.com; "
       "script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; "
       "frame-ancestors 'self'; connect-src 'self'; worker-src 'self'; manifest-src 'self'")


def public_headers(handler):
    handler.set_header('X-Content-Type-Options', 'nosniff')
    handler.set_header('X-Robots-Tag', 'noindex, follow')
    handler.set_header('Referrer-Policy', 'strict-origin-when-cross-origin')
    handler.set_header('Content-Security-Policy', CSP)


class CardRedirect(RequestHandler):
    def get(self):
        query = '?' + self.request.query if self.request.query else ''
        self.redirect('/card/' + query, status=308)

    def head(self):
        self.get()


class CardContent(RequestHandler):
    def initialize(self, db_path=None, app_dir=None):
        self.database = db_path
        self.app_dir = app_dir

    async def prepare(self):
        if self.database is None:
            from .bootstrap import initialize
            await asyncio.to_thread(initialize)
            self.database = os.environ['SCENA_DB_PATH']
        self.app_dir = self.app_dir or os.environ.get('SCENA_APP_DIR', CARD_ROOT.parents[1])
        public_headers(self)
        self.set_header('Cache-Control', 'no-store')

    async def get(self, resource=None):
        card = await asyncio.to_thread(get_card, self.database)
        if resource == 'mbstudio.vcf':
            self.set_header('Content-Type', 'text/vcard; charset=utf-8')
            self.set_header('Content-Disposition', 'attachment; filename="MBStudio.vcf"')
            self.finish(vcard(card))
        elif resource == 'portrait.webp':
            try:
                source = await asyncio.to_thread(photo_source, self.database, self.app_dir, card)
                if isinstance(source, str):
                    # Same-origin bytes let the installed card refresh its offline
                    # portrait without cross-origin/opaque cache dependencies.
                    response = await AsyncHTTPClient().fetch(source, request_timeout=15)
                    image = response.body
                else:
                    image = await asyncio.to_thread(portrait_bytes, source)
            except (OSError, ValueError, HTTPClientError):
                raise HTTPError(404, reason='Card portrait unavailable') from None
            self.set_header('Content-Type', 'image/webp')
            self.finish(image)
        else:
            self.set_header('Content-Type', 'text/html; charset=utf-8')
            self.finish(await asyncio.to_thread(render_card, card))

    async def head(self, resource=None):
        await self.get(resource)


class BusinessCardAssets(StaticFileHandler):
    def set_extra_headers(self, path):
        # Stable filenames must revalidate after a deployment.
        self.set_header('Cache-Control', 'public, max-age=0, must-revalidate')
        public_headers(self)
        suffix = Path(path).suffix.lower()
        types = {'.webmanifest': 'application/manifest+json; charset=utf-8',
                 '.webp': 'image/webp', '.woff2': 'font/woff2'}
        if suffix in types:
            self.set_header('Content-Type', types[suffix])
        if Path(path).name == 'sw.js':
            self.set_header('Service-Worker-Allowed', '/card/')


def card_routes(*, db_path=None, app_dir=None):
    return [
        (r'/card', CardRedirect),
        (r'/card/(index\.html|mbstudio\.vcf|portrait\.webp)?', CardContent,
         {'db_path': db_path, 'app_dir': app_dir}),
        (r'/card/(.*)', BusinessCardAssets, {'path': str(CARD_ROOT)}),
    ]
