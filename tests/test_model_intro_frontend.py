"""The generated Model business card, exercised in a real offline Chromium."""

import os
import tempfile
import unittest
from pathlib import Path

from model_landing import build_model_landing_html, model_intro_from_settings
from scena_core import get_settings, init_db


ROOT = Path(__file__).resolve().parents[1]


class ModelIntroFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest("Browser checks require Playwright.")
        executable = Path(os.environ.get("SCENA_CHROMIUM", "/tmp/scena-chromium"))
        if not executable.is_file():
            raise unittest.SkipTest("Set SCENA_CHROMIUM to run browser checks.")
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "intro.db"
            init_db(db)
            cls.settings = get_settings(db)
        cls.settings.update({
            "model_published": "1", "model_slider_enabled": "1", "model_slider_autoplay": "1",
            "model_intro_enabled": "1", "model_intro_translations_approved": "1",
            "model_intro_image": "media/scena-v13/professional-portrait.webp",
            "model_intro_title_ru": "Больше, чем один образ",
            "model_intro_title_ro": "Mai mult decât o imagine",
            "model_intro_text_ru": "Я Мария. Это моя история в фотографиях.\nОбразы, настроение и мой выход на сцену.",
            "model_intro_text_ro": "Sunt Maria. Aceasta este povestea mea în fotografii.\nImagini, emoții și apariția mea pe scenă.",
            "model_intro_details_ru": "Открыта для творческих проектов.",
            "model_intro_details_ro": "Deschisă proiectelor creative.",
            "model_intro_alt_ru": "Портрет Марии Бараночниковой",
            "model_intro_alt_ro": "Portretul Mariei Baranocikova",
        })
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=str(executable), headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 1000})
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])

    def open(self, changes=None, locale="ru"):
        self.page.goto("about:blank")
        self.page.set_content(build_model_landing_html({**self.settings, **(changes or {})}, locale, ROOT), wait_until="load")
        self.page.wait_for_function("document.querySelector('.stage').dataset.transition === 'idle'")

    def test_initial_card_blocks_autoplay_keyboard_and_swipes_but_has_one_invite(self):
        self.open()
        self.assertEqual(self.page.locator(".shell").get_attribute("data-view"), "intro")
        self.assertTrue(self.page.locator(".intro-photo > img").is_visible())
        self.assertTrue(self.page.locator(".slides").is_hidden())
        self.assertEqual(self.page.locator(".intro-photo > img").evaluate("n=>getComputedStyle(n).objectFit"), "contain")
        self.assertEqual(self.page.locator("a.invite").count(), 1)
        self.assertTrue(self.page.locator("a.invite").is_visible())
        self.assertEqual(self.page.locator("a.wordmark").count(), 1)
        self.assertTrue(self.page.locator(".controls").evaluate("n=>n.inert"))
        self.page.keyboard.press("ArrowRight")
        self.page.evaluate("""() => {
          const s=document.querySelector('.stage');
          for(const [type,x] of [['touchstart',300],['touchend',30]]) {
            const e=new Event(type);Object.defineProperty(e,'changedTouches',{value:[{clientX:x,clientY:150}]});s.dispatchEvent(e);
          }
          show(3);setPlaying(true);
        }""")
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.evaluate("({active,playing,timer,animations:document.querySelector('.slides').getAnimations({subtree:true}).length})"),
                         {"active": 0, "playing": False, "timer": None, "animations": 0})

    def test_explicit_entry_return_and_reentry_preserve_frame_and_pause(self):
        self.open()
        self.page.click("#enter-images")
        self.assertEqual(self.page.locator(".shell").get_attribute("data-view"), "images")
        self.assertTrue(self.page.evaluate("playing"))
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "return-intro")
        self.page.click("#next")
        self.page.wait_for_function("document.querySelector('.stage').dataset.transition === 'idle' && active === 1")
        self.page.click("#return-intro")
        self.assertFalse(self.page.evaluate("playing"))
        self.assertIsNone(self.page.evaluate("timer"))
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "enter-images")
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.assertEqual(self.page.locator(".shell").get_attribute("data-view"), "intro")
        self.page.click("#enter-images")
        self.assertEqual(self.page.evaluate("active"), 1)
        self.assertFalse(self.page.evaluate("playing"))
        self.page.click("#toggle")
        self.assertTrue(self.page.evaluate("playing"))

    def test_return_cancels_queued_navigation_and_finishes_hidden_transition(self):
        self.open()
        self.page.click("#enter-images")
        self.page.click("#next")
        self.page.wait_for_function("moving")
        self.page.click("#next")
        self.page.click("#return-intro")
        self.page.wait_for_function("!moving")
        self.assertEqual(self.page.evaluate("({active,requested,playing,timer})"),
                         {"active": 1, "requested": 1, "playing": False, "timer": None})
        self.assertEqual(self.page.evaluate("document.querySelector('.slides').getAnimations({subtree:true}).length"), 0)

    def test_legacy_incomplete_or_unpublished_intro_cannot_replace_existing_show(self):
        invalid_changes = [
            {"model_intro_enabled": "0"}, {"model_intro_translations_approved": "0"},
            {"model_intro_title_ro": ""}, {"model_intro_text_ru": ""},
            {"model_intro_alt_ro": ""}, {"model_intro_details_ro": ""},
            {"model_intro_image": "../private.png"}, {"model_intro_image": "javascript:alert(1)"},
            {"model_intro_image": "https://[invalid"},
            {"model_intro_image": "model_landing.py"}, {"model_published": "0"},
        ]
        for changes in invalid_changes:
            with self.subTest(changes=changes):
                self.assertIsNone(model_intro_from_settings({**self.settings, **changes}, ROOT))
        legacy = {key: value for key, value in self.settings.items() if not key.startswith("model_intro_")}
        self.page.set_content(build_model_landing_html(legacy, "ru", ROOT), wait_until="load")
        self.assertEqual(self.page.locator("#introduction").count(), 0)
        self.assertEqual(self.page.locator(".shell").get_attribute("data-view"), "images")
        self.assertTrue(self.page.locator("#next").is_visible())

    def test_intro_without_slides_and_disabled_show_have_no_dead_enter_action(self):
        for changes in ({f"model_slide_{i}_visible": "0" for i in range(1, 6)}, {"model_slider_enabled": "0"}):
            with self.subTest(changes=changes):
                self.open(changes)
                self.assertTrue(self.page.locator("#enter-images").is_hidden())
                self.assertTrue(self.page.locator("a.invite").is_visible())
                self.assertEqual(self.page.locator(".slide").count(), 0)
                self.page.evaluate("show(0);setPlaying(true);enterImages()")
                self.assertEqual(self.page.evaluate("({playing,timer})"), {"playing": False, "timer": None})

    def test_mobile_long_text_is_scrollable_and_actions_are_never_cut_off(self):
        long_text = ("Личные интересы, путешествия и мои творческие планы.\n" * 80) + "ПОСЛЕДНЯЯ СТРОКА"
        self.open({"model_intro_text_ru": long_text})
        for width, height in ((390, 844), (360, 740), (360, 640)):
            with self.subTest(width=width, height=height):
                self.page.set_viewport_size({"width": width, "height": height})
                scroll = self.page.locator(".intro-copy").evaluate("n=>({height:n.clientHeight,scroll:n.scrollHeight})")
                self.assertGreater(scroll["height"], 40)
                self.assertGreater(scroll["scroll"], scroll["height"])
                self.page.locator(".intro-copy").evaluate("n=>n.scrollTop=n.scrollHeight")
                self.assertGreater(self.page.locator(".intro-copy").evaluate("n=>n.scrollTop"), 0)
                self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width)
                for selector in ("#enter-images", ".invite"):
                    bounds = self.page.locator(selector).bounding_box()
                    self.assertGreaterEqual(bounds["x"], 0)
                    self.assertLessEqual(bounds["x"] + bounds["width"], width)
                    self.assertLessEqual(bounds["y"] + bounds["height"], height)

    def test_bilingual_escaped_content_and_reduced_motion(self):
        text = '<script>window.injected=true</script>\nМой рассказ & новые идеи'
        self.open({"model_intro_text_ru": text})
        self.assertEqual(self.page.locator(".intro-text").inner_text(), text)
        self.assertIsNone(self.page.evaluate("window.injected"))
        self.open(locale="ro")
        self.assertEqual(self.page.locator("#enter-images").inner_text(), "Vezi imaginile")
        self.assertEqual(self.page.locator("#intro-title").inner_text(), "Mai mult decât o imagine")
        self.page.emulate_media(reduced_motion="reduce")
        self.page.click("#enter-images")
        self.page.click("#next")
        self.page.wait_for_function("active === 1")
        self.assertFalse(self.page.evaluate("playing"))
        self.assertEqual(self.page.evaluate("document.querySelector('.slides').getAnimations({subtree:true}).length"), 0)

    def test_desktop_and_mobile_visual_artifacts(self):
        target = Path(os.environ.get("SCENA_INTRO_SCREENSHOT_DIR", "/tmp/scena-v161-intro-qa"))
        target.mkdir(parents=True, exist_ok=True)
        for locale, width, height in (("ru", 1440, 1000), ("ru", 390, 844), ("ro", 360, 740)):
            self.page.set_viewport_size({"width": width, "height": height})
            self.open(locale=locale)
            self.page.locator(".intro-photo > img").evaluate("n=>n.decode()")
            self.page.screenshot(path=str(target / f"intro-{locale}-{width}.png"))
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width)


if __name__ == "__main__":
    unittest.main()
