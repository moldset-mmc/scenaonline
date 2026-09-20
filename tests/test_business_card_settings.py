"""Independent card persistence, rejected edits, safe output and photo ownership."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from scena_business_card import DEFAULT_CARD, get_card, save_card, render_card, vcard, portrait_bytes
from scena_core import get_settings, init_db, save_settings
from scena_photo_library import catalog, trash_photo


class CardSettingsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory()
        self.addCleanup(self.fixture.cleanup)
        self.root = Path(self.fixture.name)
        self.db = self.root / 'card.db'
        init_db(self.db)

    def test_seed_migration_and_independence_in_both_directions(self):
        self.assertEqual(get_card(self.db), DEFAULT_CARD)
        profile = get_settings(self.db)
        saved = save_card(self.db, self.root, {'first_name': 'Анна', 'last_name': '', 'email': 'anna@example.org'}, expected=get_card(self.db))
        self.assertEqual(get_settings(self.db), profile)
        save_settings(self.db, {'master_name': 'На сайте другое имя', 'instagram_url': 'https://example.com/site'})
        init_db(self.db)
        self.assertEqual(get_card(self.db), saved)
        self.assertEqual(get_settings(self.db)['master_name'], 'На сайте другое имя')

    def test_rejected_and_stale_edits_do_not_change_published_data(self):
        original = get_card(self.db)
        for changes in [{'first_name': ''}, {'site_url': 'javascript:alert(1)'}, {'site_url': 'https://user:pass@example.org'},
                        {'site_url': '//example.org'}, {'email': 'one@example.org\r\nBcc:two@example.org'},
                        {'tagline': 'line\nEND:VCARD'}, {'phone': 'tel:123'}, {'primary_label': ''},
                        {'photo': '../private.png'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                save_card(self.db, self.root, changes, expected=original)
            self.assertEqual(get_card(self.db), original)
        fresh = save_card(self.db, self.root, {'first_name': 'Новое имя'}, expected=original)
        with self.assertRaisesRegex(ValueError, 'другом окне'):
            save_card(self.db, self.root, {'first_name': 'Старая вкладка'}, expected=original, upload=self.photo())
        self.assertEqual(get_card(self.db), fresh)
        self.assertFalse(list((self.root / 'media/business-card').glob('*')))

    @staticmethod
    def photo():
        output = io.BytesIO()
        Image.new('RGB', (500, 700), 'navy').save(output, 'PNG')
        return output.getvalue()

    def test_photo_save_preview_delete_protection_and_failed_upload(self):
        original = get_card(self.db)
        profile = get_settings(self.db)
        with self.assertRaises(ValueError):
            save_card(self.db, self.root, {}, expected=original, upload=b'not a photo')
        with patch('scena_media.persist', side_effect=OSError('storage unavailable')), self.assertRaises(OSError):
            save_card(self.db, self.root, {'first_name': 'Не сохранять'}, expected=original, upload=self.photo())
        self.assertEqual(get_card(self.db), original)
        self.assertFalse(list((self.root / 'media/business-card').glob('*')))
        saved = save_card(self.db, self.root, {}, expected=original, upload=self.photo())
        self.assertEqual((self.root / saved['photo']).read_bytes(), self.photo())
        with Image.open(io.BytesIO(portrait_bytes(self.root / saved['photo']))) as photo:
            self.assertEqual(photo.format, 'WEBP')
        item = next(row for row in catalog(self.db, self.root) if row['path'] == saved['photo'])
        self.assertTrue(any(row['group'] == 'card' for row in item['uses']))
        with self.assertRaises(ValueError):
            trash_photo(self.db, self.root, saved['photo'])
        self.assertEqual(get_settings(self.db), profile)

    def test_preview_does_not_save_and_output_is_escaped(self):
        original = get_card(self.db)
        values = {**original, 'first_name': '<img src=x onerror=alert(1)>', 'last_name': 'A;B,C', 'tagline': 'д' * 160}
        document = render_card(values, preview=True)
        self.assertNotIn('<img src=x onerror=', document)
        self.assertIn('&lt;img src=x onerror=', document)
        self.assertIn('data-preview="1"', document)
        self.assertEqual(get_card(self.db), original)
        contact = vcard(values)
        self.assertIn(b'A\\;B\\,C', contact)
        self.assertTrue(all(len(line) <= 75 for line in contact.split(b'\r\n')))
        self.assertIn(('NOTE:' + 'д' * 160).encode(), contact.replace(b'\r\n ', b''))


if __name__ == '__main__':
    unittest.main()
