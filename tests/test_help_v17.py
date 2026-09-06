"""Conversation, ownership, routing and local secret storage contracts; no live I/O."""
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from scena_core import CHISINAU, init_db
from scena_cabinet import (CabinetValidationError, ask_scena_assistant, dispatch_support_notifications,
                          list_support_messages, submit_support_message, _assistant_context,
                          validate_reply_preference)
from scena_connect_setup import (AIConnection, ConnectionSetupError, configuration_path,
                                 effective_environment, load_environment, save_connection)
from scena_integrations import OpenAIResponsesAdapter
from streamlit.testing.v1 import AppTest


class HelpV17Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / "site"
        self.app.mkdir()
        self.db = self.app / "scena.db"
        self.now = datetime(2026, 9, 6, 10, 0, tzinfo=CHISINAU)
        init_db(self.db, now=self.now)
        self.env = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "private"), "LOCALAPPDATA": str(self.root / "private")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_support_channel_validation_and_idempotent_persistent_contact(self):
        first = submit_support_message(self.db, "Помогите с Model", reply_channel="telegram", contact="https://t.me/mariascena", request_key="same-request-123456", locale="en", now=self.now)
        again = submit_support_message(self.db, "Помогите с Model", reply_channel="telegram", contact="@mariascena", request_key="same-request-123456", locale="en", now=self.now)
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(len(list_support_messages(self.db)), 1)
        self.assertEqual(list_support_messages(self.db)[0]["reply_contact"], "@mariascena")
        with self.assertRaises(CabinetValidationError):
            submit_support_message(self.db, "Другое сообщение", reply_channel="telegram", contact="@mariascena", request_key="same-request-123456", now=self.now)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM integration_outbox").fetchone()[0], 1)
        init_db(self.db, now=self.now)
        self.assertEqual(list_support_messages(self.db)[0]["reply_contact"], "@mariascena")

    def test_invalid_reply_contacts_do_not_save_or_queue_anything(self):
        for channel, contact in (("sms", "555"), ("telegram", "name"), ("email", "a@b"), ("other", "x")):
            with self.subTest(channel=channel), self.assertRaises(CabinetValidationError):
                submit_support_message(self.db, "Hello", reply_channel=channel, contact=contact)
        self.assertEqual(list_support_messages(self.db), [])
        self.assertEqual(validate_reply_preference("sms", "+373 (60) 123-456"), ("sms", "+37360123456"))
        self.assertEqual(validate_reply_preference("scena", "ignored-contact"), ("scena", ""))

    def test_request_dispatch_contains_selected_contact_and_needs_ack(self):
        submit_support_message(self.db, "Есть вопрос", reply_channel="email", contact="maria@example.test", locale="ro", now=self.now)
        adapter = Mock(configured=True, configuration_fingerprint="")
        adapter.send_support_message.return_value = ""
        failed = dispatch_support_notifications(self.db, adapter, now=self.now)
        self.assertEqual(failed["failed"], 1)
        self.assertEqual(list_support_messages(self.db)[0]["delivery_status"], "failed")
        adapter.send_support_message.return_value = "confirmed-42"
        sent = dispatch_support_notifications(self.db, adapter, now=self.now)
        self.assertEqual(sent["sent"], 1)
        body = adapter.send_support_message.call_args.kwargs["body"]
        self.assertIn("maria@example.test", body)
        self.assertIn("RO", body)
        self.assertIn("ответ отправляется оператором", body)
        self.assertEqual(list_support_messages(self.db)[0]["delivery_status"], "sent")

    def test_context_has_actual_content_but_no_other_owner_private_messages_or_customer_contacts(self):
        with sqlite3.connect(self.db) as db:
            db.executemany("INSERT OR REPLACE INTO profile_settings VALUES (?,?)", [("bio", "Моя история"), ("SCENA_AI_API_KEY", "PRIVATE-KEY"), ("telegram_url", "PRIVATE-CONTACT")])
            db.execute("INSERT INTO support_threads (id,owner_key,subject,status,created_at,updated_at) VALUES (999,'other-owner','private','open','x','x')")
            db.execute("INSERT INTO support_messages (thread_id,sender,channel,body,created_at) VALUES (999,'user','assistant','OTHER-OWNER-PRIVATE','x')")
        submit_support_message(self.db, "PRIVATE-SUPPORT", reply_channel="email", contact="private@example.test", now=self.now)
        ctx = _assistant_context(self.db, self.now, "en")
        serialized = json.dumps(ctx, ensure_ascii=False)
        self.assertEqual(ctx["locale"], "en")
        self.assertEqual(ctx["profile_texts"]["bio"], "Моя история")
        self.assertTrue(ctx["services"])
        for sensitive in ("PRIVATE-KEY", "PRIVATE-CONTACT", "OTHER-OWNER-PRIVATE", "PRIVATE-SUPPORT", "private@example.test"):
            self.assertNotIn(sensitive, serialized)
        adapter = Mock(configured=True, configuration_fingerprint="")
        adapter.answer.return_value = "A real provider response"
        ask_scena_assistant(self.db, "Check my pages", adapter, locale="en", now=self.now)
        self.assertEqual(adapter.answer.call_args.kwargs["history"], [])
        self.assertEqual(adapter.answer.call_args.kwargs["context"]["locale"], "en")

    def test_guide_mode_is_labelled_and_persists_question_answer_without_fake_ai(self):
        adapter = Mock(configured=False)
        result = ask_scena_assistant(self.db, "How do I add a service?", adapter, locale="en", now=self.now)
        self.assertEqual(result["status"], "guided")
        self.assertTrue(result["assistant_message"]["body"].startswith("SCENA guide"))
        adapter.answer.assert_not_called()
        self.assertEqual([m["sender"] for m in list_support_messages(self.db)], ["user", "system"])
        self.assertIn("Work → Services", result["assistant_message"]["body"])

    def test_provider_failure_never_becomes_a_successful_ai_answer(self):
        adapter = Mock(configured=True, configuration_fingerprint="")
        adapter.answer.side_effect = RuntimeError("PRIVATE-KEY")
        result = ask_scena_assistant(self.db, "Help", adapter, locale="en", now=self.now)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("PRIVATE-KEY", json.dumps(list_support_messages(self.db)))
        self.assertEqual(list_support_messages(self.db)[-1]["sender"], "system")
        self.assertIn("No answer was received", list_support_messages(self.db)[-1]["body"])

    def test_ai_config_is_private_local_and_installation_scoped(self):
        connection = AIConnection("test-private-key", "model-id")
        with patch("scena_integrations.urlopen", side_effect=AssertionError("No network")):
            path = save_connection(self.app, connection)
            restored = load_environment(self.app)
        self.assertFalse(path.is_relative_to(self.app))
        self.assertEqual(restored, connection.as_environment())
        self.assertNotIn("test-private-key", repr(connection))
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(load_environment(self.root / "other-site"), {})
        other = configuration_path(self.root / "other-site")
        other.parent.mkdir(parents=True)
        other.write_bytes(path.read_bytes())
        with self.assertRaises(ConnectionSetupError):
            load_environment(self.root / "other-site")

    def test_corrupt_config_is_sanitized_and_environment_wins_without_reading_file(self):
        path = save_connection(self.app, AIConnection("test-private-key", "model-id"))
        path.write_text("PRIVATE-KEY corrupt", encoding="utf-8")
        with self.assertRaises(ConnectionSetupError) as failure:
            load_environment(self.app)
        self.assertNotIn("PRIVATE-KEY", str(failure.exception))
        values = effective_environment(self.app, {"SCENA_AI_API_KEY": "override", "SCENA_AI_MODEL": "other", "SCENA_TELEGRAM_BOT_TOKEN": "override"})
        self.assertEqual(values["SCENA_AI_MODEL"], "other")

    def test_insecure_or_credential_bearing_ai_endpoints_rejected_before_write(self):
        for endpoint in ("http://localhost:1234", "https://user:password@example.test/api", "https://example.test/api?key=private"):
            with self.subTest(endpoint=endpoint), self.assertRaises((ConnectionSetupError, ValueError)):
                AIConnection("test-private-key", "model-id", endpoint)
        self.assertFalse(configuration_path(self.app).exists())

    def ui(self, kind="assistant", locale="ru"):
        script = f'''from pathlib import Path
import streamlit as st
from scena_core import get_settings
from scena_help_ui import render_assistant, render_support
db = Path({str(self.db)!r})
if {kind!r} == 'assistant':
    render_assistant(db, Path({str(self.app)!r}), get_settings(db), {locale!r})
else:
    render_support(db, Path({str(self.app)!r}), {locale!r})
'''
        return AppTest.from_string(script, default_timeout=20)

    def test_chat_question_answer_are_simultaneously_visible_in_three_languages(self):
        import scena_help_ui
        for locale, prompt, guide in (("ru", "Как добавить услугу?", "Подсказка SCENA"), ("ro", "Cum adaug un serviciu?", "Ghid SCENA"), ("en", "How do I add a service?", "SCENA guide")):
            with self.subTest(locale=locale), patch.object(scena_help_ui, "_adapters", return_value=(Mock(configured=False), Mock(configured=False))):
                app = self.ui(locale=locale).run()
                self.assertEqual(len(app.exception), 0)
                app.chat_input[0].set_value(prompt).run()
                self.assertEqual(len(app.exception), 0)
                displayed = "\n".join(item.value for item in app.markdown)
                self.assertIn(prompt, displayed)
                self.assertIn(guide, displayed)
                self.assertNotIn("Пока недоступен", displayed)
                self.assertGreaterEqual(len(app.chat_message), 2)

    def test_support_composer_keeps_invalid_draft_and_queues_only_after_valid_contact(self):
        import scena_help_ui
        with patch.object(scena_help_ui, "_adapters", return_value=(Mock(configured=False), Mock(configured=False))):
            app = self.ui(kind="support").run()
            self.assertEqual(len(app.exception), 0)
            app.text_area[0].set_value("Мой вопрос")
            app.button[-1].click().run()
            self.assertTrue(app.error)
            self.assertEqual(app.text_area[0].value, "Мой вопрос")
            self.assertEqual(list_support_messages(self.db), [])
            app.text_input[0].set_value("@mariascena")
            app.button[-1].click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(list_support_messages(self.db)), 1)
            self.assertEqual(app.text_area[0].value, "")
            text = "\n".join(item.value for item in app.caption)
            self.assertIn("В очереди отправки", text)
            self.assertNotIn("Доставлено команде", text)


if __name__ == "__main__":
    unittest.main()
