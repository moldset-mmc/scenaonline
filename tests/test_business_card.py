"""HTTP integration for the isolated public card and installable resources."""
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from scena_core import init_db, save_settings
from scena_business_card import get_card, save_card

from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application, RequestHandler

from scena_web.business_card import card_routes


class ExistingRoute(RequestHandler):
    def get(self):
        self.write('existing route')


class BusinessCardTests(AsyncHTTPTestCase):
    def get_app(self):
        self.fixture = tempfile.TemporaryDirectory()
        self.addCleanup(self.fixture.cleanup)
        self.root = Path(self.fixture.name)
        self.db = self.root / 'card.db'
        init_db(self.db)
        return Application([*card_routes(db_path=self.db, app_dir=self.root), (r'/ru/', ExistingRoute)])

    def test_card_and_trailing_slash(self):
        response = self.fetch('/card?utm_source=nfc', follow_redirects=False)
        self.assertEqual(response.code, 308)
        self.assertEqual(response.headers['Location'], '/card/?utm_source=nfc')
        page = self.fetch('/card/')
        self.assertEqual(page.code, 200)
        self.assertIn('Маша'.encode(), page.body)
        self.assertEqual(page.headers['X-Robots-Tag'], 'noindex, follow')
        self.assertNotIn('immutable', page.headers['Cache-Control'])

    def test_saved_data_reaches_page_contact_and_alias_without_profile_coupling(self):
        save_settings(self.db, {'master_name': 'Имя только для сайта', 'instagram_url': 'https://example.org/profile-only'})
        before = get_card(self.db)
        self.assertEqual(before['first_name'], 'Маша')
        card = save_card(self.db, self.root, {'first_name': 'Елена', 'last_name': 'Тестовая',
                         'profession': 'Studio owner', 'phone': '+373 600 00000',
                         'email': 'elena@example.org', 'instagram_url': ''}, expected=before)
        for path in ('/card/', '/card/index.html', '/card/?utm_source=nfc'):
            page = self.fetch(path)
            self.assertEqual(page.code, 200)
            self.assertEqual(page.headers['Cache-Control'], 'no-store')
            self.assertIn('Елена'.encode(), page.body)
            self.assertNotIn('Маша'.encode(), page.body)
            self.assertIn(b'tel:+37360000000', page.body)
            self.assertNotIn(b'profile-only', page.body)
            self.assertNotIn(b'www.instagram.com', page.body)
        contact = self.fetch('/card/mbstudio.vcf')
        self.assertIn('FN:Елена Тестовая'.encode(), contact.body)
        self.assertIn(b'EMAIL;TYPE=INTERNET:elena@example.org', contact.body)
        self.assertEqual(contact.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.fetch('/card/', method='POST', body='first_name=Hacker').code, 405)
        self.assertEqual(get_card(self.db), card)

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
        self.assertEqual(self.fetch('/card/assets/portrait.webp').headers['Content-Type'], 'image/webp')

    def test_selected_cloud_rendition_is_served_under_card_origin(self):
        address = self.get_url('/card/assets/portrait.webp')
        with patch('scena_web.business_card.photo_source', return_value=address):
            image = self.fetch('/card/portrait.webp?v=updated')
        self.assertEqual(image.code, 200)
        self.assertEqual(image.headers['Content-Type'], 'image/webp')
        self.assertEqual(image.body, self.fetch('/card/assets/portrait.webp').body)
        self.assertEqual(image.headers['Cache-Control'], 'no-store')

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
