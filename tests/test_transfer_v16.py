"""Twelve-frame portfolio data must survive exports without exposing hidden roles."""

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from scena_core import get_settings, init_db, save_settings
from scena_portfolio import update_portfolio_slot
from scena_transfer import build_backup, build_platform_export, inspect_backup, restore_backup


class PortfolioTransferV16Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.media = self.root / "media"
        self.media.mkdir()
        self.db = self.root / "scena.db"
        init_db(self.db)
        # An existing owner has deliberately started both portfolio collections.
        save_settings(self.db, {"beauty_portfolio_customized": "1", "model_portfolio_customized": "1"})
        self.originals = {}
        self.references = {}
        for direction, color in (("professional", "#893d42"), ("model", "#384b79")):
            stream = io.BytesIO()
            Image.new("RGB", (720, 960), color).save(stream, format="PNG")
            self.originals[direction] = stream.getvalue()
            self.references[direction] = update_portfolio_slot(
                self.db, self.root, direction, 12, data=stream.getvalue()
            )
        (self.media / "private-original.png").write_bytes(b"unreferenced private original")

    def tearDown(self):
        self.temporary.cleanup()

    def test_public_export_contains_twelfth_frames_and_their_verified_checksums(self):
        data = build_platform_export(self.db, self.media)
        self.assertFalse(inspect_backup(data)["contains_private_data"])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            content = json.loads(archive.read("public-content.json"))
            files = {item["path"]: item for item in json.loads(archive.read("manifest.json"))["files"]}
            for direction, prefix in (("professional", "beauty"), ("model", "model")):
                with self.subTest(direction=direction):
                    reference = self.references[direction]
                    self.assertEqual(content["profile"][direction][prefix + "_image_12"], reference)
                    self.assertEqual(content["profile"][direction][prefix + "_portfolio_customized"], "1")
                    self.assertEqual(archive.read(reference), self.originals[direction])
                    self.assertEqual(files[reference]["sha256"], hashlib.sha256(self.originals[direction]).hexdigest())
            self.assertNotIn("media/private-original.png", archive.namelist())
            self.assertNotIn("scena_master.db", archive.namelist())

    def test_public_export_excludes_each_hidden_direction_and_its_twelfth_photo(self):
        for visible, hidden in (("professional", "model"), ("model", "professional")):
            with self.subTest(hidden=hidden):
                save_settings(self.db, {visible + "_published": "1", hidden + "_published": "0"})
                with zipfile.ZipFile(io.BytesIO(build_platform_export(self.db, self.media))) as archive:
                    content = json.loads(archive.read("public-content.json"))
                    self.assertNotIn(hidden, content["profile"])
                    self.assertIn(visible, content["profile"])
                    self.assertNotIn(self.references[hidden], archive.namelist())
                    self.assertIn(self.references[visible], archive.namelist())
                    self.assertNotIn("media/private-original.png", archive.namelist())

    def test_private_restore_preserves_twelfth_frames_even_when_direction_is_hidden(self):
        save_settings(self.db, {"model_published": "0"})
        backup = build_backup(self.db, self.media)
        restored = restore_backup(backup, self.root / "restored")
        settings = get_settings(restored["db_path"])
        for direction, prefix in (("professional", "beauty"), ("model", "model")):
            with self.subTest(direction=direction):
                reference = settings[prefix + "_image_12"]
                self.assertEqual(reference, self.references[direction])
                self.assertEqual(settings[prefix + "_portfolio_customized"], "1")
                self.assertEqual((Path(restored["db_path"]).parent / reference).read_bytes(), self.originals[direction])
        self.assertEqual(settings["model_published"], "0")
        self.assertEqual((Path(restored["media_dir"]) / "private-original.png").read_bytes(), b"unreferenced private original")

    def test_public_export_preserves_deliberately_empty_model_portfolio_flag(self):
        update_portfolio_slot(self.db, self.root, "model", 12, remove=True)
        with zipfile.ZipFile(io.BytesIO(build_platform_export(self.db, self.media))) as archive:
            profile = json.loads(archive.read("public-content.json"))["profile"]["model"]
            self.assertEqual(profile["model_portfolio_customized"], "1")
            self.assertEqual(profile["model_image_12"], "")
            self.assertNotIn(self.references["model"], archive.namelist())


if __name__ == "__main__":
    unittest.main()
