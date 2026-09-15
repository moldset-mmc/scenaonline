import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree as ET

from scena_core import init_db, get_settings
from scena_publications import save_draft, publish_local, archive_publication
from scena_seo import build_metadata, public_base, public_catalog, render_head, sitemap_xml, robots_txt, llms_txt


class SeoMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'test.db'
        init_db(self.db)
        self.settings = {**get_settings(self.db), 'public_base_url': 'https://scena.example',
                         'master_name': 'Имя владелицы', 'bio': 'Личная история.',
                         'bio_ro': 'Poveste personală.', 'bio_en': 'A personal story.'}

    def metadata(self, page='scene', locale='ru', **query):
        return build_metadata(self.settings, {'page': page, **query}, locale, db_path=self.db)

    def publish(self, **kwargs):
        item = save_draft(self.db, title_ru='История RU', title_ro='Poveste RO',
                          body_ru='Опубликованный текст.', body_ro='Text publicat.',
                          translations_approved=True, show_scene=True, **kwargs)
        publish_local(self.db, item['id'], item['revision'])
        return item

    def test_language_variants_have_self_canonical_and_reciprocal_alternates(self):
        metas = [self.metadata(locale=lang) for lang in ('ru', 'ro', 'en')]
        for meta in metas:
            self.assertTrue(meta['indexable'])
            self.assertEqual(parse_qs(urlsplit(meta['canonical']).query)['lang'], [meta['locale']])
            self.assertEqual(meta['alternates'][meta['locale']], meta['canonical'])
            self.assertEqual(meta['alternates'], metas[0]['alternates'])
        self.assertEqual(len({meta['title'] for meta in metas}), 3)
        self.assertEqual(len({meta['description'] for meta in metas}), 3)

    def test_owner_indexing_decisions_apply_to_dependent_routes(self):
        for area, pages in [('model', ['model', 'invite-model', 'join-model']),
                            ('professional', ['professional', 'booking'])]:
            self.settings[area + '_indexed'] = '0'
            for page in pages:
                meta = self.metadata(page)
                self.assertFalse(meta['indexable'])
                self.assertEqual(meta['status'], 200)
                self.assertNotEqual(meta['title'], 'SCENA · Страница')
                self.assertEqual(meta['json_ld'], {})
                self.assertEqual(meta['alternates'], {})
            self.assertFalse(self.metadata('portfolio', view=area)['indexable'])
            self.settings[area + '_indexed'] = '1'

    def test_hidden_admin_unknown_and_private_query_never_expose_profile_metadata(self):
        self.settings['bio'] = 'OWNER CONTENT DO NOT LEAK'
        queries = [{'page': 'admin'}, {'page': 'unknown'}, {'page': 'scene', 'admin': '1'},
                   {'page': 'scene', 'token': 'SECRET'}, {'page': 'booking', 'request': '42'},
                   {'page': 'post', 'post': 'missing'}, {'page': 'course', 'service': 'missing'}]
        for query in queries:
            meta = build_metadata(self.settings, query, 'ru', db_path=self.db)
            self.assertFalse(meta['indexable'], query)
            head = render_head(meta)
            self.assertNotIn('OWNER CONTENT', head)
            self.assertNotIn('SECRET', head)
            self.assertNotIn('application/ld+json', head)
        self.settings['profile_published'] = '0'
        self.assertNotIn('OWNER CONTENT', render_head(self.metadata()))
        self.assertEqual(self.metadata()['status'], 404)
        self.assertEqual(self.metadata('unknown')['status'], 404)
        self.assertEqual(self.metadata('course', service='missing')['status'], 404)
        self.assertEqual(self.metadata('post', post='missing')['status'], 404)

    def test_canonical_allowlist_strips_tracking_and_never_uses_visitor_host(self):
        meta = self.metadata(utm_source='https://evil.example/?token=SECRET', fbclid='SECRET')
        self.assertTrue(meta['indexable'])
        self.assertEqual(meta['canonical'], 'https://scena.example/?page=scene&lang=ru')
        self.assertNotIn('SECRET', render_head(meta))
        hostile = self.metadata('portfolio', view='model\"><script>evil</script>')
        self.assertFalse(hostile['indexable'])
        self.assertNotIn('evil', render_head(hostile))

    def test_only_configured_public_https_base_can_be_indexable(self):
        for base in ('http://localhost:8501', 'https://127.0.0.1', 'https://10.0.0.1',
                     'https://user:secret@example.com', 'javascript:alert(1)', '//scena.example',
                     'https://scena.example\nSitemap: https://evil.example', 'https://scena.example:invalid',
                     'https://scena.example/../private', 'https://scena.local'):
            settings = {**self.settings, 'public_base_url': base}
            self.assertEqual(public_base(settings), '', base)
            self.assertFalse(build_metadata(settings, {}, 'ru')['indexable'])
        self.assertEqual(public_base({**self.settings, 'public_base_url': 'https://scena.example/?token=secret#f'}), 'https://scena.example')

    def test_course_urls_require_active_visible_service(self):
        with sqlite3.connect(self.db) as con:
            row = con.execute("SELECT id FROM services WHERE category='Professional' AND kind='course' LIMIT 1").fetchone()
            self.assertIsNotNone(row)
            course_id = row[0]
        meta = self.metadata('course', service=str(course_id))
        self.assertTrue(meta['indexable'])
        self.assertEqual(parse_qs(urlsplit(meta['canonical']).query)['service'], [str(course_id)])
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE services SET active=0 WHERE id=?', (course_id,))
        self.assertFalse(self.metadata('course', service=str(course_id))['indexable'])
        self.assertFalse(any(item['page'] == 'course' and item['params'].get('service') == str(course_id)
                             for item in public_catalog(self.settings, db_path=self.db)))

    def test_published_snapshot_only_never_pending_draft_or_private_original(self):
        post = self.publish()
        save_draft(self.db, post['id'], body_ru='SECRET UNPUBLISHED DRAFT',
                   original_image_path='media/private-original-secret.jpg')
        meta = self.metadata('post', post=post['public_id'])
        self.assertTrue(meta['indexable'])
        rendered = render_head(meta)
        self.assertIn('Опубликованный текст', rendered)
        self.assertNotIn('SECRET', rendered)
        self.assertNotIn('original', rendered)
        self.assertNotIn('dateModified', rendered)
        self.assertNotIn('datePublished', rendered)
        self.assertTrue(any(node['@type'] == 'Article' for node in meta['json_ld']['@graph']))

    def test_archived_draft_hidden_and_untranslated_posts_not_advertised(self):
        published = self.publish()
        unpublished = save_draft(self.db, body_ru='UNPUBLISHED')
        self.assertFalse(self.metadata('post', post=unpublished['public_id'])['indexable'])
        self.assertFalse(self.metadata('post', locale='en', post=published['public_id'])['indexable'])
        ru = self.metadata('post', post=published['public_id'])
        self.assertEqual(set(ru['alternates']), {'ru', 'ro', 'x-default'})
        archive_publication(self.db, published['id'])
        self.assertFalse(self.metadata('post', post=published['public_id'])['indexable'])
        self.assertNotIn(published['public_id'], sitemap_xml(self.settings, db_path=self.db))
        self.assertNotIn('UNPUBLISHED', llms_txt(self.settings, db_path=self.db))

    def test_post_destination_visibility_respects_independent_index_flags(self):
        post = save_draft(self.db, title_ru='Модель', body_ru='Модельный текст', body_ro='Text de model',
                          translations_approved=True, show_scene=False, show_model=True)
        publish_local(self.db, post['id'], post['revision'])
        self.settings['model_indexed'] = '0'
        self.assertFalse(self.metadata('post', post=post['public_id'])['indexable'])
        self.assertEqual(self.metadata('post', post=post['public_id'])['status'], 200)
        self.assertNotIn(post['public_id'], sitemap_xml(self.settings, db_path=self.db))

    def test_metadata_escapes_html_and_json_script_termination(self):
        self.settings['master_name'] = '</title><script>alert("x")</script>'
        self.settings['bio'] = '</script><img src=x onerror=alert(1)> A text & more'
        meta = self.metadata()
        rendered = render_head(meta)
        self.assertNotIn('<script>alert', rendered)
        self.assertNotIn('<img src=x', rendered)
        payload = rendered.split('<script type="application/ld+json">', 1)[1].split('</script>', 1)[0]
        self.assertIsInstance(json.loads(payload), dict)
        self.assertEqual(rendered.count('</script>'), 1)

    def test_social_image_is_public_and_optional_not_private_original(self):
        self.settings['avatar_url'] = 'media/profile.png'
        meta = build_metadata(self.settings, {'page': 'scene'}, 'ru', image_resolver=lambda value: '/scena-assets/profile.png')
        self.assertEqual(meta['image'], 'https://scena.example/scena-assets/profile.png')
        self.assertIn('twitter:image', render_head(meta))
        for image in ('data:image/png;base64,ABC', 'https://scena.example/scena-photo/secret',
                      'https://scena.example/private/original.png', 'http://example.com/image.png'):
            rejected = build_metadata({**self.settings, 'avatar_url': image}, {'page': 'scene'}, 'ru')
            self.assertEqual(rejected['image'], '')

    def test_structured_data_uses_existing_visible_facts_not_invented_business(self):
        meta = self.metadata('professional')
        encoded = json.dumps(meta['json_ld'], ensure_ascii=False)
        self.assertIn(self.settings['location'], encoded)
        for forbidden in ('streetAddress', 'latitude', 'longitude', 'openingHours', 'aggregateRating', 'LocalBusiness'):
            self.assertNotIn(forbidden, encoded)
        self.assertTrue(any(node['@type'] == 'Service' for node in meta['json_ld']['@graph']))

    def test_sitemap_xml_reciprocal_unique_and_matches_route_metadata(self):
        post = self.publish(body_en='Published English text.')
        tree = ET.fromstring(sitemap_xml(self.settings, db_path=self.db))
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9', 'h': 'http://www.w3.org/1999/xhtml'}
        locs = [node.find('s:loc', ns).text for node in tree]
        self.assertEqual(len(locs), len(set(locs)))
        self.assertFalse(any('page=admin' in url for url in locs))
        for node in tree:
            url = node.find('s:loc', ns).text
            params = {key: value[0] for key, value in parse_qs(urlsplit(url).query).items()}
            meta = build_metadata(self.settings, params, params['lang'], db_path=self.db)
            self.assertTrue(meta['indexable'], url)
            self.assertEqual(meta['canonical'], url)
            links = {link.attrib['hreflang']: link.attrib['href'] for link in node.findall('h:link', ns)}
            self.assertEqual(links, meta['alternates'])
            self.assertTrue(all(target in locs for target in links.values()))
            self.assertIsNone(node.find('s:lastmod', ns))
        self.assertTrue(any(post['public_id'] in url for url in locs))

    def test_discovery_respects_hidden_site_and_robot_private_routes(self):
        self.settings.update(profile_indexed='0', professional_indexed='0', model_indexed='0')
        self.assertEqual(public_catalog(self.settings, db_path=self.db), [])
        self.assertNotIn(self.settings['master_name'], llms_txt(self.settings, db_path=self.db))
        robots = robots_txt(self.settings)
        self.assertIn('User-agent: *\nAllow: /', robots)
        self.assertIn('Sitemap: https://scena.example/sitemap.xml', robots)
        self.assertIn('Disallow: /*?*page=admin', robots)
        self.assertIn('Disallow: /auth/login', robots)
        self.assertIn('Disallow: /scena-download/', robots)
        self.assertNotIn('Disallow: /\n', robots)


if __name__ == '__main__':
    unittest.main()
