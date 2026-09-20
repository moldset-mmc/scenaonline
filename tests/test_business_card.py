"""HTTP integration for the isolated public card and installable resources."""
import json
import unittest

from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application, RequestHandler

from scena_web.business_card import card_routes


class ExistingRoute(RequestHandler):
    def get(self):
        self.write('existing route')


class BusinessCardTests(AsyncHTTPTestCase):
    def get_app(self):
        return Application([*card_routes(), (r'/ru/', ExistingRoute)])

    def test_card_and_trailing_slash(self):
        response = self.fetch('/card?utm_source=nfc', follow_redirects=False)
        self.assertEqual(response.code, 308)
        self.assertEqual(response.headers['Location'], '/card/?utm_source=nfc')
        page = self.fetch('/card/')
        self.assertEqual(page.code, 200)
        self.assertIn('Маша'.encode(), page.body)
        self.assertEqual(page.headers['X-Robots-Tag'], 'noindex, follow')
        self.assertNotIn('immutable', page.headers['Cache-Control'])

    def test_installation_resources_and_scope(self):
        response = self.fetch('/card/manifest.webmanifest')
        self.assertEqual(response.code, 200)
        self.assertIn('application/manifest+json', response.headers['Content-Type'])
        manifest = json.loads(response.body)
        self.assertEqual(manifest['scope'], './')
        self.assertEqual(manifest['start_url'], './')
        for path in ('app.js', 'style.css', 'assets/portrait.webp', 'assets/qr.svg',
                     'assets/icon-192.png', 'assets/icon-512.png', 'mbstudio.vcf'):
            with self.subTest(path=path):
                self.assertEqual(self.fetch('/card/' + path).code, 200)
        worker = self.fetch('/card/sw.js')
        self.assertEqual(worker.code, 200)
        self.assertIn('javascript', worker.headers['Content-Type'])
        self.assertEqual(worker.headers['Service-Worker-Allowed'], '/card/')
        self.assertIn('text/vcard', self.fetch('/card/mbstudio.vcf').headers['Content-Type'])

    def test_head_and_conditional_request(self):
        response = self.fetch('/card/', method='HEAD')
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body, b'')
        etag = self.fetch('/card/app.js').headers['Etag']
        self.assertEqual(self.fetch('/card/app.js', headers={'If-None-Match': etag}).code, 304)

    def test_missing_files_and_directory_escape(self):
        self.assertEqual(self.fetch('/card/missing.js').code, 404)
        self.assertEqual(self.fetch('/card/%2e%2e/%2e%2e/scena_core.py').code, 403)
        self.assertEqual(self.fetch('/ru/').body, b'existing route')


if __name__ == '__main__':
    unittest.main()
