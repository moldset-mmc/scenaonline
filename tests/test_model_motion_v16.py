"""Browser regression checks for the real generated Model stage.

Set SCENA_CHROMIUM to a local Chromium executable when running these checks
outside the build environment. No server, live account, or network is required.
"""

import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ModelMotionV16Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest("Browser checks require Playwright.")
        executable = Path(os.environ.get("SCENA_CHROMIUM", "/tmp/scena-chromium"))
        if not executable.is_file():
            raise unittest.SkipTest("Set SCENA_CHROMIUM to run browser motion checks.")
        from model_landing import build_model_landing_html
        from scena_core import get_settings, init_db

        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "model-motion.db"
            init_db(db)
            settings = get_settings(db)
            settings["model_intro_enabled"] = "0"
            settings["model_slider_autoplay"] = "0"
            for index in range(1, 6):
                settings[f"model_slide_{index}_duration_seconds"] = "30"
            cls.document = build_model_landing_html(settings, "ru", ROOT)
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=str(executable),
            headless=True,
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
        self.page.set_content(self.document, wait_until="load")
        self.page.wait_for_function("document.querySelector('.stage').dataset.transition === 'idle'")

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])

    def test_outgoing_frame_keeps_current_scale_then_recedes_and_blurs(self):
        self.page.evaluate("setPlaying(true)")
        self.page.evaluate("document.querySelector('.slide.is-active img').getAnimations()[0].currentTime = 6000")
        before = self.page.evaluate("new DOMMatrix(getComputedStyle(document.querySelector('.slide.is-active img')).transform).a")
        self.assertGreater(before, 1.018)
        self.page.click("#next")
        self.page.wait_for_function("document.querySelector('.stage').dataset.transition === 'moving'")
        initial = self.page.evaluate("new DOMMatrix(getComputedStyle(document.querySelector('.slide[data-index=\"0\"] img')).transform).a")
        self.assertLess(abs(initial - before), 0.012, "The outgoing drift must not reset to its CSS base scale.")
        self.page.wait_for_timeout(550)
        middle = self.page.evaluate("({scale:new DOMMatrix(getComputedStyle(document.querySelector('.slide[data-index=\"0\"] img')).transform).a,filter:getComputedStyle(document.querySelector('.slide[data-index=\"0\"] img')).filter})")
        self.assertLess(middle["scale"], initial)
        self.assertRegex(middle["filter"], r"blur\([1-9]")
        self.page.wait_for_function("document.querySelector('.stage').dataset.transition === 'idle'")
        self.assertEqual(self.page.locator(".slide.is-active").get_attribute("data-index"), "1")
        self.assertEqual(self.page.locator(".slide.is-active").count(), 1)

    def test_rapid_navigation_finishes_latest_requested_frame_without_stale_callbacks(self):
        self.page.click("#next")
        self.page.wait_for_function("document.querySelector('.stage').dataset.transition === 'moving'")
        self.page.click("#next")
        self.page.click("#next")
        self.page.wait_for_function("document.querySelector('.stage').dataset.transition === 'idle' && document.querySelector('.slide.is-active').dataset.index === '3'")
        self.assertEqual(self.page.locator(".dot.is-current").get_attribute("data-index"), "3")
        self.assertEqual(self.page.evaluate("document.querySelectorAll('.slide:not(.is-active) img').length"), 4)
        self.assertEqual(self.page.evaluate("[...document.querySelectorAll('.slide:not(.is-active)')].flatMap(n=>n.getAnimations({subtree:true})).length"), 0)

    def test_pause_freezes_idle_motion_and_manual_navigation_still_works(self):
        self.page.evaluate("setPlaying(true)")
        self.page.wait_for_timeout(120)
        self.page.click("#toggle")
        frozen = self.page.evaluate("getComputedStyle(document.querySelector('.slide.is-active img')).transform")
        self.page.wait_for_timeout(180)
        self.assertEqual(self.page.evaluate("getComputedStyle(document.querySelector('.slide.is-active img')).transform"), frozen)
        self.assertTrue(self.page.locator("#progress").is_hidden())
        self.page.click("#next")
        self.page.wait_for_function("document.querySelector('.stage').dataset.transition === 'idle' && document.querySelector('.slide.is-active').dataset.index === '1'")
        self.assertTrue(self.page.locator("#progress").is_hidden())

    def test_failed_image_decode_keeps_last_visible_frame(self):
        self.page.evaluate("document.querySelector('.slide[data-index=\"1\"] img').src='data:image/png;base64,bm90YW5pbWFnZQ=='")
        self.page.click("#next")
        self.page.wait_for_function("document.querySelector('.stage').dataset.transition === 'idle'")
        self.assertEqual(self.page.locator(".slide.is-active").get_attribute("data-index"), "0")
        self.assertEqual(self.page.locator(".slide.is-active").count(), 1)

    def test_reduced_motion_switches_without_animations(self):
        self.page.emulate_media(reduced_motion="reduce")
        self.page.click("#next")
        self.page.wait_for_function("document.querySelector('.slide.is-active').dataset.index === '1'")
        self.assertTrue(self.page.locator("#progress").is_hidden())
        self.assertEqual(self.page.evaluate("document.querySelector('.slides').getAnimations({subtree:true}).length"), 0)

    def test_large_name_is_reduced_by_quarter_desktop_and_phone(self):
        first = self.page.locator(".first").evaluate("n=>parseFloat(getComputedStyle(n).fontSize)")
        last = self.page.locator(".last").evaluate("n=>parseFloat(getComputedStyle(n).fontSize)")
        self.assertAlmostEqual(first, 1440 * .088 * .75, delta=.1)
        self.assertAlmostEqual(last, 1440 * .044 * .75, delta=.1)
        self.page.set_viewport_size({"width": 390, "height": 844})
        mobile = self.page.locator(".last").evaluate("n=>parseFloat(getComputedStyle(n).fontSize)")
        self.assertAlmostEqual(mobile, 390 * .085 * .75, delta=.1)
        self.assertLessEqual(self.page.locator(".last").evaluate("n=>n.getBoundingClientRect().right"), 390)


if __name__ == "__main__":
    unittest.main()
