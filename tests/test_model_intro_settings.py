"""Model introduction: durable content, original reuse, rejected/stale edits."""
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest

from PIL import Image
from scena_core import get_settings, init_db, save_settings
from scena_model_intro import DEFAULT_INTRO_SETTINGS, save_intro, saved_portraits


class IntroSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'fixture.db'
        init_db(self.db)
        self.photo = self.make_photo('navy')
        self.settings = save_intro(self.db, self.root, {}, upload=self.photo)

    @staticmethod
    def make_photo(color):
        output = io.BytesIO()
        Image.new('RGB', (600, 800), color).save(output, 'PNG')
        return output.getvalue()

    def test_additive_migration_preserves_existing_card_and_profile(self):
        save_settings(self.db, {'master_name': 'Личное имя', 'model_intro_title_ru': 'Моя собственная история'})
        with sqlite3.connect(self.db) as con:
            con.execute("DELETE FROM profile_settings WHERE key='model_intro_details_ro'")
        init_db(self.db)
        settings = get_settings(self.db)
        self.assertEqual(settings['model_intro_title_ru'], 'Моя собственная история')
        self.assertEqual(settings['master_name'], 'Личное имя')
        self.assertIn('model_intro_details_ro', settings)

    def test_text_crop_and_photo_survive_reopen(self):
        changes = {'model_intro_title_ru': 'Мой путь', 'model_intro_title_ro': 'Drumul meu',
                   'model_intro_details_ru': 'Поездки\nЛичные проекты', 'model_intro_details_ro': 'Călătorii\nProiecte personale',
                   'model_intro_desktop_x': '26', 'model_intro_mobile_y': '73'}
        save_intro(self.db, self.root, changes, expected=self.settings)
        init_db(self.db)
        saved = get_settings(self.db)
        for key, value in changes.items():
            self.assertEqual(saved[key], value)
        self.assertEqual((self.root / saved['model_intro_image']).read_bytes(), self.photo)

    def test_replacement_keeps_original_and_can_restore_it_without_touching_slides(self):
        before_slides = {k: v for k, v in self.settings.items() if k.startswith('model_slide_')}
        first = self.settings['model_intro_image']
        second_data = self.make_photo('gold')
        changed = save_intro(self.db, self.root, {}, upload=second_data, expected=self.settings)
        self.assertNotEqual(first, changed['model_intro_image'])
        self.assertEqual(len(saved_portraits(self.root)), 2)
        self.assertEqual((self.root / first).read_bytes(), self.photo)
        restored = save_intro(self.db, self.root, {'model_intro_image': first}, expected=changed)
        self.assertEqual(restored['model_intro_image'], first)
        self.assertEqual(before_slides, {k: v for k, v in restored.items() if k.startswith('model_slide_')})

    def test_rejected_edits_leave_published_content_and_media_intact(self):
        for invalid in ({'model_intro_text_ro': ''}, {'model_intro_details_ru': 'Только RU'},
                        {'model_intro_translations_approved': '0'}, {'model_intro_mobile_x': '101'},
                        {'model_intro_image': '../outside.png'}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                save_intro(self.db, self.root, invalid)
            self.assertEqual(get_settings(self.db), self.settings)
            self.assertEqual(len(saved_portraits(self.root)), 1)
        with self.assertRaises(ValueError):
            save_intro(self.db, self.root, {}, upload=b'not an image')
        self.assertEqual(get_settings(self.db), self.settings)

    def test_stale_editor_cannot_overwrite_new_content_or_leave_new_file(self):
        fresh = save_intro(self.db, self.root, {'model_intro_title_ru': 'Новее'}, expected=self.settings)
        with self.assertRaisesRegex(ValueError, 'другом окне'):
            save_intro(self.db, self.root, {'model_intro_title_ru': 'Старая вкладка'}, upload=self.make_photo('red'), expected=self.settings)
        self.assertEqual(get_settings(self.db), fresh)
        self.assertEqual(len(saved_portraits(self.root)), 1)
        self.assertFalse(list((self.root / 'media/model-intro').glob('.photo-*')))

    def test_disabled_card_may_keep_private_incomplete_draft(self):
        saved = save_intro(self.db, self.root, {'model_intro_enabled': '0', 'model_intro_text_ro': '', 'model_intro_translations_approved': '0'})
        self.assertEqual(saved['model_intro_enabled'], '0')

    def test_editor_save_is_real_and_fresh_session_reads_it(self):
        from streamlit.testing.v1 import AppTest
        source = f'''from pathlib import Path
from scena_core import get_settings
from scena_model_intro import render_intro_editor
render_intro_editor({str(self.db)!r}, Path({str(self.root)!r}), get_settings({str(self.db)!r}))
'''
        app = AppTest.from_string(source).run()
        next(w for w in app.text_input if w.label == 'Заголовок RU').set_value('Моя визитка')
        next(w for w in app.button if w.label == 'Сохранить визитку').click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn('Визитка сохранена.', [w.value for w in app.success])
        fresh = AppTest.from_string(source).run()
        self.assertEqual(next(w for w in fresh.text_input if w.label == 'Заголовок RU').value, 'Моя визитка')
        self.assertEqual(len(fresh.exception), 0)


if __name__ == '__main__':
    unittest.main()
