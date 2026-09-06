"""Upgrade cannot bypass PRO trust validation when global Python lacks packages."""
import builtins
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import scena_upgrade


class UpgradePrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = self.root / "previous"
        self.new = self.root / "new-version"
        (self.old / "config").mkdir(parents=True)
        self.new.mkdir()
        self.key_path = self.old / "config" / "pro-issuer-public.pem"
        self.key_bytes = Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.key_path.write_bytes(self.key_bytes)
        self.source = patch.object(scena_upgrade, "__file__", str(self.new / "scena_upgrade.py"))
        self.source.start()
        self.addCleanup(self.source.stop)

    def test_missing_cryptography_stops_before_backup_or_copy_with_launcher_instruction(self):
        original_import = builtins.__import__

        def no_cryptography(name, *args, **kwargs):
            if name.startswith("cryptography"):
                raise ModuleNotFoundError("No module named 'cryptography'")
            return original_import(name, *args, **kwargs)

        output = io.StringIO()
        with patch("builtins.__import__", side_effect=no_cryptography), patch.object(scena_upgrade, "build_backup") as backup, patch.object(scena_upgrade, "restore_installation") as restore, contextlib.redirect_stdout(output):
            result = scena_upgrade.main([str(self.old)])
        self.assertEqual(result, 1)
        self.assertIn("UPGRADE-SCENA.cmd", output.getvalue())
        backup.assert_not_called()
        restore.assert_not_called()
        self.assertEqual(self.key_path.read_bytes(), self.key_bytes)
        self.assertEqual(list(self.root.glob("SCENA-UPGRADED-*")), [])

    def test_available_dependency_keeps_validation_and_preserves_valid_public_key(self):
        def restore(_bundle, _current, destination):
            destination.mkdir()
            return {"destination": str(destination)}

        summary = {"owner_name": "Test owner", "file_count": 1, "media_count": 0}
        with patch.object(scena_upgrade, "build_backup", return_value=b"fixture"), patch.object(scena_upgrade, "inspect_backup", return_value=summary), patch.object(scena_upgrade, "restore_installation", side_effect=restore), patch("builtins.input", return_value="ДА"), contextlib.redirect_stdout(io.StringIO()):
            result = scena_upgrade.main([str(self.old)])
        self.assertEqual(result, 0)
        destinations = list(self.root.glob("SCENA-UPGRADED-V1.7-*"))
        self.assertEqual(len(destinations), 1)
        self.assertEqual((destinations[0] / "config" / "pro-issuer-public.pem").read_bytes(), self.key_bytes)
        self.assertEqual(self.key_path.read_bytes(), self.key_bytes)

    def test_invalid_public_key_is_rejected_before_moving_data(self):
        self.key_path.write_bytes(b"invalid public key")
        with patch.object(scena_upgrade, "build_backup") as backup, patch.object(scena_upgrade, "restore_installation") as restore, contextlib.redirect_stdout(io.StringIO()):
            result = scena_upgrade.main([str(self.old)])
        self.assertEqual(result, 1)
        backup.assert_not_called()
        restore.assert_not_called()
        self.assertEqual(list(self.root.glob("SCENA-UPGRADED-*")), [])


if __name__ == "__main__":
    unittest.main()
