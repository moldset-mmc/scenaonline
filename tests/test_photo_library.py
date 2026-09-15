import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from scena_core import init_db, get_settings, save_settings
from scena_photo_library import catalog, targets, upload_photo, assign_photo, original_path


def photo(color='navy'):
    output = io.BytesIO()
    Image.new('RGB', (800, 1000), color).save(output, 'PNG')
    return output.getvalue()


class PhotoLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'test.db'
        init_db(self.db)
        self.first = upload_photo(self.db, self.root, photo(), 'portrait.png')
        self.second = upload_photo(self.db, self.root, photo('maroon'), 'new.png')

    def target(self, key):
        return next(item for item in targets(self.db) if item['id'] == key)

    def test_upload_preserves_original_bytes_and_stays_unassigned(self):
        self.assertEqual(original_path(self.db, self.root, self.first).read_bytes(), photo())
        row = next(item for item in catalog(self.db, self.root) if item['path'] == self.first)
        self.assertFalse(row['uses'])
        self.assertEqual(get_settings(self.db)['avatar_url'], '')

    def test_replace_one_use_keeps_other_use_and_original(self):
        save_settings(self.db, {'avatar_url': self.first, 'model_intro_image': self.first})
        before = self.target('avatar_url')
        assign_photo(self.db, self.root, before['id'], self.second, before['version'])
        after = get_settings(self.db)
        self.assertEqual(after['avatar_url'], self.second)
        self.assertEqual(after['model_intro_image'], self.first)
        self.assertEqual(original_path(self.db, self.root, self.first).read_bytes(), photo())

    def test_stale_form_cannot_overwrite_new_photo(self):
        before = self.target('avatar_url')
        assign_photo(self.db, self.root, before['id'], self.first, before['version'])
        with self.assertRaises(ValueError):
            assign_photo(self.db, self.root, before['id'], self.second, before['version'])
        self.assertEqual(get_settings(self.db)['avatar_url'], self.first)

    def test_failed_publish_does_not_change_reference(self):
        before = self.target('avatar_url')
        with patch('scena_media.publish_reference', side_effect=OSError('storage unavailable')):
            with self.assertRaises(OSError):
                assign_photo(self.db, self.root, before['id'], self.first, before['version'])
        self.assertEqual(get_settings(self.db)['avatar_url'], '')

    def test_professional_cover_is_preserved_when_first_portfolio_photo_changes(self):
        save_settings(self.db, {'beauty_image_1': self.first})
        before = self.target('beauty_image_1')
        assign_photo(self.db, self.root, before['id'], self.second, before['version'])
        self.assertEqual(self.target('professional_cover_image')['path'], self.first)
        self.assertEqual(self.target('beauty_image_1')['path'], self.second)

    def test_model_slide_change_preserves_inherited_portfolio(self):
        save_settings(self.db, {'model_slide_1_image': self.first})
        before = self.target('model_slide_1_image')
        assign_photo(self.db, self.root, before['id'], self.second, before['version'])
        self.assertEqual(self.target('model_image_1')['path'], self.first)
        self.assertEqual(self.target('model_slide_1_image')['path'], self.second)

    def test_unsafe_paths_and_symlinks_are_rejected(self):
        secret = self.root / 'secret.png'
        secret.write_bytes(photo())
        (self.root / 'media' / 'linked.png').symlink_to(secret)
        for value in ('secret.png', 'media/../secret.png', 'media/linked.png', 'https://example.org/photo.png'):
            with self.assertRaises(ValueError):
                original_path(self.db, self.root, value)
        paths = {row['path'] for row in catalog(self.db, self.root)}
        self.assertNotIn('media/linked.png', paths)

    def test_catalog_does_not_download_originals(self):
        with patch('scena_media.ensure_local', side_effect=AssertionError('unexpected download')):
            self.assertEqual(len(catalog(self.db, self.root)), 2)

    def test_small_and_invalid_uploads_cannot_enter_library(self):
        tiny = io.BytesIO()
        Image.new('RGB', (10, 10)).save(tiny, 'PNG')
        for content in (b'not an image', tiny.getvalue()):
            with self.assertRaises(ValueError):
                upload_photo(self.db, self.root, content, 'invalid.png')
        self.assertEqual(len(catalog(self.db, self.root)), 2)

    def test_booking_cover_replacement_keeps_course_and_professional_covers(self):
        save_settings(self.db, {'professional_hero_image': self.first})
        before = self.target('professional_hero_image')
        assign_photo(self.db, self.root, before['id'], self.second, before['version'])
        self.assertEqual(self.target('course_cover_image')['path'], self.first)
        self.assertEqual(self.target('professional_cover_image')['path'], self.first)
        self.assertEqual(self.target('professional_hero_image')['path'], self.second)

    def test_shop_assignment_preserves_other_photos_fields_and_photo_history(self):
        from scena_shop import save_product, get_product, PRODUCT_FIELDS, ShopError
        values = {field: 'Test ' + field for field in PRODUCT_FIELDS}
        values.update(price='100', status='published', image=self.first, image_2=self.first)
        product = save_product(self.db, self.root, values)
        key = 'product:' + product['id'] + ':image'
        before = self.target(key)
        assign_photo(self.db, self.root, key, self.second, before['version'])
        after = get_product(self.db, product['id'])
        self.assertEqual(after['image'], self.second)
        self.assertEqual(after['image_2'], self.first)
        self.assertEqual(after['price_cents'], product['price_cents'])
        self.assertEqual(after['status'], product['status'])
        with self.assertRaises(ValueError):
            assign_photo(self.db, self.root, key, self.first, before['version'])
        last = self.target('product:' + product['id'] + ':image_2')
        assign_photo(self.db, self.root, last['id'], self.second, last['version'])
        self.assertIn(self.first, get_product(self.db, product['id'])['photo_history'])

    def test_cloud_only_originals_are_listed_without_hydration_or_private_urls(self):
        from scena_database import connect
        with connect(self.db) as con:
            con.execute('CREATE TABLE scena_media_files(path TEXT, bytes INTEGER, private_url TEXT)')
            con.executemany('INSERT INTO scena_media_files VALUES(?,?,?)', [
                ('media/library/cloud.png', 2000, 'private-storage-reference'),
                ('media/../secret.png', 2000, 'private-storage-reference')])
        with patch('scena_photo_library.cloud_database', return_value=True), patch('scena_media.ensure_local', side_effect=AssertionError('unexpected download')):
            rows = catalog(self.db, self.root)
        self.assertEqual(len(rows), 3)
        self.assertNotIn('private-storage-reference', str(rows))
        self.assertTrue(any(row['path'] == 'media/library/cloud.png' for row in rows))

    def test_publication_renditions_share_the_original_card(self):
        folder = self.root / 'media' / 'publications' / 'example'
        folder.mkdir(parents=True)
        (folder / 'original.png').write_bytes(photo())
        (folder / 'scena-publication.jpg').write_bytes(photo('tan'))
        rows = catalog(self.db, self.root)
        self.assertEqual(len(rows), 3)
        self.assertTrue(any(row['path'].endswith('original.png') for row in rows))
        self.assertFalse(any(row['path'].endswith('scena-publication.jpg') for row in rows))

    def test_reframed_post_still_points_to_the_exact_original(self):
        from scena_publications import store_publication_image, restyle_publication_image, save_draft
        media = store_publication_image(self.root, photo(), 'portrait.png')
        draft = save_draft(self.db, body_ru='Example', image_url=media['image_url'], original_image_path=media['original_image_path'])
        restyled = restyle_publication_image(self.root, media['original_image_path'])
        save_draft(self.db, draft['id'], image_url=restyled['image_url'])
        rows = catalog(self.db, self.root)
        self.assertEqual(len(rows), 3)
        original = next(row for row in rows if row['path'] == media['original_image_path'])
        self.assertTrue(any(use['group'] == 'posts' for use in original['uses']))
        self.assertEqual(original_path(self.db, self.root, original['path']).read_bytes(), photo())


if __name__ == '__main__':
    unittest.main()
