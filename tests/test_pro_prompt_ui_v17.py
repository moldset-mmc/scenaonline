import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from streamlit.testing.v1 import AppTest
from scena_core import init_db
from scena_prompts import initialize_prompts, list_versions
from scena_licensing import initialize_licensing


class ProPromptUI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'scena.db'
        init_db(self.db)
        with sqlite3.connect(self.db) as connection:
            initialize_prompts(connection)
            initialize_licensing(connection)
        self.root = Path(__file__).resolve().parents[1]

    def page(self, module, function, locale):
        source = (f'from {module} import {function}\n'
                  f'from scena_core import get_settings\n'
                  f'{function}({str(self.db)!r}, {str(self.root)!r}, get_settings({str(self.db)!r}), {locale!r})\n')
        return AppTest.from_string(source, default_timeout=15).run()

    def test_pro_and_prompts_render_in_three_languages(self):
        for locale in ('ru', 'ro', 'en'):
            pro = self.page('scena_pro_ui', 'render_pro', locale)
            self.assertFalse(pro.exception, f'{locale}: {pro.exception}')
            self.assertTrue(any(button.key == 'pro_open_prompts' for button in pro.button))
            prompts = self.page('scena_prompts', 'render_prompts', locale)
            self.assertFalse(prompts.exception, f'{locale}: {prompts.exception}')
            self.assertTrue(prompts.text_area)

    def test_free_editor_saves_and_reopens_authored_text(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE pro_subscriptions SET tier='FREE', status='expired', expires_at=?", ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),))
        page = self.page('scena_prompts', 'render_prompts', 'ru')
        page.text_area[0].set_value('My authored image brief, preserved across restarts.')
        next(button for button in page.button if button.label == 'Сохранить мою версию').click().run()
        self.assertFalse(page.exception)
        self.assertEqual(list_versions(self.db)[0]['body'], 'My authored image brief, preserved across restarts.')
        reopened = self.page('scena_prompts', 'render_prompts', 'ru')
        self.assertEqual(reopened.text_area[0].value, 'My authored image brief, preserved across restarts.')
        reopened.selectbox(key='prompt_scenario').set_value('club').run()
        self.assertFalse(reopened.exception)
        self.assertFalse(reopened.text_area)


if __name__ == '__main__':
    unittest.main()
