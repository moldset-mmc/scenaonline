"""The independent card editor must not prevent a complete owner backup."""
import tempfile
import unittest
from pathlib import Path

from scena_core import init_db
from scena_business_card import get_card, save_card
from scena_transfer import build_backup, inspect_backup, restore_backup


class CardBackupTests(unittest.TestCase):
    def test_card_content_survives_a_full_backup_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'media').mkdir()
            database=root/'scena.db'
            init_db(database)
            card=get_card(database)
            saved=save_card(database,root,{'first_name':'Тест сохранения','phone':'+37360000000'},expected=card)
            archive=build_backup(database,root/'media')
            self.assertTrue(inspect_backup(archive)['contains_private_data'])
            restored=restore_backup(archive,root/'restored')
            self.assertEqual(get_card(restored['db_path']),saved)


if __name__=='__main__':
    unittest.main()
