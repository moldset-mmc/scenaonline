"""A Model card exports published content, while private backups retain originals."""
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from PIL import Image

from scena_core import get_settings, init_db, save_settings
from scena_model_intro import DEFAULT_INTRO_SETTINGS
from scena_transfer import build_backup, build_platform_export, restore_backup


class ModelIntroExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / "media"
        self.media.mkdir()
        self.db = self.root / "scena.db"
        init_db(self.db)
        self.photo = "media/intro-original.png"
        image = io.BytesIO()
        Image.new("RGB", (720, 960), "#5c5947").save(image, "PNG")
        self.original = image.getvalue()
        (self.root / self.photo).write_bytes(self.original)
        self.intro = {**DEFAULT_INTRO_SETTINGS,
                      "model_intro_image": self.photo,
                      "model_intro_text_ru": "Мой личный текст визитки.",
                      "model_intro_text_ro": "Textul meu personal de prezentare.",
                      "model_intro_details_ru": "Мои интересы и путешествия.",
                      "model_intro_details_ro": "Interesele și călătoriile mele."}
        save_settings(self.db, {**self.intro, "model_published": "1",
                               "professional_published": "0", "profile_published": "0"})

    def export(self):
        with zipfile.ZipFile(io.BytesIO(build_platform_export(self.db, self.media))) as archive:
            content = json.loads(archive.read("public-content.json"))
            return content, {name: archive.read(name) for name in archive.namelist()}

    def test_complete_card_exports_explicit_fields_and_original_photo(self):
        content, files = self.export()
        model = content["profile"]["model"]
        self.assertEqual({key: model[key] for key in DEFAULT_INTRO_SETTINGS}, self.intro)
        self.assertEqual(files[self.photo], self.original)
        self.assertNotIn("scena_master.db", files)

    def test_hidden_or_unreviewed_card_never_exports_its_text_or_photo(self):
        invalid = [("model_intro_enabled", "0"),
                   ("model_intro_translations_approved", "0"),
                   ("model_intro_details_ro", " ")]
        invalid += [(f"model_intro_{field}_{lang}", " ")
                    for field in ("title", "text", "alt") for lang in ("ru", "ro")]
        for field, value in invalid:
            with self.subTest(field=field):
                save_settings(self.db, {**self.intro, field: value})
                content, files = self.export()
                self.assertFalse(set(DEFAULT_INTRO_SETTINGS) & set(content["profile"]["model"]))
                self.assertNotIn(self.photo, files)
                self.assertNotIn(self.intro["model_intro_text_ru"], files["public-content.json"].decode())

    def test_hidden_model_excludes_whole_card(self):
        save_settings(self.db, {"model_published": "0"})
        content, files = self.export()
        self.assertNotIn("model", content["profile"])
        self.assertNotIn(self.photo, files)

    def test_missing_corrupt_external_or_unsafe_photo_is_not_exported(self):
        (self.media / "broken.png").write_bytes(b"not a photo")
        for photo in ("media/missing.png", "media/broken.png", "../intro-original.png",
                      "https://example.invalid/portrait.png", "media/../outside.png"):
            with self.subTest(photo=photo):
                save_settings(self.db, {"model_intro_image": photo})
                content, files = self.export()
                self.assertFalse(set(DEFAULT_INTRO_SETTINGS) & set(content["profile"]["model"]))
                self.assertNotIn(self.photo, files)
                self.assertNotIn("media/broken.png", files)

    def test_empty_optional_details_are_public_ready(self):
        save_settings(self.db, {"model_intro_details_ru": "", "model_intro_details_ro": ""})
        content, files = self.export()
        self.assertEqual(content["profile"]["model"]["model_intro_details_ru"], "")
        self.assertIn(self.photo, files)

    def test_private_backup_restores_unpublished_card_and_unused_original(self):
        save_settings(self.db, {"model_intro_enabled": "0", "model_intro_translations_approved": "0"})
        (self.media / "older-original.png").write_bytes(self.original)
        backup = build_backup(self.db, self.media)
        with zipfile.ZipFile(io.BytesIO(backup)) as archive:
            public = json.loads(archive.read("public-content.json"))
            self.assertNotIn("model_intro_text_ru", public["profile"]["model"])
        restored = restore_backup(backup, self.root / "restored")
        settings = get_settings(restored["db_path"])
        self.assertEqual(settings["model_intro_text_ru"], self.intro["model_intro_text_ru"])
        self.assertEqual(settings["model_intro_translations_approved"], "0")
        self.assertEqual((Path(restored["media_dir"]) / "intro-original.png").read_bytes(), self.original)
        self.assertEqual((Path(restored["media_dir"]) / "older-original.png").read_bytes(), self.original)

    def test_slides_require_both_reviewed_languages_before_public_export(self):
        slide_image = "media/slide-original.png"
        (self.root / slide_image).write_bytes(self.original)
        prefix = "model_slide_1"
        values = {prefix + "_image": slide_image,
                  prefix + "_visible": "1", prefix + "_translations_approved": "1",
                  prefix + "_manifesto_ru": "Текст кадра", prefix + "_manifesto_ro": "Textul imaginii",
                  prefix + "_alt_ru": "Описание кадра", prefix + "_alt_ro": "Descrierea imaginii"}
        for suffix in ("_visible", "_translations_approved", "_image", "_manifesto_ru",
                       "_manifesto_ro", "_alt_ru", "_alt_ro"):
            with self.subTest(suffix=suffix):
                save_settings(self.db, {**values, prefix + suffix: ""})
                content, files = self.export()
                self.assertFalse(any(key.startswith(prefix + "_") for key in content["profile"]["model"]))
                self.assertNotIn(slide_image, files)
        save_settings(self.db, values)
        content, files = self.export()
        self.assertEqual(content["profile"]["model"][prefix + "_translations_approved"], "1")
        self.assertEqual(files[slide_image], self.original)


if __name__ == "__main__":
    unittest.main()
