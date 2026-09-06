import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy.start_preview import main, prepare_runtime, preview_password


class PreviewIsolationTests(unittest.TestCase):
    def test_missing_password_keeps_workspace_closed(self):
        self.assertIsNone(preview_password({}))
        with self.assertRaises(RuntimeError):
            preview_password({"SCENA_ADMIN_PASSWORD": "short"})

    def test_runtime_excludes_owner_database_and_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source"
            source.mkdir()
            (source / "scena_app.py").write_text("# application")
            (source / "scena_master.db").write_bytes(b"private database")
            (source / "media").mkdir()
            (source / "media/cover.webp").write_bytes(b"bundled image")
            (source / ".streamlit").mkdir()
            (source / ".streamlit/config.toml").write_text("[theme]\nbase='light'")
            (source / ".streamlit/secrets.toml").write_text("private='not copied'")
            (source / "deploy").mkdir()
            (source / "deploy/preview-credentials.json").write_text("{}")
            runtime = prepare_runtime(source, Path(folder) / "runtime")
            self.assertTrue((runtime / "media/cover.webp").exists())
            self.assertFalse((runtime / "scena_master.db").exists())
            self.assertFalse((runtime / ".streamlit/secrets.toml").exists())
            self.assertFalse((runtime / "deploy/preview-credentials.json").exists())

    def test_production_cannot_start_temporary_preview(self):
        with patch.dict("os.environ", {"VERCEL_ENV": "production"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "preview"):
                main()


if __name__ == "__main__":
    unittest.main()
