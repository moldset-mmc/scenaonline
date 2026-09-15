import base64
import io
from pathlib import Path
import re
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from PIL import Image
from scena_core import init_db, get_settings, save_settings
from scena_intro_qr import DESTINATIONS, DEFAULT_QR_SETTINGS, qr_config, qr_destination, qr_button, save_qr
from scena_model_intro import save_intro
from scena_photo_library import catalog, trash_photo, restore_photo, upload_photo, assign_photo, targets

ROOT = Path(__file__).resolve().parents[1]


class IntroQRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'test.db'
        init_db(self.db)
        output = io.BytesIO()
        Image.new('RGB', (800, 1200), 'navy').save(output, 'PNG')
        self.photo = output.getvalue()
        self.settings = save_intro(self.db, self.root, {}, upload=self.photo)

    def test_replaced_image_keeps_interactive_overlay_and_enlarged_code(self):
        from model_landing import build_model_landing_html
        for path in ('media/qr-scenes/model.png', 'media/qr-scenes/professional.png', 'media/scena-v13/professional-portrait.webp'):
            document = build_model_landing_html({**self.settings, 'model_intro_image': path}, 'ru', ROOT)
            self.assertIn('class="intro-photo" data-qr-photo', document)
            self.assertIn('data-qr-open="qr-dialog"', document)
            self.assertNotIn('<figcaption class="intro-qr"', document)
            self.assertIn('dialog.showModal()', document)

    def test_every_destination_encodes_its_page_and_locale(self):
        from scena_qr import qr_png_bytes
        codes = set()
        for row in DESTINATIONS:
            for locale in ('ru', 'ro', 'en'):
                settings = {**self.settings, 'public_base_url': 'https://scena.example', 'model_intro_qr_destination': row[0]}
                address, label = qr_destination(settings, locale)
                query = parse_qs(urlparse(address).query)
                page, _, view = row[0].partition('-')
                self.assertEqual(query, {'page': [page], 'lang': [locale], **({'view': [view]} if view else {})})
                button, dialog = qr_button(settings, locale)
                encoded = re.search(r'<img src="data:image/png;base64,([^"]+)"', button)[1]
                self.assertEqual(base64.b64decode(encoded), qr_png_bytes(address))
                self.assertIn(encoded, dialog)
                codes.add(encoded)
        self.assertEqual(len(codes), 24)

    def test_qr_save_changes_only_qr_and_survives_reopen(self):
        changes = {'model_intro_qr_destination': 'professional', 'model_intro_qr_x': '51.1', 'model_intro_qr_y': '38.3', 'model_intro_qr_size': '15.8'}
        saved = save_qr(self.db, changes, expected=self.settings)
        self.assertEqual({k:v for k,v in saved.items() if k not in DEFAULT_QR_SETTINGS}, {k:v for k,v in self.settings.items() if k not in DEFAULT_QR_SETTINGS})
        init_db(self.db)
        self.assertEqual({key:get_settings(self.db)[key] for key in changes}, changes)
        replacement = save_intro(self.db, self.root, {}, upload=self.photo, expected=saved)
        self.assertEqual({key:replacement[key] for key in changes}, changes)

    def test_stale_qr_cannot_place_code_on_a_different_photo(self):
        newer = save_intro(self.db, self.root, {}, upload=self.photo, expected=self.settings)
        with self.assertRaisesRegex(ValueError, 'Обновите редактор'):
            save_qr(self.db, {'model_intro_qr_destination': 'booking'}, expected=self.settings)
        self.assertEqual(get_settings(self.db), newer)

    def test_stale_qr_and_invalid_coordinates_are_rejected(self):
        saved = save_qr(self.db, {'model_intro_qr_destination': 'shop'}, expected=self.settings)
        with self.assertRaises(ValueError):
            save_qr(self.db, {}, expected=self.settings)
        for invalid in ({'model_intro_qr_x':'nan'}, {'model_intro_qr_size':'0'}, {'model_intro_qr_y':'101'}, {'model_intro_qr_destination':'admin'}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                save_qr(self.db, invalid, expected=saved)
            self.assertEqual(get_settings(self.db), saved)

    def test_default_anchors_and_saved_anchors_are_independent_of_resolution(self):
        config = qr_config({'model_intro_image':'media/qr-scenes/model.png'})
        self.assertAlmostEqual(config['x'], (429+70)/1024*100)
        self.assertAlmostEqual(config['y'], (452+70)/1536*100)
        self.assertEqual(qr_config({'model_intro_image':'media/uploaded/new.png', 'model_intro_qr_x':'62.5'})['x'], 62.5)


class PhotoTrashTests(unittest.TestCase):
    setUp = IntroQRTests.setUp
    def test_unused_photo_can_be_deleted_and_restored_without_losing_original(self):
        path = upload_photo(self.db, self.root, self.photo, 'unused.png')
        trash_photo(self.db, self.root, path)
        trash_photo(self.db, self.root, path)  # Repeat is harmless.
        self.assertNotIn(path, [row['path'] for row in catalog(self.db, self.root)])
        self.assertTrue(next(row for row in catalog(self.db, self.root, include_trashed=True) if row['path']==path)['trashed'])
        self.assertEqual((self.root/path).read_bytes(), self.photo)
        target = next(row for row in targets(self.db) if row['id']=='avatar_url')
        with self.assertRaisesRegex(ValueError, 'корзине'):
            assign_photo(self.db, self.root, target['id'], path, target['version'])
        restore_photo(self.db, self.root, path)
        self.assertIn(path, [row['path'] for row in catalog(self.db, self.root)])

    def test_used_photo_cannot_be_deleted_even_from_stale_card(self):
        path = upload_photo(self.db, self.root, self.photo, 'unused.png')
        save_settings(self.db, {'avatar_url':path})
        with self.assertRaisesRegex(ValueError, 'используется'):
            trash_photo(self.db, self.root, path)
        self.assertEqual(get_settings(self.db)['avatar_url'], path)

    def test_restored_page_keeps_its_photo_visible(self):
        path = upload_photo(self.db, self.root, self.photo, 'unused.png')
        trash_photo(self.db, self.root, path)
        save_settings(self.db, {'avatar_url':path})
        row = next(row for row in catalog(self.db, self.root) if row['path']==path)
        self.assertFalse(row['trashed'])
        self.assertTrue(row['uses'])
