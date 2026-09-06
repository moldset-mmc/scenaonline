"""PRO presentation regression: renewal stays available and applications persist."""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from streamlit.testing.v1 import AppTest

from scena_cabinet import CHISINAU, list_pro_applications
from scena_core import init_db
from scena_pro_ui import _history_item


ROOT = Path(__file__).resolve().parents[1]


class ProPresentationV16Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "pro.db"
        init_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def app(self, locale="ru"):
        return AppTest.from_string(
            "from scena_pro_ui import render_pro\n"
            f"render_pro({str(self.db)!r}, {str(ROOT)!r}, {{}}, {locale!r})\n",
            default_timeout=20,
        ).run()

    def expire(self):
        expired = (datetime.now(CHISINAU) - timedelta(days=1)).isoformat()
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE pro_subscriptions SET expires_at = ?", (expired,))

    def test_active_trial_shows_live_tools_and_renewal_without_reapplication(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertFalse(any(area.key == 'pro_application_message' for area in app.text_area))
        self.assertTrue(any(area.label == 'Код продления' for area in app.text_area))
        self.assertTrue(app.button(key="pro_open_model"))
        self.assertTrue(app.button(key="pro_open_prompts"))
        self.assertTrue(app.button(key="pro_open_shop"))
        text = "\n".join(item.value for item in app.markdown)
        self.assertIn('SCENA · PRO', text)
        self.assertNotIn("Осталось 60 дней", text)  # The shared cabinet footer owns the countdown.
        self.assertNotIn("Скоро в PRO", text)
        self.assertIn("Личный Shop", text)
        self.assertIn("После окончания PRO оформленная страница и фотографии сохраняются", text)
        self.assertNotIn("локальной V1.4", text)
        self.assertEqual(len(list_pro_applications(self.db)), 1)

    def test_expired_owner_saves_application_once_and_sees_it_in_new_session(self):
        self.expire()
        app = self.app()
        self.assertFalse(app.exception)
        app.text_area(key="pro_application_message").set_value("Хочу получать приглашения в проекты.")
        button = next(button for button in app.button if button.label == "Отправить заявку")
        button.click().run()
        self.assertFalse(app.exception)
        saved = [item for item in list_pro_applications(self.db) if item["status"] == "pending"]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["message"], "Хочу получать приглашения в проекты.")
        fresh = self.app()
        self.assertFalse(fresh.exception)
        self.assertFalse(any(area.key == 'pro_application_message' for area in fresh.text_area))
        self.assertTrue(any(area.label == 'Код продления' for area in fresh.text_area))
        self.assertTrue(any("Заявка на PRO принята" in item.value for item in fresh.info))
        self.assertEqual(len([item for item in list_pro_applications(self.db) if item["status"] == "pending"]), 1)
        history = fresh.dataframe[0].value
        self.assertIn("Хочу получать приглашения в проекты.", history["Ваше сообщение"].tolist())

    def test_romanian_owner_gets_romanian_labels_and_persisted_application(self):
        self.expire()
        app = self.app("ro")
        self.assertFalse(app.exception)
        app.text_area(key="pro_application_message").set_value("Doresc să dezvolt pagina Model.")
        next(button for button in app.button if button.label == "Trimite cererea").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Cererea pentru PRO a fost primită" in item.value for item in app.info))
        self.assertEqual(list_pro_applications(self.db)[0]["message"], "Doresc să dezvolt pagina Model.")
        fresh = self.app('ro')
        self.assertFalse(fresh.exception)
        self.assertFalse(any(area.key == 'pro_application_message' for area in fresh.text_area))
        self.assertTrue(any(area.label == 'Cod de reînnoire' for area in fresh.text_area))
        self.assertEqual(len([item for item in list_pro_applications(self.db) if item['status'] == 'pending']), 1)
        self.assertIn('Doresc să dezvolt pagina Model.', fresh.dataframe[0].value['Mesajul dvs.'].tolist())

    def test_bootstrap_labels_are_humanized_without_rewriting_authored_notes(self):
        seed = list_pro_applications(self.db)[0]
        human = _history_item(seed, "ru")
        self.assertEqual(human["Ваше сообщение"], "Пробный PRO на 60 дней")
        self.assertEqual(human["Ответ SCENA"], "Пробный период активирован")
        authored = dict(seed, message="Мой пилотный проект, V1.4 — мои слова.", decision_note="Особые условия обсуждаем лично.")
        self.assertEqual(_history_item(authored, "ru")["Ваше сообщение"], authored["message"])
        self.assertEqual(_history_item(authored, "ru")["Ответ SCENA"], authored["decision_note"])
        same_text_user = dict(seed, source="cabinet")
        self.assertEqual(_history_item(same_text_user, "ru")["Ваше сообщение"], seed["message"])


if __name__ == "__main__":
    unittest.main()
