"""Social adapter contract tests: only Meta HTTP is replaced; never real calls."""
import json
import tempfile
import unittest
from io import BytesIO
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from scena_social import FacebookPagesAdapter, InstagramAdapter, MetaTransportError, UrllibMetaTransport


ENV = {
    "SCENA_META_API_VERSION": "v25.0",
    "SCENA_FACEBOOK_PAGE_ID": "12345",
    "SCENA_FACEBOOK_PAGE_TOKEN": "page-test-secret",
    "SCENA_INSTAGRAM_ACCOUNT_ID": "67890",
    "SCENA_INSTAGRAM_ACCESS_TOKEN": "instagram-test-secret",
}


class MetaBoundary:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, *, headers, data=None, timeout=15):
        self.requests.append((method, url, headers, data, timeout))
        if not self.responses:
            raise AssertionError("Unexpected external HTTP call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def snapshot(adapter, **changes):
    result = {
        "channel": adapter.channel, "account_id": adapter.account_id,
        "caption": "SCENA story\nhttps://scena.example/post/hello",
        "image_url": "https://scena.example/media/hello.jpg",
        "return_url": "https://scena.example/post/hello",
        "configuration_fingerprint": adapter.configuration_status()["fingerprint"],
    }
    result.update(changes)
    return result


class AdapterTests(unittest.TestCase):
    def test_truncated_http_response_is_sanitized_at_the_external_boundary(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.side_effect = IncompleteRead(b"page-test-secret")
        with patch("scena_social.build_opener", return_value=opener):
            with self.assertRaises(MetaTransportError) as error:
                UrllibMetaTransport().request("GET", "https://graph.facebook.com/v25.0/me", headers={"Authorization": "Bearer page-test-secret"})
        self.assertNotIn("page-test-secret", str(error.exception))

    def test_unconfigured_adapter_does_not_send_or_expose_credentials(self):
        boundary = MetaBoundary()
        adapter = FacebookPagesAdapter(env={}, transport=boundary)
        self.assertFalse(adapter.configured)
        self.assertEqual(adapter.publish(snapshot(adapter))["status"], "failed")
        self.assertEqual(boundary.requests, [])

    def test_facebook_photo_is_published_as_configured_page_with_reviewed_caption(self):
        boundary = MetaBoundary({"id": "111", "post_id": "12345_222"})
        adapter = FacebookPagesAdapter(env=ENV, transport=boundary)
        result = adapter.publish(snapshot(adapter))
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["external_id"], "12345_222")
        method, url, headers, data, timeout = boundary.requests[0]
        self.assertEqual((method, url), ("POST", "https://graph.facebook.com/v25.0/12345/photos"))
        self.assertEqual(data, {"url": "https://scena.example/media/hello.jpg", "caption": snapshot(adapter)["caption"], "published": "true"})
        self.assertNotIn(ENV["SCENA_FACEBOOK_PAGE_TOKEN"], url)
        self.assertNotIn(ENV["SCENA_FACEBOOK_PAGE_TOKEN"], json.dumps(result))

    def test_instagram_creates_checks_publishes_and_reads_permalink(self):
        boundary = MetaBoundary({"id": "101"}, {"status_code": "FINISHED"}, {"id": "202"}, {"permalink": "https://www.instagram.com/p/hello/"})
        adapter = InstagramAdapter(env=ENV, transport=boundary)
        result = adapter.publish(snapshot(adapter))
        self.assertEqual((result["status"], result["external_id"], result["url"]), ("sent", "202", "https://www.instagram.com/p/hello/"))
        self.assertEqual(boundary.requests[0][1], "https://graph.instagram.com/v25.0/67890/media")
        self.assertEqual(boundary.requests[2][3], {"creation_id": "101"})

    def test_instagram_processing_resumes_same_container_only_on_explicit_check(self):
        boundary = MetaBoundary({"id": "101"}, {"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"}, {"id": "202"}, {"permalink": "https://www.instagram.com/p/hello/"})
        adapter = InstagramAdapter(env=ENV, transport=boundary)
        pending = adapter.publish(snapshot(adapter))
        self.assertEqual((pending["status"], pending["container_id"]), ("processing", "101"))
        self.assertEqual(len(boundary.requests), 2)
        result = adapter.check_status(pending)
        self.assertEqual(result["status"], "sent")
        self.assertEqual(sum(r[0] == "POST" and r[1].endswith("/media") for r in boundary.requests), 1)

    def test_instagram_publish_timeout_is_never_republished_by_status_check(self):
        boundary = MetaBoundary({"id": "101"}, {"status_code": "FINISHED"}, TimeoutError("secret-url"), {"status_code": "FINISHED"})
        adapter = InstagramAdapter(env=ENV, transport=boundary)
        unknown = adapter.publish(snapshot(adapter))
        self.assertEqual(unknown["status"], "unknown")
        self.assertTrue(unknown["publish_attempted"])
        result = adapter.check_status(unknown)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(len(boundary.requests), 4)
        self.assertNotIn("secret-url", json.dumps(result))

    def test_account_verification_is_read_only_and_binds_token_owner(self):
        for cls, payload in ((FacebookPagesAdapter, {"id": "12345", "name": "SCENA"}), (InstagramAdapter, {"user_id": "67890", "username": "scena"})):
            with self.subTest(channel=cls.channel):
                boundary = MetaBoundary(payload)
                adapter = cls(env=ENV, transport=boundary)
                self.assertEqual(boundary.requests, [])
                checked = adapter.verify_account()
                self.assertTrue(checked["verified"])
                self.assertEqual(checked["account_id"], adapter.account_id)
                self.assertTrue(all(r[0] == "GET" for r in boundary.requests))
        wrong = FacebookPagesAdapter(env=ENV, transport=MetaBoundary({"id": "999", "name": "Someone else"})).verify_account()
        self.assertFalse(wrong["verified"])

    def test_invalid_local_or_credential_urls_are_rejected_without_upload(self):
        bad_urls = ["http://scena.example/photo.jpg", "https://localhost/photo.jpg", "https://host.local/photo.jpg", "https://127.0.0.1/photo.jpg", "https://[::1]/photo.jpg", "https://2130706433/photo.jpg", "https://a:secret@scena.example/photo.jpg", "https://scena.example:444/photo.jpg", "https://scena.example/photo.jpg?access_token=secret", "https://scena.example/photo.png"]
        for url in bad_urls:
            with self.subTest(url=url):
                boundary = MetaBoundary()
                adapter = FacebookPagesAdapter(env=ENV, transport=boundary)
                self.assertEqual(adapter.publish(snapshot(adapter, image_url=url))["status"], "failed")
                self.assertEqual(boundary.requests, [])

    def test_token_rotation_requires_new_snapshot(self):
        original = FacebookPagesAdapter(env=ENV, transport=MetaBoundary())
        boundary = MetaBoundary()
        changed = FacebookPagesAdapter(env={**ENV, "SCENA_FACEBOOK_PAGE_TOKEN": "rotated-secret"}, transport=boundary)
        self.assertNotEqual(original.configuration_status()["fingerprint"], changed.configuration_status()["fingerprint"])
        self.assertEqual(changed.publish(snapshot(original))["error_code"], "configuration_changed")
        self.assertEqual(boundary.requests, [])
        for token in ("page-test-secret", "rotated-secret"):
            self.assertNotIn(token, json.dumps(changed.configuration_status()))

    def test_only_single_image_is_supported_and_sent_receipt_cannot_repeat(self):
        adapter = FacebookPagesAdapter(env=ENV, transport=MetaBoundary())
        self.assertEqual(adapter.publish(snapshot(adapter, media_type="REELS"))["error_code"], "unsupported_format")
        self.assertEqual(adapter.publish(snapshot(adapter, image_urls=["https://scena.example/one.jpg"]))["error_code"], "unsupported_format")
        self.assertEqual(adapter.publish(snapshot(adapter, status="sent"))["error_code"], "already_dispatched")

    def test_platform_rejection_and_network_uncertainty_are_distinct_and_sanitized(self):
        for response, expected in (({"error": {"message": "page-test-secret private body", "code": 190}}, "failed"), (MetaTransportError(503), "unknown"), (TimeoutError("page-test-secret"), "unknown")):
            adapter = FacebookPagesAdapter(env=ENV, transport=MetaBoundary(response))
            result = adapter.publish(snapshot(adapter))
            self.assertEqual(result["status"], expected)
            self.assertNotIn("page-test-secret", json.dumps(result))

    def test_successful_instagram_publication_survives_permalink_lookup_failure(self):
        responses = []
        for payload in ({"id": "101"}, {"status_code": "FINISHED"}, {"id": "202"}, None):
            context = MagicMock()
            if payload:
                context.__enter__.return_value.read.return_value = json.dumps(payload).encode()
            else:
                context.__enter__.return_value.read.side_effect = IncompleteRead(b"instagram-test-secret")
            responses.append(context)
        opener = MagicMock()
        opener.open.side_effect = responses
        adapter = InstagramAdapter(env=ENV)
        with patch("scena_social.build_opener", return_value=opener):
            result = adapter.publish(snapshot(adapter))
        self.assertEqual((result["status"], result["external_id"], result["url"]), ("sent", "202", ""))

    def test_unknown_instagram_outcome_can_be_confirmed_from_existing_container(self):
        boundary = MetaBoundary({"id": "101"}, {"status_code": "FINISHED"}, TimeoutError(), {"status_code": "PUBLISHED"})
        adapter = InstagramAdapter(env=ENV, transport=boundary)
        unknown = adapter.publish(snapshot(adapter))
        result = adapter.check_status(unknown)
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["external_id"], "")
        self.assertEqual(result["container_id"], "101")
        self.assertEqual(sum(r[0] == "POST" for r in boundary.requests), 2)


class SocialWorkspaceTests(unittest.TestCase):
    def test_prepared_download_keeps_branded_image_and_exact_caption(self):
        from PIL import Image
        from scena_publications import store_publication_image, PublicationValidationError
        from scena_social_ui import build_social_export
        with tempfile.TemporaryDirectory() as directory:
            image = BytesIO()
            Image.new("RGB", (1080, 1350), "#445566").save(image, "PNG")
            stored = store_publication_image(directory, image.getvalue(), "source.png")
            package = build_social_export(directory, stored["image_url"], "Точная подпись\nhttps://scena.example/post")
            with ZipFile(BytesIO(package)) as archive:
                self.assertEqual(set(archive.namelist()), {"scena-publication.jpg", "caption.txt"})
                self.assertEqual(archive.read("scena-publication.jpg"), Path(stored["image_path"]).read_bytes())
                self.assertEqual(archive.read("caption.txt").decode("utf-8"), "Точная подпись\nhttps://scena.example/post")
            with self.assertRaises(PublicationValidationError):
                build_social_export(directory, "../../outside.jpg", "Text")

    def test_unconfigured_workspace_saves_channel_caption_across_restart_without_network(self):
        from streamlit.testing.v1 import AppTest
        from scena_core import init_db
        from scena_publications import save_draft, get_channel_draft
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {}, clear=True):
            db = Path(directory) / "pilot.db"
            init_db(db)
            post = save_draft(db, body_ru="Моя работа", body_ro="Lucrarea mea")
            script = f"from scena_social_ui import render_social_workspace\nrender_social_workspace({str(db)!r}, {directory!r}, {{'public_base_url':'http://localhost:8501'}}, 'ru', {post['id']})"
            app = AppTest.from_string(script).run()
            self.assertFalse(app.exception)
            app.text_area[0].input("Моя сохранённая подпись")
            next(b for b in app.button if b.label == "Сохранить вариант").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(get_channel_draft(db, post["id"], "facebook")["caption"], "Моя сохранённая подпись")
            restarted = AppTest.from_string(script).run()
            self.assertFalse(restarted.exception)
            self.assertEqual(restarted.text_area[0].value, "Моя сохранённая подпись")
            self.assertFalse(any("Отправить в" in b.label for b in restarted.button))

    def test_configured_workspace_requires_verified_account_preview_and_confirmation(self):
        from streamlit.testing.v1 import AppTest
        from scena_core import init_db
        from scena_publications import save_draft, publish_local, save_channel_draft, list_deliveries
        from scena_social import UrllibMetaTransport
        from scena_social_ui import public_post_url
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", ENV, clear=True):
            db = Path(directory) / "pilot.db"
            init_db(db)
            post = save_draft(db, body_ru="Моя работа", body_ro="Lucrarea mea", translations_approved=True)
            publish_local(db, post["id"], post["revision"])
            settings = {"public_base_url": "https://scena.example"}
            back = public_post_url(settings, post["public_id"], "ru")
            save_channel_draft(db, post["id"], "facebook", "Моя работа", "ru", "https://scena.example/photo.jpg", back, "12345")
            script = f"from scena_social_ui import render_social_workspace\nrender_social_workspace({str(db)!r}, {directory!r}, {settings!r}, 'ru', {post['id']})"
            boundary = MetaBoundary({"id": "12345", "name": "My Page"}, {"id": "111", "post_id": "12345_222"})
            with patch.object(UrllibMetaTransport, "request", side_effect=boundary.request):
                app = AppTest.from_string(script).run()
                self.assertFalse(app.exception)
                self.assertEqual(boundary.requests, [])
                self.assertTrue(next(b for b in app.button if b.label == "Посмотреть перед отправкой").disabled)
                next(b for b in app.button if b.label == "Проверить аккаунт").click().run()
                next(b for b in app.button if b.label == "Посмотреть перед отправкой").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(len(boundary.requests), 1)
                self.assertTrue(next(b for b in app.button if b.label == "Отправить в Facebook").disabled)
                app.checkbox[0].check().run()
                next(b for b in app.button if b.label == "Отправить в Facebook").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(list_deliveries(db, post["id"])[0]["status"], "sent")
                app.run()
                self.assertEqual(len(boundary.requests), 2)
                self.assertFalse(any(b.label == "Отправить в Facebook" for b in app.button))


if __name__ == "__main__":
    unittest.main()
