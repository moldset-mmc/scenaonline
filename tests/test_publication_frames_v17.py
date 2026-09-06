"""Real JPEG dimensions, immutable sources, caption ownership and review gates."""
import hashlib
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageChops, ImageStat

from scena_core import init_db
from scena_publications import (
    FRAME_FORMATS, PublicationValidationError, archive_publication, get_draft,
    get_private_export_source, get_publication, list_versions, managed_original,
    publish_local, render_publication_image, restore_version, restyle_publication_image,
    save_channel_draft, get_channel_draft, save_draft, store_publication_image,
)
from scena_social_ui import _default_caption, build_social_export

ROOT = Path(__file__).resolve().parents[1]


def raw_photo(color=(210, 192, 163), size=(960, 1200)):
    output = BytesIO()
    Image.new('RGB', size, color).save(output, format='PNG')
    return output.getvalue()


class PublicationFramesV17Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root/'test.db'
        init_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_export_has_exact_announced_ratio_and_dimensions(self):
        for kind, size in FRAME_FORMATS.items():
            with self.subTest(format=kind):
                payload = render_publication_image(ROOT, raw_photo(), frame_format=kind)
                with Image.open(BytesIO(payload)) as image:
                    self.assertEqual(image.size, size)
                    self.assertEqual(image.format, 'JPEG')
                    self.assertLess(len(payload), 8*1024*1024)

    def test_photo_occupies_full_height_without_a_black_footer_and_label_is_on_photo(self):
        payload = render_publication_image(ROOT, raw_photo(), frame_style='ivory')
        with Image.open(BytesIO(payload)) as image:
            # Exact central photo pixel reaches the lower image edge; no 90px footer.
            self.assertLess(max(abs(a-b) for a,b in zip(image.getpixel((540, 1300)), (210,192,163))), 4)
            self.assertGreater(min(image.getpixel((540, 1345))), 235)
            # Signature is in the upper photo, with contrast against the flat source.
            crop = image.crop((65, 40, 330, 125)).convert('L')
            self.assertGreater(ImageStat.Stat(crop).stddev[0], 25)

    def test_frame_choices_change_only_surface_and_auto_respects_light_dark(self):
        samples = {}
        for style in ('ivory', 'sand', 'noir', 'mist'):
            image = Image.open(BytesIO(render_publication_image(ROOT, raw_photo(), frame_style=style)))
            samples[style] = image.getpixel((3, 3))
            self.assertLess(max(abs(a-b) for a,b in zip(image.getpixel((540,700)), (210,192,163))), 4)
        self.assertEqual(len(set(samples.values())), 4)
        light = Image.open(BytesIO(render_publication_image(ROOT, raw_photo((230,230,230)))))
        dark = Image.open(BytesIO(render_publication_image(ROOT, raw_photo((10,10,10)))))
        self.assertGreater(sum(light.getpixel((3,3))), 700)
        self.assertLess(sum(dark.getpixel((3,3))), 100)

    def test_restyling_is_immutable_and_published_source_ignores_new_draft(self):
        raw = raw_photo()
        photo = store_publication_image(self.root, raw, 'my-photo.png', frame_style='ivory')
        original = Path(photo['original_path'])
        old_image = Path(photo['image_path']).read_bytes()
        first = save_draft(self.db, body_ru='История', body_ro='Poveste', body_en='Story',
                           translations_approved=True, image_url=photo['image_url'],
                           original_image_path=photo['original_image_path'], frame_style='ivory')
        publish_local(self.db, first['id'], first['revision'], media_root=self.root)
        changed_photo = restyle_publication_image(self.root, photo['original_image_path'], frame_style='sand', frame_format='square')
        second = save_draft(self.db, first['id'], expected_revision=first['revision'], **changed_photo)
        self.assertNotEqual(changed_photo['image_url'], photo['image_url'])
        self.assertEqual(original.read_bytes(), raw)
        self.assertEqual(Path(photo['image_path']).read_bytes(), old_image)
        source = get_private_export_source(self.db, first['id'])
        self.assertEqual(source['image_url'], photo['image_url'])
        self.assertEqual(source['original_image_path'], photo['original_image_path'])
        public = get_publication(self.db, first['public_id'])
        self.assertNotIn('original_image_path', public)
        self.assertEqual(public['body_en'], 'Story')
        self.assertEqual(public['frame_style'], 'ivory')
        publish_local(self.db, second['id'], second['revision'], media_root=self.root)
        self.assertEqual(get_publication(self.db, first['public_id'])['frame_format'], 'square')

    def test_caption_and_download_keep_price_author_link_outside_image(self):
        photo = store_publication_image(self.root, raw_photo(), 'photo.png')
        post = {'title_en':'My work', 'body_en':'A new look.', 'kind':'offer', 'price_text':'450 MDL'}
        url='https://scene.example/?page=post&post=abc&lang=en'
        caption = _default_caption(post, 'en', url, 'Maria Baranochnikova')
        self.assertIn('450 MDL', caption)
        self.assertIn('Maria Baranochnikova', caption)
        self.assertEqual(caption.count(url),1)
        package=build_social_export(self.root, photo['image_url'], caption,
                                    original_image_path=photo['original_image_path'], frame_style='sand', frame_format='story')
        with ZipFile(BytesIO(package)) as archive:
            self.assertEqual(set(archive.namelist()), {'scena-publication.jpg','caption.txt'})
            self.assertEqual(archive.read('caption.txt').decode(),caption)
            with Image.open(BytesIO(archive.read('scena-publication.jpg'))) as image:
                self.assertEqual(image.size,(1080,1920))

    def test_english_and_frame_metadata_survive_restart_archive_and_restore(self):
        post=save_draft(self.db, title_en='My story', body_en='My own words.', body_ru='История', body_ro='Poveste', translations_approved=True, frame_style='sand')
        publish_local(self.db,post['id'],post['revision'])
        init_db(self.db)
        self.assertEqual(get_draft(self.db,post['id'])['body_en'],'My own words.')
        save_channel_draft(self.db,post['id'],'instagram','My own words.',locale='en')
        self.assertEqual(get_channel_draft(self.db,post['id'],'instagram')['locale'],'en')
        archive_publication(self.db,post['id'])
        public=get_publication(self.db,post['public_id'])
        self.assertNotIn('body_en',public)
        self.assertNotIn('frame_style',public)
        restored=restore_version(self.db,post['id'],post['revision'])
        self.assertGreater(restored['revision'],post['revision'])
        self.assertEqual(restored['frame_style'],'sand')
        self.assertEqual(restored['body_en'],'My own words.')
        self.assertFalse(restored['translations_approved'])
        self.assertEqual(get_publication(self.db,post['public_id'])['status'],'archived')

    def test_wrong_format_cannot_be_published_and_partial_english_is_rejected(self):
        photo=store_publication_image(self.root,raw_photo(),'photo.png')
        post=save_draft(self.db,body_ru='Текст',body_ro='Text',translations_approved=True,
                        image_url=photo['image_url'],original_image_path=photo['original_image_path'],frame_format='square')
        with self.assertRaises(PublicationValidationError):
            publish_local(self.db,post['id'],post['revision'],media_root=self.root)
        post=save_draft(self.db,body_ru='Текст',body_ro='Text',title_en='Only title',translations_approved=True)
        with self.assertRaises(PublicationValidationError):
            publish_local(self.db,post['id'],post['revision'])

    def test_original_path_scope_and_invalid_style_reject_before_files_are_written(self):
        outside=self.root/'private.png';outside.write_bytes(raw_photo())
        with self.assertRaises(PublicationValidationError):
            managed_original(self.root, str(outside))
        with self.assertRaises(PublicationValidationError):
            store_publication_image(self.root,raw_photo(),'photo.png',frame_style='arbitrary')
        self.assertFalse((self.root/'media/publications').exists())


if __name__=='__main__':
    unittest.main()
