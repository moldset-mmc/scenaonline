"""Runtime redirect for the legacy public host, including container deployments.

Only public GET/HEAD routes move. POST actions, Telegram webhooks, health checks
and private media/download endpoints retain their existing handlers.
"""
from __future__ import annotations

import asyncio
import os
import re
from tornado.routing import Matcher, Rule
from tornado.web import RequestHandler

LEGACY_HOST = "scenaonline.vercel.app"
PUBLIC_ORIGIN = "https://scena.life"
PUBLIC_DOCUMENTS = frozenset(("/", "/robots.txt", "/sitemap.xml", "/llms.txt"))


class PublicReadMatcher(Matcher):
    def match(self, request):
        if request.method in ("GET", "HEAD") and (
            request.path in PUBLIC_DOCUMENTS or request.path.startswith("/scena-assets/")
        ):
            return {}
        return None


class LegacyPublicRedirect(RequestHandler):
    def get(self):
        # request.uri retains path, query ordering, encoding and language.
        # The origin is a constant, never a forwarded Host or user parameter.
        self.set_header("Cache-Control", "public, max-age=300")
        self.redirect(PUBLIC_ORIGIN + self.request.uri, status=308)

    def head(self):
        self.get()


def with_legacy_redirects(application):
    application.add_handlers(re.escape(LEGACY_HOST), [Rule(PublicReadMatcher(), LegacyPublicRedirect)])
    return application


async def serve():
    # Same startup contract as scena_web.server.serve, with routing installed
    # before listen. No changes to renderer, forms, authentication or persistence.
    from .server import application, bootstrap
    with_legacy_redirects(application()).listen(
        int(os.environ.get("PORT", "80")), address="0.0.0.0", max_buffer_size=4*1024*1024
    )
    await asyncio.to_thread(bootstrap.initialize)
    await asyncio.Event().wait()
