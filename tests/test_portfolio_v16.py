import io
import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scena_core import get_settings, init_db, save_settings
from scena_portfolio import build_portfolio_html, effective_slots, portfolio_frames, saved_originals, update_portfolio_slot


def original_bytes(color="navy"):
    buffer = io.BytesIO()
    Image.new("RGB", (800, 1200), color).save(buffer, "PNG")
    return buffer.getvalue()


class PortfolioV16Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "profile.db"
        init_db(self.db)

    def test_twelfth_slot_survives_restart_and_original_is_unchanged(self):
        original = original_bytes()
        relative = update_portfolio_slot(self.db, self.root, "Professional", 12, data=original)
        init_db(self.db)
        settings = get_settings(self.db)
        self.assertEqual(settings["beauty_image_12"], relative)
        self.assertEqual((self.root / relative).read_bytes(), original)
        self.assertEqual([frame["slot"] for frame in portfolio_frames(self.root, settings, "ru", "Professional")], [12])

    def test_replacement_and_removal_keep_both_originals(self):
        first = update_portfolio_slot(self.db, self.root, "Model", 8, data=original_bytes())
        second = update_portfolio_slot(self.db, self.root, "Model", 8, data=original_bytes("maroon"))
        self.assertNotEqual(first, second)
        update_portfolio_slot(self.db, self.root, "Model", 8, remove=True)
        self.assertEqual(get_settings(self.db)["model_image_8"], "")
        self.assertTrue((self.root / first).is_file())
        self.assertTrue((self.root / second).is_file())

    def test_previous_original_can_be_restored_without_another_file_copy(self):
        first = update_portfolio_slot(self.db, self.root, "Model", 9, data=original_bytes())
        update_portfolio_slot(self.db, self.root, "Model", 9, data=original_bytes("maroon"))
        self.assertIn(first, saved_originals(self.root))
        update_portfolio_slot(self.db, self.root, "Model", 9, existing_image=first)
        init_db(self.db)
        self.assertEqual(get_settings(self.db)["model_image_9"], first)
        self.assertEqual(len(saved_originals(self.root)), 2)
        with self.assertRaises(ValueError):
            update_portfolio_slot(self.db, self.root, "Model", 9, existing_image="media/../secret.png")

    def test_initial_gallery_persists_as_editable_slots_and_stays_empty_after_removal(self):
        before = effective_slots(get_settings(self.db), "Model")
        self.assertEqual(sum(bool(value) for value in before.values()), 5)
        update_portfolio_slot(self.db, self.root, "Model", 3, remove=True)
        after = effective_slots(get_settings(self.db), "Model")
        self.assertFalse(after[3])
        self.assertEqual(after[4], before[4])
        for index in (1, 2, 4, 5):
            update_portfolio_slot(self.db, self.root, "Model", index, remove=True)
        init_db(self.db)
        self.assertFalse(any(effective_slots(get_settings(self.db), "Model").values()))

    def test_failed_database_save_keeps_old_reference_without_orphan_upload(self):
        before = get_settings(self.db)["beauty_image_1"]
        with patch("scena_portfolio._persist_portfolio_slot", side_effect=OSError("database unavailable")):
            with self.assertRaises(OSError):
                update_portfolio_slot(self.db, self.root, "Professional", 1, data=original_bytes())
        self.assertEqual(get_settings(self.db)["beauty_image_1"], before)
        self.assertFalse(list((self.root / "media" / "portfolio").iterdir()))

    def test_concurrent_first_edits_preserve_both_slots_and_initial_gallery(self):
        from scena_portfolio import _validate_original

        rendezvous = threading.Barrier(2)
        def validate_together(data):
            result = _validate_original(data)
            rendezvous.wait(timeout=5)
            return result
        with patch("scena_portfolio._validate_original", side_effect=validate_together):
            with ThreadPoolExecutor(max_workers=2) as executor:
                edits = {
                    slot: executor.submit(update_portfolio_slot, self.db, self.root, "Model", slot, data=original_bytes())
                    for slot in (6, 7)
                }
                originals = {slot: future.result(timeout=10) for slot, future in edits.items()}
        settings = get_settings(self.db)
        for slot, value in originals.items():
            self.assertEqual(settings[f"model_image_{slot}"], value)
        self.assertEqual(sum(bool(value) for value in effective_slots(settings, "Model").values()), 7)

    def test_invalid_or_small_upload_does_not_replace_existing_photo(self):
        relative = update_portfolio_slot(self.db, self.root, "Professional", 1, data=original_bytes())
        tiny = io.BytesIO()
        Image.new("RGB", (90, 90)).save(tiny, "PNG")
        for invalid in (b"not an image", tiny.getvalue()):
            with self.assertRaises(ValueError):
                update_portfolio_slot(self.db, self.root, "Professional", 1, data=invalid)
        self.assertEqual(get_settings(self.db)["beauty_image_1"], relative)

    def test_private_files_paths_and_symlinks_are_not_exposed(self):
        secret = self.root / "secret.png"
        secret.write_bytes(original_bytes())
        media = self.root / "media"
        media.mkdir()
        (media / "linked.png").symlink_to(secret)
        for value in ("secret.png", "media/../secret.png", "media/linked.png", "https://example.org/photo.jpg"):
            self.assertEqual(portfolio_frames(self.root, {"beauty_image_1": value}, "ru", "Professional"), [])

    def test_user_text_cannot_break_gallery_script_or_inject_markup(self):
        value = '</script><script>alert("x")</script>'
        content = build_portfolio_html([{"slot": 1, "src": "data:image/png;base64,AAAA", "label": value}], "ru", value)
        self.assertNotIn(value, content)
        self.assertIn("\\u003c/script>", content)
        self.assertIn("&lt;script&gt;", content)

    def test_editor_keeps_selected_slot_when_its_photo_changes(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_string(
            "from pathlib import Path\n"
            "from scena_core import get_settings\n"
            "from scena_portfolio import render_portfolio_editor\n"
            f"db = Path({str(self.db)!r})\n"
            f"render_portfolio_editor(db, Path({str(self.root)!r}), get_settings(db), 'Professional')\n"
        ).run()
        app.selectbox[0].set_value(12).run()
        update_portfolio_slot(self.db, self.root, "Professional", 12, data=original_bytes())
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[0].value, 12)


if __name__ == "__main__":
    unittest.main()
