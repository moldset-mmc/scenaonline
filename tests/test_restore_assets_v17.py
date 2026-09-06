"""Upgrade must carry new distribution visuals without replacing owner media."""
import hashlib
import io
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

from model_landing import image_uri
from scena_core import get_settings, init_db, save_settings
from scena_qr import QR_SURFACES, qr_campaign_html
from scena_restore import APPLICATION_FILES, BUNDLED_MEDIA_FILES


class RestoreAssetsV17Tests(unittest.TestCase):
    def test_upgrade_supplies_new_visuals_preserving_owner_files(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old, distribution = root / 'old-pilot', root / 'new-distribution'
            old.mkdir()
            distribution.mkdir()
            old_db = old / 'scena_master.db'
            init_db(old_db)
            save_settings(old_db, {'master_name_ru': 'Сохранённое имя'})
            # The earlier installation has no Model introduction setting or QR scenes.
            with sqlite3.connect(old_db) as connection:
                connection.execute("DELETE FROM profile_settings WHERE key LIKE 'model_intro_%'")
            collision = 'media/scena-v13/professional-portrait.webp'
            personal = old / collision
            personal.parent.mkdir(parents=True)
            buffer = io.BytesIO()
            Image.new('RGB', (500, 600), '#274959').save(buffer, 'WEBP')
            personal.write_bytes(buffer.getvalue())
            self.assertFalse((old / 'media/qr-scenes').exists())
            for name in (*APPLICATION_FILES, *BUNDLED_MEDIA_FILES):
                source = project / name
                if source.is_file():
                    destination = distribution / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
            unrelated = distribution / 'media/private-owner-upload.webp'
            unrelated.write_bytes(buffer.getvalue())
            old_hash = hashlib.sha256(old_db.read_bytes()).hexdigest()
            completed = subprocess.run(
                [sys.executable, str(distribution / 'scena_upgrade.py')],
                input=f'{old}\nДА\n', cwd=distribution,
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            copies = list(root.glob('SCENA-UPGRADED-V1.7-*'))
            self.assertEqual(len(copies), 1)
            upgraded = copies[0]
            init_db(upgraded / 'scena_master.db')
            settings = get_settings(upgraded / 'scena_master.db')
            self.assertEqual(settings['master_name_ru'], 'Сохранённое имя')
            self.assertEqual((upgraded / collision).read_bytes(), personal.read_bytes())
            self.assertEqual(hashlib.sha256(old_db.read_bytes()).hexdigest(), old_hash)
            self.assertFalse((upgraded / 'media/private-owner-upload.webp').exists())
            self.assertFalse((old / 'media/qr-scenes').exists())
            for name in BUNDLED_MEDIA_FILES:
                expected = personal if name == collision else distribution / name
                self.assertEqual((upgraded / name).read_bytes(), expected.read_bytes(), name)
            intro = upgraded / settings['model_intro_image']
            with Image.open(intro) as image:
                image.verify()
            self.assertTrue(image_uri(upgraded, settings['model_intro_image']).startswith('data:image/png;base64,'))
            for page in QR_SURFACES:
                with Image.open(upgraded / f'media/qr-scenes/{page}.png') as image:
                    self.assertEqual(image.size, (1024, 1536))
                    image.verify()
                html = qr_campaign_html(settings, page, 'ru', upgraded)
                self.assertIn('data:image/png;base64,', html)
                self.assertIn('SCENA', html)
            self.assertTrue((upgraded / 'START-SCENA.cmd').is_file())


if __name__ == '__main__':
    unittest.main()
