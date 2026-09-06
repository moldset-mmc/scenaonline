import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scena_core import init_db, get_settings, save_settings
from scena_model_builder import (PRESETS, create_model_design, update_model_design,
    update_model_snapshot, save_model_draft_photo, list_model_designs, prepare_model_preview,
    publish_model_design, published_model_design, validate_design)

ROOT = Path(__file__).resolve().parents[1]


class ModelBuilderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = Path(self.directory.name)
        shutil.copytree(ROOT / 'media', self.app / 'media', copy_function=os.link)
        self.db = self.app / 'test.db'
        init_db(self.db)
        save_settings(self.db, {'model_published': '1'})

    def tearDown(self):
        self.directory.cleanup()

    def publish(self, item):
        token, settings = prepare_model_preview(self.db, item, self.app)
        publish_model_design(self.db, item, self.app, token, desktop_confirmed=True, mobile_confirmed=True)
        return settings

    def test_history_restores_photo_text_and_crop_as_new_draft(self):
        original = get_settings(self.db)
        first = create_model_design(self.db, 'First', 'gloss')
        self.publish(first)
        save_settings(self.db, {'model_intro_text_ru': 'Другая история', 'model_intro_text_ro': 'Altă poveste', 'model_slide_1_desktop_x': '75'})
        second = create_model_design(self.db, 'Second', 'club')
        self.publish(second)
        restored = create_model_design(self.db, 'Restored', restored_from=first, app_dir=self.app)
        self.assertNotEqual(restored, first)
        self.assertEqual(get_settings(self.db)['model_intro_text_ru'], 'Другая история')
        preview = self.publish(restored)
        self.assertEqual(preview['model_intro_text_ru'], original['model_intro_text_ru'])
        self.assertEqual(get_settings(self.db)['model_slide_1_desktop_x'], original['model_slide_1_desktop_x'])
        rows = list_model_designs(self.db)
        self.assertEqual(sum(row['status'] == 'published' for row in rows), 1)
        self.assertEqual(sum(row['status'] == 'archived' for row in rows), 2)

    def test_deleted_photo_becomes_empty_and_cannot_publish_until_replaced(self):
        first = create_model_design(self.db, 'First')
        self.publish(first)
        image = self.app / get_settings(self.db)['model_intro_image']
        data = image.read_bytes()
        image.unlink()
        restored = create_model_design(self.db, 'Restore', restored_from=first, app_dir=self.app)
        row = next(row for row in list_model_designs(self.db) if row['id'] == restored)
        self.assertEqual(json.loads(row['snapshot_json'])['model_intro_image'], '')
        with self.assertRaisesRegex(ValueError, 'удалена'):
            prepare_model_preview(self.db, restored, self.app)
        save_model_draft_photo(self.db, restored, 'model_intro_image', data, self.app, row['revision'])
        self.publish(restored)
        new_path = self.app / get_settings(self.db)['model_intro_image']
        self.assertTrue(new_path.is_file())
        self.assertEqual(new_path.read_bytes(), data)

    def test_current_content_change_invalidates_two_preview_approval(self):
        draft = create_model_design(self.db, 'Test')
        token, _ = prepare_model_preview(self.db, draft, self.app)
        save_settings(self.db, {'model_title': 'Changed after preview'})
        with self.assertRaisesRegex(ValueError, 'изменилось'):
            publish_model_design(self.db, draft, self.app, token, desktop_confirmed=True, mobile_confirmed=True)

    def test_both_view_confirmations_and_revision_are_required(self):
        draft = create_model_design(self.db, 'Test')
        token, _ = prepare_model_preview(self.db, draft, self.app)
        with self.assertRaisesRegex(ValueError, 'оба просмотра'):
            publish_model_design(self.db, draft, self.app, token, desktop_confirmed=True)
        update_model_design(self.db, draft, 'Changed', PRESETS['club'], 1)
        with self.assertRaisesRegex(ValueError, 'изменилось'):
            publish_model_design(self.db, draft, self.app, token, desktop_confirmed=True, mobile_confirmed=True)
        with self.assertRaisesRegex(ValueError, 'другом окне'):
            update_model_design(self.db, draft, 'Lost update', PRESETS['gloss'], 1)

    def test_live_pro_checked_in_transaction_and_published_survives_expiry(self):
        first = create_model_design(self.db, 'First', 'club')
        self.publish(first)
        second = create_model_design(self.db, 'Second')
        token, _ = prepare_model_preview(self.db, second, self.app)
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE pro_subscriptions SET expires_at='2020-01-01T00:00:00+00:00'")
        with patch('scena_model_builder._require_pro'):
            with self.assertRaisesRegex(ValueError, 'Продлите'):
                publish_model_design(self.db, second, self.app, token, desktop_confirmed=True, mobile_confirmed=True)
        self.assertEqual(published_model_design(self.db)['theme'], 'club')
        self.assertEqual(json.loads(get_settings(self.db)['model_design_json'])['theme'], 'club')

    def test_unknown_css_and_low_contrast_rejected(self):
        for changes in ({'background': '#ffffff'}, {'accent': '#111111'}, {'accent': '</style><script>'}, {'html': '<script>'}, {'show_location': 'yes'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_design({**PRESETS['gloss'], **changes})

    def test_snapshot_edit_is_private_until_publish(self):
        draft = create_model_design(self.db, 'Test')
        previous = get_settings(self.db)['model_intro_text_ru']
        update_model_snapshot(self.db, draft, {'model_intro_text_ru': 'Только в черновике'}, 1)
        self.assertEqual(get_settings(self.db)['model_intro_text_ru'], previous)
        token, preview = prepare_model_preview(self.db, draft, self.app)
        self.assertEqual(preview['model_intro_text_ru'], 'Только в черновике')
        with self.assertRaises(ValueError):
            update_model_snapshot(self.db, draft, {'admin_password': 'bad'}, 2)


if __name__ == '__main__': unittest.main()
