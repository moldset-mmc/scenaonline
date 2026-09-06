"""A real user draft survives a fresh app session and reaches its public route."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


class PublicationUITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'ui.db'
        self.env = patch.dict(os.environ, {
            'SCENA_DB_PATH': str(self.db),
            'SCENA_ADMIN_PASSWORD': 'local-test-only',
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def app(self, **params):
        app = AppTest.from_file(str(ROOT / 'scena-master-standalone.py'), default_timeout=25)
        app.query_params.update(params)
        return app

    def test_create_save_restart_preview_publish_and_open_post(self):
        from scena_publications import get_draft, list_publications

        app = self.app(page='admin', admin='1', section='promotion', view='posts')
        app.session_state['scena_admin_authenticated'] = True
        app.run()
        self.assertFalse(app.exception)
        app.button(key='publications_create').click().run()
        app.text_input(key='post_title_ru_new').set_value('Моя первая история')
        app.text_area(key='post_body_ru_new').set_value('Сегодня показываю новую работу.')
        app.button(key='post_save_new').click().run()
        self.assertFalse(app.exception)
        saved = list_publications(self.db)[0]
        self.assertEqual(saved['body_ru'], 'Сегодня показываю новую работу.')

        fresh = self.app(page='admin', admin='1', section='promotion', view='posts')
        fresh.session_state['scena_admin_authenticated'] = True
        fresh.session_state['publication_edit_id'] = saved['id']
        fresh.run()
        self.assertEqual(fresh.text_area(key=f"post_body_ru_{saved['id']}").value,
                         'Сегодня показываю новую работу.')
        fresh.text_input(key=f"post_title_ro_{saved['id']}").set_value('Prima mea poveste')
        fresh.text_area(key=f"post_body_ro_{saved['id']}").set_value('Astăzi prezint o lucrare nouă.')
        fresh.checkbox(key=f"post_approved_{saved['id']}").check()
        fresh.button(key=f"post_save_{saved['id']}").click().run()
        self.assertFalse(fresh.exception)
        fresh.button(key=f"post_preview_{saved['id']}").click().run()
        fresh.checkbox(key=f"post_preview_confirm_{saved['id']}").check().run()
        fresh.button(key=f"post_publish_{saved['id']}").click().run()
        self.assertFalse(fresh.exception)
        current = get_draft(self.db, saved['id'])
        public = self.app(page='post', post=current['public_id'], lang='ro').run()
        self.assertFalse(public.exception)
        self.assertIn('Prima mea poveste', public.title[0].value)

    def test_stale_editor_does_not_overwrite_another_session(self):
        from scena_core import init_db
        from scena_publications import save_draft, get_draft
        init_db(self.db)
        post = save_draft(self.db, body_ru='Первая версия', body_ro='Prima versiune')
        app = self.app(page='admin', admin='1', section='promotion', view='posts')
        app.session_state['scena_admin_authenticated'] = True
        app.session_state['publication_edit_id'] = post['id']
        app.run()
        save_draft(self.db, post['id'], body_ro='Salvată din altă fereastră')
        app.text_area(key=f"post_body_ru_{post['id']}").set_value('Правка старой вкладки')
        app.button(key=f"post_save_{post['id']}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(get_draft(self.db, post['id'])['body_ro'], 'Salvată din altă fereastră')
        self.assertTrue(app.error)


if __name__ == '__main__':
    unittest.main()
