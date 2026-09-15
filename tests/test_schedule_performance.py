import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import scena_core as core


class SchedulePerformanceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = Path(self.folder.name) / 'schedule.db'
        core.init_db(self.db)
        self.now = datetime(2026, 9, 15, 8, tzinfo=core.CHISINAU)
        self.service = core.list_services(self.db, 'Professional', kind='appointment')[0]['id']

    def slots(self, day):
        return core.generate_available_slots(self.db, self.service, day, now=self.now)

    def test_individual_weekday_and_date_override_preserve_other_days(self):
        regular_wednesday = self.slots('2026-09-16')
        regular_thursday = self.slots('2026-09-17')
        core.save_weekday_hours(self.db, 2, start_time='10:00', end_time='12:00')
        short = self.slots('2026-09-16')
        self.assertTrue(short)
        self.assertTrue(all('10:00' <= t < '12:00' for t in short))
        self.assertNotEqual(short, regular_wednesday)
        self.assertEqual(short, self.slots('2026-09-23'))
        self.assertEqual(regular_thursday, self.slots('2026-09-17'))
        core.save_date_hours(self.db, '2026-09-16', start_time='15:00', end_time='17:00')
        self.assertTrue(all('15:00' <= t < '17:00' for t in self.slots('2026-09-16')))
        self.assertEqual(short, self.slots('2026-09-23'))
        core.save_date_hours(self.db, '2026-09-16', closed=True)
        self.assertEqual([], self.slots('2026-09-16'))
        core.save_date_hours(self.db, '2026-09-16', reset=True)
        self.assertEqual(short, self.slots('2026-09-16'))
        core.save_weekday_hours(self.db, 2, reset=True)
        self.assertEqual(regular_wednesday, self.slots('2026-09-16'))

    def test_invalid_replacement_preserves_saved_day_and_no_double_booking(self):
        core.save_date_hours(self.db, '2026-09-16', start_time='09:00', end_time='12:00')
        before = self.slots('2026-09-16')
        with self.assertRaises(core.RequestValidationError):
            core.save_date_hours(self.db, '2026-09-16', start_time='12:00', end_time='09:00')
        self.assertEqual(before, self.slots('2026-09-16'))
        payload = dict(service_id=self.service, slot_date='2026-09-16', slot_time=before[0], name='Fixture', phone='+37360000111', consent=True, now=self.now)
        core.create_service_request(self.db, **payload)
        with self.assertRaises(core.RequestValidationError):
            core.create_service_request(self.db, **payload)
        self.assertNotIn(before[0], self.slots('2026-09-16'))

    def test_month_is_one_connection_five_reads_and_matches_individual_days(self):
        core.add_schedule_exception(self.db, '2026-09-21', 'closed')
        core.add_schedule_exception(self.db, '2026-09-19', 'extra', start_time='10:00', end_time='12:00')
        core.save_weekday_hours(self.db, 2, start_time='09:00', end_time='16:00', break_start='12:00', break_end='13:00')
        days = [(self.now.date() + timedelta(days=i)).isoformat() for i in range(16)]
        expected = {day:self.slots(day) for day in days}
        native_connect = sqlite3.connect
        counts = {'connections':0, 'reads':0}
        def counted(*args, **kwargs):
            counts['connections'] += 1
            db = native_connect(*args, **kwargs)
            def trace(sql):
                if sql.lstrip().upper().startswith('SELECT'):counts['reads'] += 1
            db.set_trace_callback(trace)
            return db
        with patch('scena_database.sqlite3.connect', counted):
            result = core.generate_availability_range(self.db, self.service, days[0], days[-1], now=self.now)
        self.assertEqual(result, expected)
        self.assertEqual(counts, {'connections':1, 'reads':5})

    def test_saved_public_pages_are_invalidated_transactionally(self):
        from scena_web import page_cache
        with patch.dict('os.environ', SCENA_DB_PATH=str(self.db)):
            with sqlite3.connect(self.db) as db:page_cache.initialize(db)
            version, saved = page_cache.lookup('fixture')
            self.assertIsNone(saved)
            page_cache.save('fixture', version, '<html>old</html>', '/')
            self.assertIsNotNone(page_cache.lookup('fixture')[1])
            core.save_settings(self.db, {'master_name_ru':'Updated owner'})
            self.assertIsNone(page_cache.lookup('fixture')[1])
            page_cache.save('fixture', version, '<html>stale render</html>', '/')
            self.assertIsNone(page_cache.lookup('fixture')[1], 'An in-flight old render reentered the cache')

class LazyMediaTests(unittest.TestCase):
    def test_editor_fetches_only_selected_original_and_lists_without_bytes(self):
        import hashlib
        import os
        from types import SimpleNamespace
        from scena_media import hydrate, saved_files
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            database=root/'media.db'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE scena_media_files(path TEXT PRIMARY KEY, private_url TEXT, sha256 TEXT, bytes INTEGER, public_url TEXT)')
                for name in ('selected', 'unrelated'):
                    content=name.encode()
                    db.execute('INSERT INTO scena_media_files VALUES (?,?,?,?,?)',('media/portfolio/'+name+'.webp','https://fixture/'+name,hashlib.sha256(content).hexdigest(),len(content),''))
            with patch.dict(os.environ,SCENA_DB_PATH=str(database),SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN='fixture-only'), patch('scena_media.cloud_database',return_value=True), patch('vercel.blob.get',return_value=SimpleNamespace(status_code=200,content=b'selected')) as download:
                self.assertEqual(len(saved_files(root,'media/portfolio')),2)
                download.assert_not_called()
                hydrate(root,paths=['media/portfolio/selected.webp'])
                self.assertEqual(download.call_count,1)
                self.assertEqual((root/'media/portfolio/selected.webp').read_bytes(),b'selected')
                self.assertFalse((root/'media/portfolio/unrelated.webp').exists())


if __name__ == '__main__':
    unittest.main()
