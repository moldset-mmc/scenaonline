import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ModelLandingV12TestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "pilot-v12.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def settings(self):
        from scena_core import get_settings, init_db

        init_db(self.db_path)
        return get_settings(self.db_path)

    def test_five_approved_assets_are_packaged_and_public_ready(self):
        from model_landing import model_slides_from_settings

        slides = model_slides_from_settings(self.settings(), PROJECT_ROOT)

        self.assertEqual([slide["slot"] for slide in slides], [1, 2, 3, 4, 5])
        self.assertTrue(all(str(slide["src"]).startswith("data:image/webp;base64,") for slide in slides))
        self.assertTrue(all(slide["duration"] == 7000 for slide in slides))
        for slot in range(1, 6):
            path = PROJECT_ROOT / self.settings()[f"model_slide_{slot}_image"]
            self.assertTrue(path.is_file(), path)

    def test_hidden_or_unapproved_slides_remain_drafts_and_order_is_respected(self):
        from model_landing import model_slides_from_settings

        settings = self.settings()
        settings["model_slide_1_order"] = "5"
        settings["model_slide_5_order"] = "1"
        settings["model_slide_2_visible"] = "0"
        settings["model_slide_3_translations_approved"] = "0"

        slides = model_slides_from_settings(settings, PROJECT_ROOT)

        self.assertEqual([slide["slot"] for slide in slides], [5, 4, 1])

    def test_landing_is_self_contained_interactive_and_escapes_profile_text(self):
        from model_landing import build_model_landing_html

        settings = self.settings()
        settings["master_name"] = "<script>alert(1)</script> Мария"
        settings["public_base_url"] = "http://localhost:8599"
        document = build_model_landing_html(settings, "ru", PROJECT_ROOT)

        self.assertEqual(document.count('class="slide'), 6)  # slides wrapper + five figures
        self.assertIn('id="previous"', document)
        self.assertIn('id="toggle"', document)
        self.assertIn('id="next"', document)
        self.assertIn("touchstart", document)
        self.assertIn("streamlit:setFrameHeight", document)
        self.assertEqual(
            document.count('href="?page=invite-model&amp;lang=ru"'),
            1,
        )
        self.assertNotIn(
            'href="http://localhost:8599/?page=invite-model',
            document,
        )
        self.assertNotIn("<script>alert(1)</script>", document)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", document)

    def test_romanian_landing_uses_romanian_copy_and_language_routes(self):
        from model_landing import build_model_landing_html

        document = build_model_landing_html(self.settings(), "ro", PROJECT_ROOT)

        self.assertIn("MANIFEST PERSONAL", document)
        self.assertIn("INVITĂ ÎN PROIECT", document)
        self.assertIn("Lumina mea nu cere o scenă. O creează.", document)
        self.assertIn("?page=model&amp;lang=ru", document)
        self.assertIn("?page=model&amp;lang=ro", document)

    def test_qr_codes_are_local_pngs_for_three_distinct_public_urls(self):
        from model_landing import public_page_url, qr_png_bytes

        settings = self.settings()
        settings["public_base_url"] = "https://scena.example/profile/?old=1#fragment"
        urls = [public_page_url(settings, page) for page in ("scene", "professional", "model")]

        self.assertEqual(
            urls,
            [
                "https://scena.example/profile/?page=scene",
                "https://scena.example/profile/?page=professional",
                "https://scena.example/profile/?page=model",
            ],
        )
        self.assertEqual(len(set(urls)), 3)
        for url in urls:
            png = qr_png_bytes(url)
            self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertGreater(len(png), 500)

    def test_v13_admin_and_public_route_contract_are_wired(self):
        source = (PROJECT_ROOT / "scena_app.py").read_text(encoding="utf-8")

        self.assertIn('"model": "Model"', source)
        self.assertIn('"QR-коды"', source)
        self.assertIn("render_model_admin(settings)", source)
        self.assertIn("render_qr_admin(settings)", source)
        self.assertIn("build_model_landing_html(settings, locale, APP_DIR)", source)
        self.assertIn("model_slide_5", source)


if __name__ == "__main__":
    unittest.main()
