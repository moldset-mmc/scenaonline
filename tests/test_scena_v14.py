import json
import os
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ModuleNotFoundError:
    AppTest = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "scena-master-standalone.py"


def element_with_label(elements, label):
    return next(element for element in elements if element.label == label)


def group_with_key(app, key):
    return next(group for group in app.get("button_group") if group.key == key)


class ScenaV14CabinetTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "pilot-v14.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_pilot_trial_starts_once_and_counts_down_from_60_days(self):
        from scena_cabinet import get_pro_status, list_pro_applications
        from scena_core import CHISINAU, init_db

        started_at = datetime(2026, 9, 5, 10, 0, tzinfo=CHISINAU)
        init_db(self.db_path, now=started_at)

        status = get_pro_status(self.db_path, now=started_at)
        self.assertEqual(status["label"], "PRO Trial")
        self.assertEqual(status["status"], "trial")
        self.assertEqual(status["days_remaining"], 60)
        self.assertEqual(status["expires_at"], "2026-11-04T10:00:00+02:00")

        init_db(self.db_path, now=started_at + timedelta(days=10))
        later = get_pro_status(self.db_path, now=started_at + timedelta(days=10))
        self.assertEqual(later["days_remaining"], 50)
        self.assertEqual(later["expires_at"], status["expires_at"])

        applications = list_pro_applications(self.db_path)
        self.assertEqual(len(applications), 1)
        self.assertEqual(applications[0]["status"], "approved")
        self.assertEqual(applications[0]["source"], "pilot_preapproval")

    def test_expired_user_can_submit_one_application_and_approval_starts_a_new_trial(self):
        from scena_cabinet import (
            CabinetValidationError,
            decide_pro_application,
            get_pro_status,
            list_pro_applications,
            submit_pro_application,
        )
        from scena_core import CHISINAU, init_db

        first_start = datetime(2026, 1, 1, 9, 0, tzinfo=CHISINAU)
        expired_now = first_start + timedelta(days=61)
        init_db(self.db_path, now=first_start)
        self.assertEqual(get_pro_status(self.db_path, now=expired_now)["status"], "expired")

        application = submit_pro_application(
            self.db_path,
            "Хочу продолжить работу с профессиональными инструментами.",
            now=expired_now,
        )
        self.assertEqual(application["status"], "pending")
        with self.assertRaisesRegex(CabinetValidationError, "уже отправлена"):
            submit_pro_application(self.db_path, "Повторная заявка", now=expired_now)

        approved_at = expired_now + timedelta(days=1)
        decided = decide_pro_application(
            self.db_path,
            application["id"],
            approved=True,
            note="Одобрено администратором платформы.",
            now=approved_at,
        )
        self.assertEqual(decided["status"], "approved")
        renewed = get_pro_status(self.db_path, now=approved_at)
        self.assertEqual(renewed["status"], "trial")
        self.assertEqual(renewed["days_remaining"], 60)

        applications = list_pro_applications(self.db_path)
        self.assertEqual([item["status"] for item in applications], ["approved", "approved"])

    def test_support_message_is_persistent_and_dispatched_through_telegram_adapter(self):
        from scena_cabinet import (
            dispatch_support_notifications,
            list_support_messages,
            submit_support_message,
        )
        from scena_core import CHISINAU, init_db

        class RecordingTelegram:
            configured = True

            def __init__(self):
                self.sent = []

            def send_support_message(self, *, thread_id, body):
                self.sent.append({"thread_id": thread_id, "body": body})
                return "telegram-message-501"

        now = datetime(2026, 9, 5, 12, 30, tzinfo=CHISINAU)
        init_db(self.db_path, now=now)
        created = submit_support_message(
            self.db_path,
            "Не понимаю, как изменить фотографию на странице Model.",
            now=now,
        )
        self.assertEqual(created["sender"], "user")
        self.assertEqual(created["delivery_status"], "queued")

        telegram = RecordingTelegram()
        result = dispatch_support_notifications(self.db_path, telegram, now=now)
        self.assertEqual(result, {"sent": 1, "failed": 0, "waiting_configuration": 0})
        self.assertEqual(telegram.sent[0]["thread_id"], created["thread_id"])
        self.assertIn("изменить фотографию", telegram.sent[0]["body"])

        history = list_support_messages(self.db_path)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["body"], created["body"])
        self.assertEqual(history[0]["delivery_status"], "sent")
        self.assertEqual(history[0]["external_message_id"], "telegram-message-501")

    def test_support_outbox_claim_prevents_duplicate_concurrent_delivery(self):
        from scena_cabinet import dispatch_support_notifications, submit_support_message
        from scena_core import CHISINAU, init_db

        class SlowTelegram:
            configured = True

            def __init__(self):
                self.calls = 0
                self.lock = threading.Lock()
                self.entered = threading.Event()
                self.release = threading.Event()

            def send_support_message(self, *, thread_id, body):
                with self.lock:
                    self.calls += 1
                self.entered.set()
                self.release.wait(timeout=3)
                return "telegram-message-once"

        now = datetime(2026, 9, 5, 12, 45, tzinfo=CHISINAU)
        init_db(self.db_path, now=now)
        submit_support_message(self.db_path, "Отправьте один раз.", now=now)
        telegram = SlowTelegram()
        results = []
        errors = []

        def dispatch():
            try:
                results.append(
                    dispatch_support_notifications(self.db_path, telegram, now=now)
                )
            except Exception as exc:  # pragma: no cover - captured for assertion
                errors.append(exc)

        first = threading.Thread(target=dispatch)
        first.start()
        self.assertTrue(telegram.entered.wait(timeout=2))
        second = threading.Thread(target=dispatch)
        second.start()
        second.join(timeout=2)
        telegram.release.set()
        first.join(timeout=2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(telegram.calls, 1)
        self.assertEqual(sum(item["sent"] for item in results), 1)

    def test_telegram_reply_returns_to_the_same_cabinet_thread_once(self):
        from scena_cabinet import (
            dispatch_support_notifications,
            list_support_messages,
            submit_support_message,
            sync_telegram_replies,
        )
        from scena_core import CHISINAU, init_db

        class ReplyingTelegram:
            configured = True

            def send_support_message(self, *, thread_id, body):
                return "telegram-message-777"

            def poll_admin_replies(self, *, offset):
                if offset > 9100:
                    return []
                return [{
                    "update_id": 9100,
                    "text": "Откройте Model → Кадры и выберите нужный слот.",
                    "reply_to_message_id": "telegram-message-777",
                }]

        now = datetime(2026, 9, 5, 13, 0, tzinfo=CHISINAU)
        init_db(self.db_path, now=now)
        question = submit_support_message(self.db_path, "Где заменить кадр?", now=now)
        telegram = ReplyingTelegram()
        dispatch_support_notifications(self.db_path, telegram, now=now)

        first_sync = sync_telegram_replies(
            self.db_path, telegram, now=now + timedelta(minutes=2)
        )
        second_sync = sync_telegram_replies(
            self.db_path, telegram, now=now + timedelta(minutes=3)
        )
        self.assertEqual(first_sync["received"], 1)
        self.assertEqual(second_sync["received"], 0)

        history = list_support_messages(self.db_path)
        self.assertEqual([item["sender"] for item in history], ["user", "admin"])
        self.assertEqual(history[1]["thread_id"], question["thread_id"])
        self.assertIn("Model", history[1]["body"])

    def test_telegram_poll_offset_advances_past_irrelevant_updates(self):
        from scena_cabinet import sync_telegram_replies
        from scena_core import CHISINAU, init_db

        class NoisyTelegram:
            configured = True

            def __init__(self):
                self.offsets = []

            def poll_admin_replies(self, *, offset):
                self.offsets.append(offset)
                return {"replies": [], "next_offset": 9302}

        now = datetime(2026, 9, 5, 13, 15, tzinfo=CHISINAU)
        init_db(self.db_path, now=now)
        telegram = NoisyTelegram()
        sync_telegram_replies(self.db_path, telegram, now=now)
        sync_telegram_replies(self.db_path, telegram, now=now)

        self.assertEqual(telegram.offsets, [0, 9302])

    def test_scena_assistant_uses_only_current_cabinet_context_and_keeps_history(self):
        from scena_cabinet import ask_scena_assistant, list_support_messages
        from scena_core import CHISINAU, init_db, save_settings

        class RecordingAssistant:
            configured = True

            def __init__(self):
                self.context = None
                self.history = None

            def answer(self, *, question, context, history):
                self.context = context
                self.history = history
                return (
                    "Сначала откройте Model → Кадры. У первого кадра не заполнено "
                    "отдельное мобильное кадрирование."
                )

        now = datetime(2026, 9, 5, 14, 0, tzinfo=CHISINAU)
        init_db(self.db_path, now=now)
        save_settings(
            self.db_path,
            {
                "master_name": "Мария Бараночникова",
                "location": "Кишинёв",
                "bio": "",
            },
        )
        assistant = RecordingAssistant()
        result = ask_scena_assistant(
            self.db_path,
            "Что мне улучшить на странице Model?",
            assistant,
            now=now,
        )

        self.assertEqual(result["status"], "answered")
        self.assertEqual(assistant.context["owner"]["name"], "Мария Бараночникова")
        self.assertEqual(assistant.context["owner"]["location"], "Кишинёв")
        self.assertIn(
            "Работа → Услуги",
            [item["route"] for item in assistant.context["cabinet_guide"]],
        )
        self.assertIn(
            "Настройки → Резервная копия",
            [item["route"] for item in assistant.context["cabinet_guide"]],
        )
        self.assertNotIn("phone", str(assistant.context).lower())
        self.assertNotIn("email", str(assistant.context).lower())
        self.assertEqual(assistant.history, [])

        history = list_support_messages(self.db_path)
        self.assertEqual([item["sender"] for item in history], ["user", "assistant"])
        self.assertEqual([item["channel"] for item in history], ["assistant", "assistant"])
        self.assertIn("мобильное кадрирование", history[1]["body"])

    def test_scena_assistant_records_only_a_sanitized_failure_code(self):
        from scena_cabinet import ask_scena_assistant
        from scena_core import CHISINAU, init_db
        from scena_integrations import IntegrationResponseError

        class SuccessfulAssistant:
            configured = True
            configuration_fingerprint = "a" * 64

            def answer(self, *, question, context, history):
                return "Сначала проверьте страницу Model."

        class FailingAssistant:
            configured = True
            configuration_fingerprint = "a" * 64

            def answer(self, *, question, context, history):
                raise IntegrationResponseError(
                    "provider details with TOP-SECRET", code="transport_error"
                )

        now = datetime(2026, 9, 5, 14, 30, tzinfo=CHISINAU)
        init_db(self.db_path, now=now)
        ask_scena_assistant(
            self.db_path, "Что проверить?", SuccessfulAssistant(), now=now
        )
        result = ask_scena_assistant(
            self.db_path, "Почему нет ответа?", FailingAssistant(), now=now
        )
        self.assertEqual(result["status"], "failed")
        with sqlite3.connect(self.db_path) as connection:
            states = dict(
                connection.execute(
                    "SELECT key, value FROM integration_state WHERE channel = 'ai'"
                ).fetchall()
            )
        self.assertEqual(states["last_error_code"], "transport_error")
        self.assertEqual(states["last_check_status"], "failed")
        self.assertEqual(states["configuration_fingerprint"], "a" * 64)
        self.assertNotIn("TOP-SECRET", str(states))

    def test_openai_responses_adapter_parses_text_without_storing_remote_history(self):
        from scena_integrations import OpenAIResponsesAdapter

        class JsonResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        captured = {}

        def open_response(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return JsonResponse({
                "output": [{
                    "type": "message",
                    "content": [{
                        "type": "output_text",
                        "text": "Добавьте отдельное кадрирование для телефона.",
                    }],
                }],
            })

        adapter = OpenAIResponsesAdapter(
            api_key="test-platform-key",
            model="test-model",
            opener=open_response,
        )
        answer = adapter.answer(
            question="Что улучшить?",
            context={"owner": {"name": "Мария"}},
            history=[{"role": "user", "content": "Проверь Model."}],
        )

        self.assertTrue(adapter.configured)
        self.assertEqual(answer, "Добавьте отдельное кадрирование для телефона.")
        self.assertEqual(captured["url"], "https://api.openai.com/v1/responses")
        self.assertEqual(captured["payload"]["model"], "test-model")
        self.assertFalse(captured["payload"].get("store", True))
        self.assertIn("только данные текущего кабинета", captured["payload"]["instructions"])

    def test_telegram_adapter_sends_support_and_accepts_only_admin_replies(self):
        from scena_integrations import TelegramBotAdapter

        class JsonResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        calls = []

        def open_telegram(request, timeout):
            payload = json.loads(request.data.decode("utf-8"))
            calls.append((request.full_url, payload, timeout))
            if request.full_url.endswith("/sendMessage"):
                return JsonResponse({"ok": True, "result": {"message_id": 777}})
            return JsonResponse({
                "ok": True,
                "result": [
                    {
                        "update_id": 9200,
                        "message": {
                            "chat": {"id": -100555},
                            "from": {"id": 501},
                            "text": "Ответ администратора.",
                            "reply_to_message": {"message_id": 777},
                        },
                    },
                    {
                        "update_id": 9201,
                        "message": {
                            "chat": {"id": -100555},
                            "from": {"id": 999},
                            "text": "Чужое сообщение.",
                            "reply_to_message": {"message_id": 777},
                        },
                    },
                ],
            })

        adapter = TelegramBotAdapter(
            bot_token="test-bot-token",
            admin_chat_id="-100555",
            admin_user_ids=["501"],
            opener=open_telegram,
        )
        external_id = adapter.send_support_message(thread_id=4, body="Нужна помощь.")
        poll_result = adapter.poll_admin_replies(offset=9200)
        replies = poll_result["replies"]

        self.assertTrue(adapter.configured)
        self.assertEqual(external_id, "777")
        self.assertIn("SCENA · обращение #4", calls[0][1]["text"])
        self.assertEqual(calls[1][1]["offset"], 9200)
        self.assertEqual(poll_result["next_offset"], 9202)
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["reply_to_message_id"], "777")
        self.assertEqual(replies[0]["text"], "Ответ администратора.")

    def test_external_adapter_errors_do_not_expose_credentials(self):
        from scena_integrations import (
            IntegrationResponseError,
            OpenAIResponsesAdapter,
            TelegramBotAdapter,
        )

        def failing_open(request, timeout):
            raise RuntimeError(f"connection failed for {request.full_url}")

        ai_secret = "platform-secret-key"
        ai = OpenAIResponsesAdapter(
            api_key=ai_secret,
            model="test-model",
            opener=failing_open,
        )
        with self.assertRaises(IntegrationResponseError) as ai_error:
            ai.answer(question="Помоги", context={}, history=[])
        self.assertNotIn(ai_secret, str(ai_error.exception))

        telegram_secret = "telegram-secret-token"
        telegram = TelegramBotAdapter(
            bot_token=telegram_secret,
            admin_chat_id="101",
            opener=failing_open,
        )
        with self.assertRaises(IntegrationResponseError) as telegram_error:
            telegram.send_support_message(thread_id=1, body="Помоги")
        self.assertNotIn(telegram_secret, str(telegram_error.exception))

        self.assertNotIn(ai_secret, ai.configuration_fingerprint)
        self.assertNotIn(telegram_secret, telegram.configuration_fingerprint)
        self.assertNotEqual(
            ai.configuration_fingerprint,
            OpenAIResponsesAdapter(
                api_key="another-key", model="test-model"
            ).configuration_fingerprint,
        )

    def test_support_outbox_keeps_only_sanitized_external_error(self):
        from scena_cabinet import dispatch_support_notifications, submit_support_message
        from scena_core import CHISINAU, init_db

        class LeakyTelegram:
            configured = True

            def send_support_message(self, *, thread_id, body):
                raise RuntimeError("https://api.telegram.org/botTOP-SECRET/sendMessage")

        now = datetime(2026, 9, 5, 16, 0, tzinfo=CHISINAU)
        init_db(self.db_path, now=now)
        submit_support_message(self.db_path, "Помогите настроить Model.", now=now)
        result = dispatch_support_notifications(self.db_path, LeakyTelegram(), now=now)

        self.assertEqual(result["failed"], 1)
        with sqlite3.connect(self.db_path) as connection:
            stored_error = connection.execute(
                "SELECT last_error FROM integration_outbox"
            ).fetchone()[0]
        self.assertNotIn("TOP-SECRET", stored_error)
        self.assertEqual(stored_error, "Внешняя отправка временно недоступна.")


@unittest.skipIf(AppTest is None, "Streamlit UI dependencies are not installed")
class ScenaV14AppTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "ui-v14.db"
        keys = (
            "SCENA_DB_PATH",
            "SCENA_ADMIN_PASSWORD",
            "SCENA_AI_API_KEY",
            "SCENA_AI_MODEL",
            "SCENA_TELEGRAM_BOT_TOKEN",
            "SCENA_TELEGRAM_ADMIN_CHAT_ID",
            "SCENA_TELEGRAM_ADMIN_USER_IDS",
        )
        self.old_env = {key: os.environ.get(key) for key in keys}
        os.environ["SCENA_DB_PATH"] = str(self.db_path)
        os.environ["SCENA_ADMIN_PASSWORD"] = "test-password"
        for key in keys[2:]:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def logged_in_app(self, *, view="assistant", section="help"):
        app = AppTest.from_file(str(APP_PATH), default_timeout=20)
        app.query_params["page"] = "admin"
        app.query_params["lang"] = "ru"
        app.query_params["admin"] = "1"
        app.query_params["section"] = section
        app.query_params["view"] = view
        app.run()
        element_with_label(app.text_input, "Пароль").set_value("test-password")
        element_with_label(app.button, "Войти").click()
        return app.run()

    def test_every_cabinet_screen_shows_trial_status_and_assistant_is_transparent(self):
        from scena_cabinet import list_support_messages

        app = self.logged_in_app(view="assistant")
        self.assertEqual(len(app.exception), 0)
        markup = "\n".join(item.value for item in app.markdown)
        self.assertIn("SCENA · PRO Trial", markup)
        self.assertIn("PRO Trial", markup)
        self.assertIn("Осталось", markup)
        self.assertIsNotNone(group_with_key(app, "admin_section_navigation_help"))

        app.chat_input[0].set_value("Что мне заполнить сначала?").run()

        self.assertEqual(len(app.exception), 0)
        self.assertFalse(app.warning)
        history = list_support_messages(self.db_path)
        self.assertEqual([item["sender"] for item in history], ["user", "system"])
        self.assertIn("Что мне заполнить", history[0]["body"])
        self.assertIn("Подсказка SCENA", history[1]["body"])

    def test_support_form_keeps_message_when_telegram_is_not_configured(self):
        from scena_cabinet import list_support_messages

        app = self.logged_in_app(view="support")
        element_with_label(app.selectbox, "Удобный канал").set_value("scena").run()
        element_with_label(app.text_area, "Сообщение команде SCENA").set_value(
            "Помогите проверить страницу Model."
        )
        element_with_label(app.button, "Отправить").click()
        app.run()

        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("В очереди отправки" in item.value for item in app.caption))
        history = list_support_messages(self.db_path)
        support = [item for item in history if item["channel"] == "support"]
        self.assertEqual(len(support), 1)
        self.assertEqual(support[0]["delivery_status"], "queued")

    def test_configured_integrations_are_not_claimed_as_verified_before_a_call(self):
        os.environ["SCENA_AI_API_KEY"] = "test-key"
        os.environ["SCENA_AI_MODEL"] = "test-model"
        app = self.logged_in_app(section="settings", view="connections")

        markup = "\n".join(item.value for item in app.caption)
        self.assertIn("ожидает проверки", markup)
        self.assertNotIn("Связь проверена", markup)

    def test_changed_ai_credentials_require_a_fresh_successful_check(self):
        from scena_core import init_db

        init_db(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.executemany(
                """
                INSERT INTO integration_state(channel, key, value)
                VALUES ('ai', ?, ?)
                """,
                [
                    ("last_check_status", "success"),
                    ("configuration_fingerprint", "b" * 64),
                    ("last_success_at", "2099-01-01T00:00:00+02:00"),
                ],
            )
        os.environ["SCENA_AI_API_KEY"] = "new-test-key"
        os.environ["SCENA_AI_MODEL"] = "test-model"

        app = self.logged_in_app(section="settings", view="connections")

        markup = "\n".join(item.value for item in app.caption)
        self.assertIn("ожидает проверки", markup)
        self.assertNotIn("Связь проверена", markup)

    def test_support_has_an_explicit_retry_for_queued_messages(self):
        from scena_cabinet import submit_support_message
        from scena_core import init_db

        init_db(self.db_path)
        submit_support_message(self.db_path, "Сообщение ожидает Telegram.")
        os.environ["SCENA_TELEGRAM_BOT_TOKEN"] = "test-token"
        os.environ["SCENA_TELEGRAM_ADMIN_CHAT_ID"] = "501"

        app = self.logged_in_app(view="support")

        self.assertEqual(len(app.exception), 0)
        markup = "\n".join(item.value for item in app.markdown)
        self.assertNotIn("Связь проверена", markup)
        retry = element_with_label(app.button, "Повторить отправку (1)")
        self.assertFalse(retry.disabled)


if __name__ == "__main__":
    unittest.main()
