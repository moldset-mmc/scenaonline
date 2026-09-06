"""Publication privacy at the new cross-page image reuse seam."""
import unittest
from pathlib import Path
from scena_core import DEFAULT_SETTINGS
from scena_design import public_model_image


class PublicModelImageTests(unittest.TestCase):
    def test_hidden_or_unapproved_preferred_image_is_not_reused(self):
        root = Path(__file__).resolve().parents[1]
        settings = dict(DEFAULT_SETTINGS)
        for key, value in [('model_slide_1_visible', '0'), ('model_slide_1_translations_approved', '0')]:
            with self.subTest(key=key):
                edited = dict(settings, **{key: value})
                actual = public_model_image(root, edited, 1)
                self.assertTrue(actual)
                self.assertNotEqual(actual, settings['model_slide_1_image'])

    def test_unpublished_model_and_no_approved_images_have_no_public_photo(self):
        root = Path(__file__).resolve().parents[1]
        settings = dict(DEFAULT_SETTINGS, model_published='0')
        self.assertEqual(public_model_image(root, settings), '')
        settings['model_published'] = '1'
        for index in range(1,6):
            settings[f'model_slide_{index}_translations_approved'] = '0'
        self.assertEqual(public_model_image(root, settings), '')

    def test_preferred_approved_image_and_fallback_respect_owner_order(self):
        root = Path(__file__).resolve().parents[1]
        settings = dict(DEFAULT_SETTINGS)
        self.assertEqual(public_model_image(root, settings, 3), settings['model_slide_3_image'])
        settings['model_slide_1_visible'] = '0'
        settings['model_slide_5_order'] = '1'
        self.assertEqual(public_model_image(root, settings, 1), settings['model_slide_5_image'])


if __name__ == '__main__':
    unittest.main()
