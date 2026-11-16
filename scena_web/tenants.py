"""Level-1 tenant documents served by the platform app.

A level-1 tenant ("визитка") lives in this repository and is mounted by host:
`<tenant>.scena.life` serves a static card from `public/tenants/<tenant>/`.
Level-2 tenants (a full site with its own database, accounts, booking and shop)
are deployed in the tenant's own Vercel and GitHub accounts; this module never
serves them and holds no credentials for them.
"""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from tornado.routing import Matcher
from tornado.web import RequestHandler

ROOT = Path(__file__).resolve().parents[1] / 'public' / 'tenants'

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'self'"
)

# host -> directory under public/tenants/
TENANTS = {
    'sofileroux.scena.life': 'sofileroux',
}

HOST_SAFE = re.compile(r'^[a-z0-9.-]+$')


class TenantMatcher(Matcher):
    """Every public read on a tenant host belongs to that tenant."""

    def match(self, request):
        if request.method not in ('GET', 'HEAD'):
            return None
        return {}


class TenantDocument(RequestHandler):
    """Serve one static document from the tenant directory."""

    def initialize(self, tenant):
        self.tenant = tenant

    def compute_etag(self):
        return None

    def get(self, path=None):
        if not HOST_SAFE.fullmatch(self.tenant):
            raise self._not_found()
        target = self._resolve(path)
        if target is None:
            raise self._not_found()

        self.set_header('X-Content-Type-Options', 'nosniff')
        # Demo tenants stay out of search results until the owner publishes them.
        self.set_header('X-Robots-Tag', 'noindex, nofollow')
        self.set_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.set_header('Content-Security-Policy', CSP)
        self.set_header('Cache-Control', 'public, max-age=0, must-revalidate')

        content_type, _ = mimetypes.guess_type(str(target))
        self.set_header('Content-Type', content_type or 'application/octet-stream')
        self.finish(target.read_bytes())

    def head(self, path=None):
        self.get(path)

    def _not_found(self):
        self.set_status(404)
        self.set_header('Content-Type', 'text/plain; charset=utf-8')
        return None

    def _resolve(self, path):
        base = (ROOT / self.tenant).resolve()
        name = (path or '').lstrip('/') or 'index.html'
        if name.endswith('/'):
            name += 'index.html'
        candidate = (base / name).resolve()
        if candidate != base and base not in candidate.parents:
            return None
        if candidate.is_dir():
            candidate = candidate / 'index.html'
        return candidate if candidate.is_file() else None


def tenant_hosts():
    """Host -> tenant mapping for the router."""
    return dict(TENANTS)
