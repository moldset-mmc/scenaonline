import io
import importlib.util
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from scena_core import init_db, get_settings, save_settings


class PortableInstallationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "pilot.db"
        self.media = self.root / "media"
        self.media.mkdir()
        (self.media / "portrait.webp").write_bytes(b"owned original bytes")
        init_db(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_backup_restore_preserves_owner_settings_and_originals(self):
        from scena_transfer import build_backup, inspect_backup, restore_backup
        save_settings(self.db, {"master_name": "Мария Бараночникова"})
        archive = build_backup(self.db, self.media)
        preview = inspect_backup(archive)
        self.assertEqual(preview["kind"], "private_backup")
        self.assertTrue(preview["contains_private_data"])
        result = restore_backup(archive, self.root / "restored")
        self.assertEqual(get_settings(result["db_path"])["master_name"], "Мария Бараночникова")
        self.assertEqual((Path(result["media_dir"]) / "portrait.webp").read_bytes(), b"owned original bytes")
        self.assertEqual(inspect_backup(build_backup(result["db_path"], result["media_dir"]))["identity"], preview["identity"])

    def test_committed_changes_in_live_wal_database_survive_backup(self):
        from scena_transfer import build_backup, restore_backup
        with sqlite3.connect(self.db) as live_connection:
            live_connection.execute("PRAGMA journal_mode=WAL")
            save_settings(self.db, {"master_name": "Сохранено в работающей Сцене"})
            result = restore_backup(build_backup(self.db, self.media), self.root / "wal-copy")
        self.assertEqual(get_settings(result["db_path"])["master_name"], "Сохранено в работающей Сцене")

    def test_restore_rejects_tampering_and_does_not_overwrite_existing_files(self):
        from scena_transfer import build_backup, inspect_backup, restore_backup, TransferValidationError
        archive = build_backup(self.db, self.media)
        with zipfile.ZipFile(io.BytesIO(archive)) as source:
            files = {name: source.read(name) for name in source.namelist()}
        files["media/portrait.webp"] = b"tampered"
        corrupted = io.BytesIO()
        with zipfile.ZipFile(corrupted, "w") as output:
            for name, data in files.items():
                output.writestr(name, data)
        target = self.root / "must-not-exist"
        with self.assertRaises(TransferValidationError):
            restore_backup(corrupted.getvalue(), target)
        self.assertFalse(target.exists())
        with self.assertRaises(TransferValidationError):
            restore_backup(archive, self.root)
        self.assertEqual((self.media / "portrait.webp").read_bytes(), b"owned original bytes")

    def test_restore_rejects_traversal_duplicate_and_symlink_archives(self):
        from scena_transfer import build_backup, inspect_backup, TransferValidationError
        archive = build_backup(self.db, self.media)
        for malicious in ("../escape.txt", "C:/escape.txt", "media/../escape.txt", "media\\escape.txt", "media/Portrait.webp"):
            buffer = io.BytesIO(archive)
            with zipfile.ZipFile(buffer, "a") as output:
                output.writestr(malicious, b"unexpected")
            with self.subTest(path=malicious), self.assertRaises(TransferValidationError):
                inspect_backup(buffer.getvalue())
        buffer = io.BytesIO(archive)
        with zipfile.ZipFile(buffer, "a") as output:
            entry = zipfile.ZipInfo("media/link")
            entry.create_system = 3
            entry.external_attr = 0o120777 << 16
            output.writestr(entry, "/outside")
        with self.assertRaises(TransferValidationError):
            inspect_backup(buffer.getvalue())

    def test_backup_rejects_media_symlink_and_restores_into_empty_directory(self):
        from scena_transfer import build_backup, restore_backup, TransferValidationError
        (self.media / "link.webp").symlink_to(self.db)
        with self.assertRaises(TransferValidationError):
            build_backup(self.db, self.media)
        (self.media / "link.webp").unlink()
        target = self.root / "empty"
        target.mkdir()
        restored = restore_backup(build_backup(self.db, self.media), target)
        self.assertEqual(get_settings(restored["db_path"])["master_name"], "Мария Бараночникова")

    def test_public_export_excludes_private_media_data_and_unpublished_revision(self):
        from scena_transfer import build_platform_export, inspect_backup
        from scena_publications import save_draft, publish_local
        save_settings(self.db, {"avatar_url": "media/portrait.webp", "support_secret": "must not travel"})
        (self.media / "private.webp").write_bytes(b"private photo must not travel")
        post = save_draft(self.db, title_ru="Публичная история", body_ru="Публичный текст", body_ro="Public text", translations_approved=True)
        publish_local(self.db, post["id"], post["revision"])
        save_draft(self.db, post["id"], body_ru="PRIVATE DRAFT MUST NOT TRAVEL")
        private_post = save_draft(self.db, title_ru="PRIVATE STORY", body_ru="PRIVATE STORY BODY")
        export = build_platform_export(self.db, self.media)
        preview = inspect_backup(export)
        self.assertFalse(preview["contains_private_data"])
        with zipfile.ZipFile(io.BytesIO(export)) as source:
            names = source.namelist()
            self.assertNotIn("scena_master.db", names)
            self.assertIn("media/portrait.webp", names)
            self.assertNotIn("media/private.webp", names)
            content = json.loads(source.read("public-content.json"))
            self.assertEqual(content["posts"][0]["body_ru"], "Публичный текст")
            self.assertNotIn("PRIVATE", source.read("public-content.json").decode())
            self.assertNotIn("must not travel", source.read("public-content.json").decode())
            self.assertNotIn("requests", content)
            self.assertTrue(content["object_mappings"])
        again = build_platform_export(self.db, self.media)
        with zipfile.ZipFile(io.BytesIO(again)) as source:
            self.assertEqual(json.loads(source.read("public-content.json"))["object_mappings"], content["object_mappings"])

    def test_restore_rejects_executable_database_schema(self):
        from scena_transfer import build_backup, restore_backup, TransferValidationError
        with sqlite3.connect(self.db) as connection:
            connection.execute("CREATE TRIGGER injected AFTER INSERT ON profile_settings BEGIN DELETE FROM services; END")
        archive = build_backup(self.db, self.media)
        target = self.root / "must-not-restore"
        with self.assertRaises(TransferValidationError):
            restore_backup(archive, target)
        self.assertFalse(target.exists())

    def test_owner_can_restore_a_launchable_copy_without_copying_operator_secrets(self):
        from scena_transfer import build_backup, TransferValidationError
        from scena_restore import REQUIRED_APPLICATION_FILES, restore_installation
        app = self.root / "application"
        app.mkdir()
        for name in REQUIRED_APPLICATION_FILES:
            (app / name).write_text("# application fixture", encoding="utf-8")
        (app / "scena_app.py").write_text("# application fixture", encoding="utf-8")
        (app / "START-SCENA.cmd").write_text("@echo fixture", encoding="utf-8")
        (app / "start_scena.py").write_text("# launcher fixture", encoding="utf-8")
        (app / "requirements.txt").write_text("streamlit", encoding="utf-8")
        (app / ".env").write_text("TOKEN=do-not-copy", encoding="utf-8")
        (app / ".streamlit").mkdir()
        (app / ".streamlit" / "secrets.toml").write_text("token='do-not-copy'", encoding="utf-8")
        archive = build_backup(self.db, self.media)
        target = self.root / "restored-app"
        result = restore_installation(archive, app, target)
        self.assertEqual((target / "START-SCENA.cmd").read_text(), "@echo fixture")
        self.assertFalse((target / ".env").exists())
        self.assertFalse((target / ".streamlit" / "secrets.toml").exists())
        self.assertEqual(get_settings(result["db_path"])["master_name"], "Мария Бараночникова")
        with self.assertRaises(TransferValidationError):
            restore_installation(archive, app, target)
        self.assertEqual((self.media / "portrait.webp").read_bytes(), b"owned original bytes")
        (app / "scena_publication_ui.py").unlink()
        incomplete_target = self.root / "must-not-create-incomplete"
        with self.assertRaises(TransferValidationError):
            restore_installation(archive, app, incomplete_target)
        self.assertFalse(incomplete_target.exists())

    def test_archived_public_permalink_survives_export_without_its_photo_or_text(self):
        from scena_transfer import build_platform_export
        from scena_publications import save_draft, publish_local, archive_publication
        public = save_draft(self.db, body_ru="Текст исчезнет", body_ro="Text ascuns", translations_approved=True)
        publish_local(self.db, public["id"], public["revision"])
        archive_publication(self.db, public["id"])
        private = save_draft(self.db, body_ru="Никогда не опубликовано")
        archive_publication(self.db, private["id"])
        with zipfile.ZipFile(io.BytesIO(build_platform_export(self.db, self.media))) as source:
            posts = json.loads(source.read("public-content.json"))["posts"]
        self.assertEqual(posts, [{"id": public["public_id"], "public_revision": public["revision"], "status": "archived"}])

    def test_hidden_service_group_is_absent_from_public_export(self):
        from scena_core import add_service_group, add_service, set_service_group_active, list_services
        from scena_transfer import build_platform_export
        group = add_service_group(self.db, category="Professional", name_ru="HIDDEN GROUP", name_ro="HIDDEN GRUP", description_ru="HIDDEN DESCRIPTION")
        service = add_service(self.db, category="Professional", name="HIDDEN SERVICE", name_ro="HIDDEN SERVICIU", description_ru="HIDDEN OFFER", description_ro="HIDDEN OFERTA", translations_approved=True, price=98765, duration=60, group_id=group)
        set_service_group_active(self.db, group, False)
        self.assertNotIn(service, {item["id"] for item in list_services(self.db)})
        with zipfile.ZipFile(io.BytesIO(build_platform_export(self.db, self.media))) as source:
            content = source.read("public-content.json").decode("utf-8")
        self.assertNotIn("HIDDEN", content)
        self.assertNotIn("98765", content)

    def test_hidden_scene_suppresses_posts_and_their_media_but_keeps_public_professional_page(self):
        from scena_publications import save_draft, publish_local
        from scena_transfer import build_platform_export
        (self.media / "post.webp").write_bytes(b"private when scene hidden")
        post = save_draft(self.db, body_ru="HIDDEN POST", body_ro="HIDDEN TEXT", image_url="media/post.webp", translations_approved=True, show_professional=True)
        publish_local(self.db, post["id"], post["revision"])
        save_settings(self.db, {"profile_published": "0", "professional_published": "1", "model_published": "0", "avatar_url": "media/portrait.webp"})
        with zipfile.ZipFile(io.BytesIO(build_platform_export(self.db, self.media))) as source:
            content = json.loads(source.read("public-content.json"))
            self.assertEqual(content["posts"], [])
            self.assertNotIn("media/post.webp", source.namelist())
            self.assertNotIn("media/portrait.webp", source.namelist())
        self.assertNotIn("bio", content["profile"])
        self.assertNotIn("model", content["profile"])
        self.assertIn("professional", content["profile"])
        self.assertTrue(content["services"])

    @unittest.skipUnless(importlib.util.find_spec("streamlit"), "Streamlit dependencies are not installed")
    def test_full_restored_application_imports_and_opens_scene_and_publications_cabinet(self):
        from scena_transfer import build_backup
        from scena_restore import restore_installation
        project = Path(__file__).resolve().parents[1]
        source = self.root / "complete-application"
        source.mkdir()
        for file in project.iterdir():
            if file.is_file() and (file.suffix in (".py", ".cmd") or file.name == "requirements.txt"):
                shutil.copyfile(file, source / file.name)
        target = self.root / "complete-restored"
        result = restore_installation(build_backup(self.db, self.media), source, target)
        script = """
from pathlib import Path
import scena_app
import scena_publication_ui
root = Path.cwd()
assert Path(scena_app.__file__).parent == root
assert Path(scena_publication_ui.__file__).parent == root
from streamlit.testing.v1 import AppTest
scene = AppTest.from_file(str(root / 'scena-master-standalone.py'), default_timeout=20)
scene.query_params.update({'page': 'scene', 'lang': 'ru'})
scene.run()
assert not scene.exception, [item.message for item in scene.exception]
admin = AppTest.from_file(str(root / 'scena-master-standalone.py'), default_timeout=20)
admin.query_params.update({'page': 'admin', 'admin': '1', 'section': 'promotion', 'view': 'posts', 'lang': 'ru'})
admin.session_state['scena_admin_authenticated'] = True
admin.run()
assert not admin.exception, [item.message for item in admin.exception]
next(item for item in admin.button if item.key == 'publications_create').click().run()
assert not admin.exception, [item.message for item in admin.exception]
assert any(item.label == 'Заголовок RU' for item in admin.text_input)
print('RESTORED_APP_SCENE_AND_PUBLICATIONS=PASS')
"""
        environment = {**os.environ, "PYTHONPATH": str(target), "SCENA_DB_PATH": result["db_path"], "SCENA_ADMIN_PASSWORD": "restore-test-password"}
        completed = subprocess.run([sys.executable, "-c", script], cwd=target, env=environment, capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("RESTORED_APP_SCENE_AND_PUBLICATIONS=PASS", completed.stdout)

    def test_upgrade_real_v14_preserves_owner_data_and_old_database(self):
        project = Path(__file__).resolve().parents[1]
        baseline = project.parent.parent / "work-v14" / "SCENA-PILOT-V1.4" / "scena_master.db"
        if not baseline.is_file():
            self.skipTest("Historical V1.4 acceptance fixture is not available")
        old = self.root / "old-v14"
        old.mkdir()
        old_db = old / "scena_master.db"
        shutil.copyfile(baseline, old_db)
        (old / "media").mkdir()
        photo = old / "media" / "owner-photo.webp"
        photo.write_bytes(b"original owner photo from old pilot")
        with sqlite3.connect(old_db) as connection:
            connection.execute("UPDATE profile_settings SET value=? WHERE key='master_name'", ("Мария Бараночникова — моя настройка",))
            connection.execute("UPDATE profile_settings SET value=? WHERE key='bio'", ("Моя сохранённая история",))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM app_meta WHERE key IN ('installation_id','owner_id')").fetchone()[0], 0)
        old_hash = hashlib.sha256(old_db.read_bytes()).hexdigest()
        new = self.root / "new-v15"
        new.mkdir()
        for file in project.iterdir():
            if file.is_file() and (file.suffix in (".py", ".cmd") or file.name == "requirements.txt"):
                shutil.copyfile(file, new / file.name)
        shutil.copyfile(self.db, new / "scena_master.db")
        stock_hash = hashlib.sha256((new / "scena_master.db").read_bytes()).hexdigest()
        completed = subprocess.run([sys.executable, str(new / "scena_upgrade.py")], input=str(old) + "\nДА\n", cwd=new, capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        copies = list(self.root.glob("SCENA-UPGRADED-V1.7-*"))
        self.assertEqual(len(copies), 1)
        upgraded = copies[0]
        self.assertIn("Мария Бараночникова — моя настройка", completed.stdout)
        self.assertEqual(get_settings(upgraded / "scena_master.db")["bio"], "Моя сохранённая история")
        self.assertEqual((upgraded / "media" / photo.name).read_bytes(), photo.read_bytes())
        self.assertEqual(hashlib.sha256(old_db.read_bytes()).hexdigest(), old_hash)
        self.assertEqual(hashlib.sha256((new / "scena_master.db").read_bytes()).hexdigest(), stock_hash)
        self.assertTrue((upgraded / "scena_publication_ui.py").is_file())
        self.assertEqual((upgraded / "scena_publication_ui.py").read_bytes(), (new / "scena_publication_ui.py").read_bytes())
        init_db(upgraded / "scena_master.db")
        from scena_publications import get_installation_identity
        identity = get_installation_identity(upgraded / "scena_master.db")
        init_db(upgraded / "scena_master.db")
        self.assertEqual(get_installation_identity(upgraded / "scena_master.db"), identity)
        self.assertTrue(identity["owner_id"])
        self.assertEqual(hashlib.sha256(old_db.read_bytes()).hexdigest(), old_hash)


if __name__ == "__main__":
    unittest.main()
