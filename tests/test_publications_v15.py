import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

from scena_core import init_db, list_posts


class PublicationsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "pilot.db"
        init_db(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_draft_survives_restart_without_leaking_into_published_page(self):
        from scena_publications import save_draft, get_draft, get_publication, publish_local
        draft = save_draft(self.db, title_ru="Моя работа", body_ru="Первый текст")
        init_db(self.db)
        self.assertEqual(get_draft(self.db, draft["id"])["body_ru"], "Первый текст")
        self.assertIsNone(get_publication(self.db, draft["public_id"]))
        draft = save_draft(self.db, draft["id"], body_ro="Primul text", translations_approved=True)
        publish_local(self.db, draft["id"], draft["revision"])
        save_draft(self.db, draft["id"], body_ru="Частный новый текст")
        self.assertEqual(get_publication(self.db, draft["public_id"])["body_ru"], "Первый текст")
        self.assertEqual(list_posts(self.db)[0]["body_ru"], "Первый текст")

    def test_archive_hides_content_and_restore_is_a_new_private_draft(self):
        from scena_publications import (save_draft, publish_local, archive_publication,
                                        get_publication, list_versions, restore_version)
        draft = save_draft(self.db, body_ru="Текст", body_ro="Text", translations_approved=True)
        publish_local(self.db, draft["id"], draft["revision"])
        version = list_versions(self.db, draft["id"])[0]
        archive_publication(self.db, draft["id"])
        archived = get_publication(self.db, draft["public_id"])
        self.assertEqual(archived["author_name"], "Мария Бараночникова")
        self.assertNotIn("body_ru", archived)
        self.assertNotIn("image_url", archived)
        restored = restore_version(self.db, draft["id"], version["revision"])
        self.assertGreater(restored["revision"], draft["revision"])
        self.assertEqual(get_publication(self.db, draft["public_id"])["status"], "archived")
        self.assertEqual(restored["body_ru"], "Текст")

    def test_stale_preview_and_incomplete_offer_cannot_publish(self):
        from scena_publications import save_draft, publish_local, PublicationValidationError
        draft = save_draft(self.db, body_ru="Услуга", body_ro="Serviciu", kind="offer", translations_approved=True)
        with self.assertRaises(PublicationValidationError):
            publish_local(self.db, draft["id"], draft["revision"])
        updated = save_draft(self.db, draft["id"], price_text="600 MDL")
        with self.assertRaises(PublicationValidationError):
            publish_local(self.db, draft["id"], draft["revision"])
        self.assertEqual(publish_local(self.db, draft["id"], updated["revision"])["status"], "published")

    def test_upload_preserves_original_and_creates_unique_branded_portrait_derivative(self):
        from PIL import Image
        from scena_publications import store_publication_image, PublicationValidationError
        output = BytesIO()
        Image.new("RGB", (1400, 1000), "#789abc").save(output, format="PNG")
        original = output.getvalue()
        photo = store_publication_image(Path(self.temp.name), original, "../../unsafe.png")
        self.assertEqual(Path(photo["original_path"]).read_bytes(), original)
        with Image.open(photo["image_path"]) as branded:
            self.assertEqual(branded.size, (1080, 1350))
            self.assertEqual(branded.format, "JPEG")
        again = store_publication_image(Path(self.temp.name), original, "same.png")
        self.assertNotEqual(photo["original_path"], again["original_path"])
        with self.assertRaises(PublicationValidationError):
            store_publication_image(Path(self.temp.name), b"<script>bad</script>", "bad.png")

    def test_channel_draft_and_confirmed_delivery_are_durable_and_dispatched_once(self):
        from scena_publications import (save_draft, publish_local, save_channel_draft,
                                        get_channel_draft, prepare_delivery, dispatch_delivery,
                                        get_delivery, PublicationValidationError)
        draft = save_draft(self.db, body_ru="Работа", body_ro="Lucrare", translations_approved=True)
        publish_local(self.db, draft["id"], draft["revision"])
        save_channel_draft(self.db, draft["id"], "facebook", "Моя работа")
        init_db(self.db)
        self.assertEqual(get_channel_draft(self.db, draft["id"], "facebook")["caption"], "Моя работа")
        delivery = prepare_delivery(self.db, draft["id"], "facebook", "Моя работа",
                                    "https://media.example.com/scena.jpg", "https://scena.example.com/?post=" + draft["public_id"], "123")
        class Adapter:
            channel = "facebook"
            account_id = "123"
            configured = True
            def __init__(self):
                self.snapshots = []
            def publish(self, snapshot):
                self.snapshots.append(snapshot)
                return {"status": "sent", "external_id": "123_456", "url": "https://facebook.com/123_456"}
        adapter = Adapter()
        with self.assertRaises(PublicationValidationError):
            dispatch_delivery(self.db, delivery["id"], adapter, delivery["snapshot_hash"])
        with self.assertRaises(PublicationValidationError):
            dispatch_delivery(self.db, delivery["id"], adapter, "wrong", confirmed=True)
        sent = dispatch_delivery(self.db, delivery["id"], adapter, delivery["snapshot_hash"], confirmed=True)
        self.assertEqual(sent["status"], "sent")
        dispatch_delivery(self.db, delivery["id"], adapter, delivery["snapshot_hash"], confirmed=True)
        self.assertEqual(len(adapter.snapshots), 1)
        self.assertIn(draft["public_id"], adapter.snapshots[0]["caption"])
        self.assertEqual(get_delivery(self.db, delivery["id"])["url"], "https://facebook.com/123_456")

    def test_uncertain_timeout_cannot_be_resent_and_remote_secrets_are_not_retained(self):
        from scena_publications import save_draft, publish_local, prepare_delivery, dispatch_delivery, list_deliveries
        draft = save_draft(self.db, body_ru="Работа", body_ro="Lucrare", translations_approved=True)
        publish_local(self.db, draft["id"], draft["revision"])
        prepared = prepare_delivery(self.db, draft["id"], "facebook", "Работа", "https://images.example.com/a.jpg", "https://scena.example.com/post", "123")
        class Adapter:
            channel, account_id, configured = "facebook", "123", True
            def __init__(self):
                self.calls = 0
            def publish(self, snapshot):
                self.calls += 1
                raise TimeoutError("access_token=NEVER_STORE_ME")
        adapter = Adapter()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: dispatch_delivery(self.db, prepared["id"], adapter, prepared["snapshot_hash"], confirmed=True), range(2)))
        self.assertEqual(adapter.calls, 1)
        saved = list_deliveries(self.db, draft["id"])[0]
        self.assertEqual(saved["status"], "unknown")
        self.assertNotIn("NEVER_STORE_ME", str(saved))
        dispatch_delivery(self.db, prepared["id"], adapter, prepared["snapshot_hash"], confirmed=True)
        self.assertEqual(adapter.calls, 1)

    def test_processing_continuation_reuses_container_and_requires_confirmation(self):
        from scena_publications import save_draft, publish_local, prepare_delivery, dispatch_delivery, refresh_delivery, PublicationValidationError
        draft = save_draft(self.db, body_ru="Работа", body_ro="Lucrare", translations_approved=True)
        publish_local(self.db, draft["id"], draft["revision"])
        prepared = prepare_delivery(self.db, draft["id"], "instagram", "Работа", "https://images.example.com/a.jpg", "https://scena.example.com/post", "123")
        class Adapter:
            channel, account_id, configured = "instagram", "123", True
            def publish(self, snapshot):
                return {"status": "processing", "container_id": "987", "publish_attempted": False}
            def check_status(self, result):
                if result["container_id"] != "987":
                    raise AssertionError("Lost existing container")
                return {"status": "sent", "external_id": "654", "container_id": "987", "publish_attempted": True}
        adapter = Adapter()
        dispatch_delivery(self.db, prepared["id"], adapter, prepared["snapshot_hash"], confirmed=True)
        with self.assertRaises(PublicationValidationError):
            refresh_delivery(self.db, prepared["id"], adapter, prepared["snapshot_hash"])
        result = refresh_delivery(self.db, prepared["id"], adapter, prepared["snapshot_hash"], confirmed=True)
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["container_id"], "987")

    def test_legacy_post_and_identity_survive_reinitialization(self):
        from scena_core import add_post, set_post_active
        from scena_publications import get_installation_identity, list_publications, get_publication
        post_id = add_post(self.db, title_ru="До обновления", title_ro="Înainte", body_ru="История", body_ro="Poveste", translations_approved=True)
        set_post_active(self.db, post_id, True)
        identity = get_installation_identity(self.db)
        initial = next(p for p in list_publications(self.db) if p["id"] == post_id)
        init_db(self.db)
        current = next(p for p in list_publications(self.db) if p["id"] == post_id)
        self.assertEqual(identity, get_installation_identity(self.db))
        self.assertEqual(initial["public_id"], current["public_id"])
        self.assertEqual(get_publication(self.db, current["public_id"])["body_ru"], "История")

    def test_low_quality_original_stays_saved_but_cannot_be_published(self):
        from PIL import Image
        from scena_publications import store_publication_image, save_draft, publish_local, PublicationValidationError
        raw = BytesIO()
        Image.new("RGB", (250, 300)).save(raw, format="PNG")
        stored = store_publication_image(Path(self.temp.name), raw.getvalue(), "small.png")
        self.assertFalse(stored["publication_allowed"])
        self.assertTrue(Path(stored["original_path"]).exists())
        draft = save_draft(self.db, body_ru="История", body_ro="Poveste", translations_approved=True,
                           image_url=stored["image_url"], original_image_path=stored["original_image_path"])
        with self.assertRaises(PublicationValidationError):
            publish_local(self.db, draft["id"], draft["revision"])

    def test_configuration_and_stale_publication_block_external_send(self):
        from scena_publications import save_draft, publish_local, prepare_delivery, dispatch_delivery, PublicationValidationError
        draft = save_draft(self.db, body_ru="Работа", body_ro="Lucrare", translations_approved=True)
        publish_local(self.db, draft["id"], draft["revision"])
        prepared = prepare_delivery(self.db, draft["id"], "facebook", "Работа", "https://images.example.com/a.jpg", "https://scena.example.com/post", "123")
        class Adapter:
            channel, account_id, configured = "facebook", "123", False
            def publish(self, snapshot):
                raise AssertionError("External call must not happen")
        adapter = Adapter()
        result = dispatch_delivery(self.db, prepared["id"], adapter, prepared["snapshot_hash"], confirmed=True)
        self.assertEqual(result["status"], "not_configured")
        adapter.configured = True
        updated = save_draft(self.db, draft["id"], body_ru="Новая работа", translations_approved=True)
        publish_local(self.db, draft["id"], updated["revision"])
        with self.assertRaises(PublicationValidationError):
            dispatch_delivery(self.db, prepared["id"], adapter, prepared["snapshot_hash"], confirmed=True)

    def test_real_instagram_adapter_continues_persisted_receipt_without_new_upload(self):
        from scena_social import InstagramAdapter
        from scena_publications import save_draft, publish_local, prepare_delivery, dispatch_delivery, refresh_delivery
        class Boundary:
            def __init__(self):
                self.responses = iter([{"id": "101"}, {"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"}, {"id": "202"}, {"permalink": "https://www.instagram.com/p/test/"}])
            def request(self, *args, **kwargs):
                return next(self.responses)
        adapter = InstagramAdapter(env={"SCENA_META_API_VERSION": "v25.0", "SCENA_INSTAGRAM_ACCOUNT_ID": "67890", "SCENA_INSTAGRAM_ACCESS_TOKEN": "never-store-token"}, transport=Boundary())
        draft = save_draft(self.db, body_ru="Работа", body_ro="Lucrare", translations_approved=True)
        publish_local(self.db, draft["id"], draft["revision"])
        prepared = prepare_delivery(self.db, draft["id"], "instagram", "Работа", "https://images.example.com/a.jpg", "https://scena.example.com/post", "67890")
        first = dispatch_delivery(self.db, prepared["id"], adapter, prepared["snapshot_hash"], confirmed=True)
        self.assertEqual(first["status"], "processing")
        result = refresh_delivery(self.db, prepared["id"], adapter, prepared["snapshot_hash"], confirmed=True)
        self.assertEqual(result["status"], "sent")
        self.assertNotIn("never-store-token", str(result))

    def test_explicit_new_preview_after_proven_failure_keeps_old_receipt_and_can_retry(self):
        from scena_publications import save_draft, publish_local, prepare_delivery, dispatch_delivery, get_delivery
        from scena_social import FacebookPagesAdapter, MetaTransportError
        draft = save_draft(self.db, body_ru="Работа", body_ro="Lucrare", translations_approved=True)
        publish_local(self.db, draft["id"], draft["revision"])
        args = (self.db, draft["id"], "facebook", "Работа", "https://images.example.com/a.jpg", "https://scena.example.com/post", "123")
        first = prepare_delivery(*args)
        class Boundary:
            def __init__(self):
                self.calls = 0
            def request(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise MetaTransportError(429)
                return {"id": "456", "post_id": "123_456"}
        boundary = Boundary()
        adapter = FacebookPagesAdapter(env={"SCENA_META_API_VERSION": "v25.0", "SCENA_FACEBOOK_PAGE_ID": "123", "SCENA_FACEBOOK_PAGE_TOKEN": "not-real-token"}, transport=boundary)
        failed = dispatch_delivery(self.db, first["id"], adapter, first["snapshot_hash"], confirmed=True)
        self.assertEqual(failed["status"], "failed")
        again = prepare_delivery(*args)
        self.assertEqual(boundary.calls, 1)
        self.assertNotEqual(again["id"], first["id"])
        self.assertEqual(again["snapshot"]["previous_delivery_id"], first["id"])
        self.assertEqual(again["status"], "prepared")
        self.assertEqual(get_delivery(self.db, first["id"])["status"], "failed")
        result = dispatch_delivery(self.db, again["id"], adapter, again["snapshot_hash"], confirmed=True)
        self.assertEqual(result["status"], "sent")
        self.assertEqual(prepare_delivery(*args)["id"], again["id"])
        self.assertEqual(boundary.calls, 2)


if __name__ == "__main__":
    unittest.main()
