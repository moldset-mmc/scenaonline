import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from scena_core import init_db, get_settings, save_settings
from scena_seo import build_metadata, public_catalog
from scena_urls import public_path, query_from_path, rewrite_links
from scena_web.mbstudio_migration import migrate, KEY, ORIGIN
from scena_analytics import render_analytics


class MBStudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'test.db'
        init_db(self.db)
        save_settings(self.db, {'public_base_url': 'https://scena.life', 'model_portfolio_customized':'1',
                                **{f'{p}_image_{i}':'' for p in ('beauty','model') for i in range(1,13)}})

    def test_migration_is_atomic_and_respects_later_owner_edits(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE services SET name='Дневной Makeup',description_ru='Дневной Makeup' WHERE id=1")
        prod = {'VERCEL':'1', 'VERCEL_ENV':'production'}
        self.assertEqual(migrate(self.db, {}, connector=sqlite3.connect), 'skipped_environment')
        before = get_settings(self.db)
        self.assertEqual(migrate(self.db, prod, connector=sqlite3.connect), 'migrated')
        settings = get_settings(self.db)
        self.assertEqual(settings['public_base_url'], ORIGIN)
        for key in ('profile_indexed','model_indexed','professional_indexed','master_name','currency'):
            self.assertEqual(settings[key], before[key])
        with sqlite3.connect(self.db) as db:
            self.assertIn('Кишинёве', db.execute('SELECT description_ru FROM services WHERE id=1').fetchone()[0])
            receipt = json.loads(db.execute('SELECT value FROM app_meta WHERE key=?',(KEY,)).fetchone()[0])
            self.assertEqual(receipt['previous']['public_base_url'], 'https://scena.life')
        save_settings(self.db, {'public_base_url':'https://later.example'})
        self.assertEqual(migrate(self.db, prod, connector=sqlite3.connect), 'already_recorded')
        self.assertEqual(get_settings(self.db)['public_base_url'], 'https://later.example')

    def test_migration_rollback_does_not_leave_half_changed_content(self):
        before = get_settings(self.db)
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON app_meta WHEN NEW.key LIKE 'seo_origin_migration:mbstudio%' BEGIN SELECT RAISE(ABORT,'rollback fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            migrate(self.db, {'VERCEL':'1','VERCEL_ENV':'production'}, connector=sqlite3.connect)
        self.assertEqual(get_settings(self.db), before)

    def test_routes_round_trip_and_private_routes_stay_private(self):
        examples = [({'page':'professional','lang':'ru'}, '/ru/makiyazh/'),
                    ({'page':'professional','lang':'ro'}, '/ro/machiaj/'),
                    ({'page':'professional','lang':'en'}, '/en/makeup/'),
                    ({'page':'portfolio','lang':'ru','view':'model'}, '/ru/portfolio/model/'),
                    ({'page':'course','lang':'ro','service':'3'}, '/ro/curs/3/'),
                    ({'page':'booking','lang':'en','service':'2'}, '/en/booking/2/'),
                    ({'page':'posts','lang':'en','destination':'professional'}, '/en/publications/professional/')]
        for query, expected in examples:
            self.assertEqual(public_path(query), expected)
            self.assertEqual(query_from_path(expected), query)
        private = {'page':'admin','lang':'ru','request':'42'}
        self.assertEqual(parse_qs(urlsplit(public_path(private)).query)['request'], ['42'])
        self.assertIsNone(query_from_path('/ru/portfolio/secret/'))
        self.assertIsNone(query_from_path('/ru/nonsense/'))
        markup = '<a href="?page=booking&amp;lang=ru">Book</a><script>const s=\'href="?page=admin"\';</script>'
        changed = rewrite_links(markup, ORIGIN)
        self.assertIn('href="/ru/zapis/"', changed)
        self.assertIn('const s=\'href="?page=admin"\'', changed)

    def test_empty_sections_are_excluded_without_changing_owner_flags(self):
        settings = {**get_settings(self.db), 'public_base_url':ORIGIN,'seo_pretty_urls':'1','seo_empty_sections_noindex':'1'}
        catalog = public_catalog(settings, db_path=self.db)
        self.assertFalse(any(row['page'] in ('posts','portfolio') for row in catalog))
        self.assertTrue(all(row['canonical'].startswith(ORIGIN + '/' + row['locale'] + '/') for row in catalog))
        for page, params in [('posts',{'destination':'scene'}),('portfolio',{'view':'model'})]:
            meta = build_metadata(settings, {'page':page,**params}, 'ru', db_path=self.db)
            self.assertEqual(meta['status'],200)
            self.assertFalse(meta['indexable'])
        self.assertEqual(settings['model_indexed'],'1')

    def test_analytics_excludes_private_preview_and_invalid_ids(self):
        settings={'seo_yandex_counter':'112712591'}
        meta={'indexable':True,'canonical':ORIGIN+'/ru/','page':'scene'}
        self.assertIn('webvisor:false', render_analytics(settings,meta))
        self.assertIn('defer:true', render_analytics(settings,meta))
        for kwargs in ({'private':True},{'submitted':True},{'preview':True}):
            self.assertEqual(render_analytics(settings,meta,**kwargs),'')
        self.assertEqual(render_analytics({'seo_yandex_counter':'1</script>'},meta),'')
        self.assertEqual(render_analytics(settings,{**meta,'indexable':False}),'')


if __name__ == '__main__':
    unittest.main()
