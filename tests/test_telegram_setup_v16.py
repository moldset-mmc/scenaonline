"""User-confirmation, recipient-isolation and credential-storage boundaries."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import scena_telegram_setup as setup


TOKEN = "123456789:" + "A" * 35
CHAT = "501"


class TelegramSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / "site"
        self.app.mkdir()
        self.connection = setup.TelegramConnection(TOKEN, CHAT)
        config_root = str(self.root / "personal")
        self.env = patch.dict(os.environ, {"XDG_CONFIG_HOME": config_root, "LOCALAPPDATA": config_root})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_save_load_is_local_private_and_outside_deliverable(self):
        environment_before = os.environ.copy()
        with patch.object(setup, "urlopen", side_effect=AssertionError("No network allowed")):
            path = setup.save_connection(self.app, self.connection)
            restored = setup.load_environment(self.app)
        self.assertFalse(path.is_relative_to(self.app))
        self.assertEqual(restored, self.connection.as_environment())
        self.assertEqual(os.environ, environment_before)
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertNotIn(TOKEN, repr(self.connection))
        self.assertNotIn(TOKEN, setup.save_preview(self.app, self.connection))
        self.assertIn(CHAT, setup.save_preview(self.app, self.connection))

    def test_another_installation_does_not_inherit_owner_credentials(self):
        setup.save_connection(self.app, self.connection)
        other_app = self.root / "sold-site"
        other_app.mkdir()
        self.assertEqual(setup.load_environment(other_app), {})
        self.assertNotEqual(setup.configuration_path(self.app), setup.configuration_path(other_app))
        self.assertEqual(setup.configuration_path(self.app / "."), setup.configuration_path(self.app))

    def test_copying_operator_file_cannot_rebind_it_to_another_installation(self):
        first = setup.save_connection(self.app, self.connection)
        other_app = self.root / "another-site"
        second = setup.configuration_path(other_app)
        second.parent.mkdir(parents=True)
        second.write_bytes(first.read_bytes())
        with self.assertRaises(setup.TelegramSetupError) as error:
            setup.load_environment(other_app)
        self.assertNotIn(TOKEN, str(error.exception))

    def test_rejects_groups_usernames_and_bad_tokens_without_echoing_secrets(self):
        for chat_id in ("-100123", "@someone", "0", "501 ", "1;echo hello", ""):
            with self.subTest(chat=chat_id), self.assertRaises(setup.TelegramSetupError):
                setup.TelegramConnection(TOKEN, chat_id)
        for token in ("invalid-secret", "123:ABC", TOKEN + "\n"):
            with self.subTest(token_length=len(token)), self.assertRaises(setup.TelegramSetupError) as error:
                setup.TelegramConnection(token, CHAT)
            self.assertNotIn(token, str(error.exception))

    def test_corrupt_operator_file_errors_do_not_disclose_saved_data(self):
        path = setup.save_connection(self.app, self.connection)
        path.write_text("corrupt " + TOKEN, encoding="utf-8")
        with self.assertRaises(setup.TelegramSetupError) as error:
            setup.load_environment(self.app)
        self.assertNotIn(TOKEN, str(error.exception))

    def test_discovery_cancel_makes_no_external_call(self):
        fetch = Mock(side_effect=AssertionError("Must not read without approval"))
        output = []
        result = setup.discover_private_chat(TOKEN, read=lambda _: "", write=output.append, fetch_updates=fetch)
        self.assertIsNone(result)
        fetch.assert_not_called()
        self.assertNotIn(TOKEN, "\n".join(output))

    @staticmethod
    def update(chat=501, *, kind="private", date=101, text="SCENA CONNECT UNIQUE", **extras):
        return {"update_id": 20, "message": {
            "text": text, "date": date,
            "chat": {"id": chat, "type": kind, "first_name": "Serghei"},
            "from": {"id": chat, "is_bot": False}, **extras,
        }}

    def test_discovery_confirms_only_fresh_private_code_and_never_shows_other_messages(self):
        updates = [
            self.update(999, text="private unrelated customer message"),
            self.update(-100501, kind="group"),
            self.update(777, date=1),
            self.update(888, forward_origin={"type": "user"}),
            self.update(666, **{"from": {"id": 777, "is_bot": False}}),
            self.update(),
            self.update(text=None),
        ]
        fetch = Mock(return_value=updates)
        replies = iter(("ПРОЧИТАТЬ", "МОЙ ЧАТ"))
        output = []
        result = setup.discover_private_chat(
            TOKEN, read=lambda _: next(replies), write=output.append,
            fetch_updates=fetch, clock=lambda: 100, code_factory=lambda: "UNIQUE",
        )
        self.assertEqual(result, CHAT)
        fetch.assert_called_once_with(TOKEN)
        rendered = "\n".join(output)
        self.assertIn("Serghei", rendered)
        self.assertIn("Chat ID: 501", rendered)
        self.assertNotIn("private unrelated customer message", rendered)
        self.assertNotIn(TOKEN, rendered)

    def test_discovery_rejects_multiple_targets_and_declined_target(self):
        with self.assertRaises(setup.TelegramSetupError):
            setup.discover_private_chat(
                TOKEN, read=lambda _: "ПРОЧИТАТЬ", write=lambda _: None,
                fetch_updates=lambda _: [self.update(), self.update(502)],
                clock=lambda: 100, code_factory=lambda: "UNIQUE",
            )
        replies = iter(("ПРОЧИТАТЬ", "нет"))
        result = setup.discover_private_chat(
            TOKEN, read=lambda _: next(replies), write=lambda _: None,
            fetch_updates=lambda _: [self.update()], clock=lambda: 100,
            code_factory=lambda: "UNIQUE",
        )
        self.assertIsNone(result)
        self.assertEqual(setup.load_environment(self.app), {})

    def test_expired_code_does_not_read_telegram(self):
        clock = iter((100, 800))
        fetch = Mock()
        with self.assertRaises(setup.TelegramSetupError):
            setup.discover_private_chat(
                TOKEN, read=lambda _: "ПРОЧИТАТЬ", write=lambda _: None,
                fetch_updates=fetch, clock=lambda: next(clock),
            )
        fetch.assert_not_called()

    def test_get_updates_never_advances_offset_or_changes_bot_settings(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"ok":true,"result":[]}'
        with patch.object(setup, "urlopen", return_value=response) as opener:
            self.assertEqual(setup._read_bot_updates(TOKEN), [])
        request = opener.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/getUpdates"))
        self.assertEqual(json.loads(request.data), {"limit": 100, "timeout": 0})

    def test_cancelled_test_does_not_instantiate_an_external_adapter(self):
        factory = Mock(side_effect=AssertionError("Must not send without approval"))
        output = []
        result = setup.test_connection(self.connection, read=lambda _: "да", write=output.append, adapter_factory=factory)
        self.assertFalse(result)
        factory.assert_not_called()
        self.assertIn(setup.TEST_MESSAGE, "\n".join(output))
        self.assertNotIn(TOKEN, "\n".join(output))

    def test_confirmed_test_sends_exactly_previewed_text_to_private_owner(self):
        adapter = Mock()
        adapter._call.side_effect = [
            {"id": 123456789, "is_bot": True},
            {"message_id": 18, "chat": {"id": 501, "type": "private"}},
        ]
        output = []
        result = setup.test_connection(
            self.connection, read=lambda _: "ОТПРАВИТЬ", write=output.append,
            adapter_factory=lambda **_: adapter,
        )
        self.assertTrue(result)
        self.assertEqual(adapter._call.call_count, 2)
        self.assertEqual(adapter._call.call_args_list[0].args, ("getMe", {}))
        self.assertEqual(adapter._call.call_args_list[1].args, (
            "sendMessage", {"chat_id": CHAT, "text": setup.TEST_MESSAGE},
        ))
        self.assertNotIn(TOKEN, "\n".join(output))

    def test_wrong_bot_stops_before_send_and_transport_failure_is_sanitized(self):
        adapter = Mock()
        adapter._call.return_value = {"id": 987654321, "is_bot": True}
        with self.assertRaises(setup.TelegramSetupError):
            setup.test_connection(self.connection, read=lambda _: "ОТПРАВИТЬ", write=lambda _: None, adapter_factory=lambda **_: adapter)
        adapter._call.assert_called_once_with("getMe", {})
        adapter.reset_mock()
        adapter._call.side_effect = RuntimeError("https://api.telegram.org/bot" + TOKEN)
        with self.assertRaises(setup.TelegramSetupError) as error:
            setup.test_connection(self.connection, read=lambda _: "ОТПРАВИТЬ", write=lambda _: None, adapter_factory=lambda **_: adapter)
        self.assertNotIn(TOKEN, str(error.exception))
        self.assertEqual(adapter._call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
