"""The public platform card must not redirect to or initialize the salon."""
import re

from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application, RequestHandler

from scena_web.domain_redirect import with_legacy_redirects
from scena_web.newcard import newcard_routes


class ExistingPage(RequestHandler):
    def get(self):
        self.write('existing page')


class NewCardTests(AsyncHTTPTestCase):
    def get_app(self):
        return with_legacy_redirects(Application([
            *newcard_routes(), (r'/ru/', ExistingPage),
        ]))

    def test_apex_card_stays_on_platform_host_and_legacy_pages_keep_redirecting(self):
        page = self.fetch('/newcard', headers={'Host': 'scena.life'}, follow_redirects=False)
        self.assertEqual(page.code, 200)
        self.assertIn(b'https://scena.life/newcard', page.body)
        self.assertIn(b'SCENA.LIVE', page.body)
        self.assertNotIn('Set-Cookie', page.headers)
        self.assertEqual(self.fetch('/newcard', method='HEAD').body, b'')
        existing = self.fetch('/ru/', headers={'Host': 'scena.life'}, follow_redirects=False)
        self.assertEqual(existing.code, 308)
        self.assertEqual(existing.headers['Location'], 'https://mbstudio.scena.life/ru/')

    def test_slash_query_assets_and_no_writes(self):
        result = self.fetch('/newcard/?utm_source=telegram', follow_redirects=False)
        self.assertEqual(result.code, 308)
        self.assertEqual(result.headers['Location'], '/newcard?utm_source=telegram')
        page = self.fetch('/newcard')
        self.assertIn("script-src 'self'", page.headers['Content-Security-Policy'])
        self.assertIn('blob:', page.headers['Content-Security-Policy'])
        self.assertNotIn('immutable', page.headers['Cache-Control'])
        assets = re.findall(rb'(?:src|href)="(/newcard/assets/[^"]+)"', page.body)
        self.assertGreaterEqual(len(assets), 3)
        for url in assets:
            response = self.fetch(url.decode())
            self.assertEqual(response.code, 200)
            self.assertIn('immutable', response.headers['Cache-Control'])
        self.assertEqual(self.fetch('/newcard', method='POST', body='test=1').code, 405)
        self.assertEqual(self.fetch('/newcard/assets/%2e%2e/%2e%2e/scena_core.py').code, 403)
