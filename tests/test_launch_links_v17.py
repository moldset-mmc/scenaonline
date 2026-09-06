import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from scena_core import init_db, get_settings, save_settings
from model_landing import public_page_url
class RuntimeLinksV17(unittest.TestCase):
 def test_runtime_port_updates_local_qr_but_preserves_public_domain_and_database(self):
  with tempfile.TemporaryDirectory() as directory:
   db=Path(directory)/'test.db';init_db(db)
   with patch.dict(os.environ,{'SCENA_LOCAL_BASE_URL':'http://localhost:8503'}):
    self.assertEqual(public_page_url(get_settings(db),'model'),'http://localhost:8503/?page=model')
    save_settings(db,{'public_base_url':'https://scena.example/owner'})
    self.assertEqual(public_page_url(get_settings(db),'scene'),'https://scena.example/owner/?page=scene')
   self.assertEqual(get_settings(db)['public_base_url'],'https://scena.example/owner')
 def test_default_intro_migration_does_not_overwrite_later_owner_choice(self):
  with tempfile.TemporaryDirectory() as directory:
   db=Path(directory)/'test.db';init_db(db)
   old='media/scena-v13/professional-portrait.webp'
   save_settings(db,{'model_intro_image':old});init_db(db)
   self.assertEqual(get_settings(db)['model_intro_image'],old)
if __name__=='__main__':unittest.main()
