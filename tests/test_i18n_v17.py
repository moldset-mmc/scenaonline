"""Persistence and migration checks for independently editable RU/RO/EN content."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import datetime

from scena_i18n import (
    CATALOG, DEFAULT_I18N_SETTINGS, content_text, localized_name,
    normalize_locale, service_name, tr, translate_literaltext,
)
from scena_core import (
    CHISINAU, _sms_body, add_service, add_service_group, create_request,
    get_settings, init_db, list_service_groups, list_services, save_settings,
    update_service, update_service_group,
)


class I18nHelpersTest(unittest.TestCase):
    def test_language_normalization_and_explicit_english(self):
        self.assertEqual(normalize_locale('EN-us'), 'en')
        self.assertEqual(normalize_locale('RO_md'), 'ro')
        self.assertEqual(normalize_locale('xx'), 'ru')
        self.assertEqual(tr('en', 'Моя Сцена', 'Scena mea'), 'My Scene')
        self.assertEqual(tr('en', 'Новое', 'Nou', 'New'), 'New')
        self.assertEqual(translate_literaltext('ro', 'Работа'), 'Activitate')
        self.assertEqual(translate_literaltext('en', 42), 42)

    def test_owner_names_do_not_get_auto_replaced(self):
        custom = {'master_name': 'Sofia Dumitru', **DEFAULT_I18N_SETTINGS}
        self.assertEqual(localized_name(custom, 'ru'), 'Sofia Dumitru')
        self.assertEqual(localized_name(custom, 'en'), 'Sofia Dumitru')
        custom.update(master_name_ru='София Думитру', master_name_en='Sofia D.')
        self.assertEqual(localized_name(custom, 'ru'), 'София Думитру')
        self.assertEqual(localized_name(custom, 'en'), 'Sofia D.')
        maria = {'master_name': 'Мария Бараночникова'}
        self.assertEqual(localized_name(maria, 'ru'), 'Мария Бараночникова')
        self.assertEqual(localized_name(maria, 'ro'), 'Maria Baranochnikova')
        self.assertEqual(localized_name(maria, 'en'), 'Maria Baranochnikova')

    def test_user_text_has_independent_translations_and_safe_fallback(self):
        fields = {'bio': 'Моя собственная история с Софией.', 'bio_ro': 'Povestea mea.', 'bio_en': 'My own story.'}
        self.assertEqual(content_text(fields, 'bio', 'en'), 'My own story.')
        self.assertEqual(content_text(fields, 'bio', 'ru'), fields['bio'])
        del fields['bio_en']
        self.assertEqual(content_text(fields, 'bio', 'en'), fields['bio'])
        self.assertEqual(service_name({'name': 'Персональная консультация'}, 'en'), 'Personal consultation')
        self.assertEqual(content_text({'model_slide_1_alt_ru': 'мой собственный кадр'}, 'model_slide_1_alt', 'en'), 'мой собственный кадр')
        self.assertEqual(translate_literaltext('en', '<script>моя история</script>'), '<script>моя история</script>')

    def test_core_user_journey_labels_have_english_and_romanian(self):
        for label in ('Главная', 'Работа', 'Что показывать', 'Сохранить Мою Сцену', 'Название услуги', 'Пригласить как модель', '2. Выберите день и время', 'Телефон +373 *', 'Подписка PRO', 'Публичное имя EN'):
            for language in ('ro', 'en'):
                with self.subTest(label=label, language=language):
                    self.assertNotEqual(translate_literaltext(language, label), label)
        self.assertGreater(len(CATALOG), 550)


class I18nPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'scena.db'
        init_db(self.db, now=datetime(2026, 9, 6, tzinfo=CHISINAU))

    def tearDown(self):
        self.temp.cleanup()

    def test_settings_persist_and_migration_preserves_custom_owner(self):
        save_settings(self.db, {'master_name': 'Sofia Dumitru', 'master_name_en': 'Sofia D.', 'bio_en': 'My story', 'booking_cta_en': 'Book a session'})
        init_db(self.db)
        settings = get_settings(self.db)
        self.assertEqual(localized_name(settings, 'en'), 'Sofia D.')
        self.assertEqual(localized_name(settings, 'ro'), 'Sofia Dumitru')
        self.assertEqual(settings['bio_en'], 'My story')
        self.assertEqual(settings['booking_cta_en'], 'Book a session')

    def test_service_and_group_english_persist_without_breaking_legacy_updates(self):
        group = add_service_group(self.db, category='Professional', name_ru='Брови', name_ro='Sprâncene', name_en='Brows', description_en='Brow services')
        service = add_service(self.db, 'Professional', 'Уход за бровями', 400, 30, name_ro='Îngrijirea sprâncenelor', description_ru='Уход', description_ro='Îngrijire', translations_approved=True, group_id=group, name_en='Brow care', description_en='A custom brow treatment')
        update_service(self.db, service, category='Professional', name='Уход за бровями', price=450, duration=30)
        update_service_group(self.db, group, name_ru='Брови', name_ro='Sprâncene')
        item = next(row for row in list_services(self.db) if row['id'] == service)
        self.assertEqual(item['name_en'], 'Brow care')
        self.assertEqual(item['description_en'], 'A custom brow treatment')
        self.assertEqual(item['group_name_en'], 'Brows')
        update_service(self.db, service, category='Professional', name='Уход за бровями', price=450, duration=30, name_en='Personal brow care')
        update_service_group(self.db, group, name_ru='Брови', name_ro='Sprâncene', name_en='Brow studio')
        item = next(row for row in list_services(self.db) if row['id'] == service)
        self.assertEqual(item['name_en'], 'Personal brow care')
        self.assertEqual(item['group_name_en'], 'Brow studio')

    def test_english_request_and_sms_are_stored_as_english(self):
        request_id = create_request(self.db, request_type='model_application', name='Sofia', phone='+37360123456', consent=True, locale='en', city='Chișinău', experience='No experience')
        with sqlite3.connect(self.db) as con:
            request = con.execute('SELECT locale FROM requests WHERE id=?', (request_id,)).fetchone()
            sms = con.execute('SELECT locale, body FROM sms_outbox WHERE request_id=?', (request_id,)).fetchone()
        self.assertEqual(request[0], 'en')
        self.assertEqual(sms[0], 'en')
        self.assertIn('received', sms[1])
        self.assertNotRegex(sms[1], '[А-Яа-я]')

    def test_old_locale_checks_migrate_without_losing_data_indexes_or_replies(self):
        # Turn empty current tables into the exact old RU/RO CHECK schema.
        with sqlite3.connect(self.db) as con:
            for table in ('sms_outbox', 'requests'):
                ddl = con.execute('SELECT sql FROM sqlite_master WHERE name=?', (table,)).fetchone()[0]
                indexes = con.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL", (table,)).fetchall()
                con.execute(f'DROP TABLE {table}')
                con.execute(ddl.replace("'ru', 'ro', 'en'", "'ru', 'ro'"))
                for item in indexes:
                    con.execute(item[0])
            con.execute("INSERT INTO requests(id,request_type,name,phone,consent,created_at,locale) VALUES(41,'model_application','Existing Client','+37360123456',1,'2026-09-06','ru')")
            con.execute("INSERT INTO sms_outbox(id,request_id,event,recipient,locale,body,created_at) VALUES(19,41,'general_request_received','+37360123456','ru','Original message','2026-09-06')")
            con.execute('CREATE TABLE reply_audit (request_id INTEGER REFERENCES requests(id), body TEXT)')
            con.execute("INSERT INTO reply_audit VALUES(41,'Existing reply')")
            con.execute('CREATE INDEX custom_request_name ON requests(name)')
            con.execute('CREATE TRIGGER audit_new_request AFTER INSERT ON requests BEGIN INSERT INTO reply_audit VALUES(new.id, new.name); END')
            con.execute("UPDATE sqlite_sequence SET seq=900 WHERE name='requests'")
        init_db(self.db)
        init_db(self.db)  # Must be idempotent.
        with sqlite3.connect(self.db) as con:
            con.execute('PRAGMA foreign_keys=ON')
            self.assertEqual(con.execute('SELECT name,locale FROM requests WHERE id=41').fetchone(), ('Existing Client', 'ru'))
            self.assertEqual(con.execute('SELECT body FROM sms_outbox WHERE id=19').fetchone()[0], 'Original message')
            self.assertEqual(con.execute('SELECT body FROM reply_audit WHERE request_id=41').fetchone()[0], 'Existing reply')
            self.assertIsNotNone(con.execute("SELECT name FROM sqlite_master WHERE name='custom_request_name'").fetchone())
            cursor = con.execute("INSERT INTO requests(request_type,name,phone,consent,created_at,locale) VALUES('model_application','New English Client','+37360123456',1,'2026-09-06','en')")
            self.assertGreater(cursor.lastrowid, 900)
            self.assertEqual(con.execute('SELECT body FROM reply_audit WHERE request_id=?', (cursor.lastrowid,)).fetchone()[0], 'New English Client')
            con.execute("INSERT INTO sms_outbox(request_id,event,recipient,locale,body,created_at) VALUES(?,'general_request_received','+37360123456','en','Received','2026-09-06')", (cursor.lastrowid,))
            self.assertEqual(con.execute('PRAGMA foreign_key_check').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
