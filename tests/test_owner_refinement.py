"""Owner operations must preserve drafts, bookings and recoverable content."""
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scena_core import init_db, schedule_periods
from scena_publications import (save_draft, publish_local, get_publication,
                                get_draft, list_publications, PublicationValidationError)


class OwnerRefinementTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'test.db'
        init_db(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def post(self):
        draft = save_draft(self.db, body_ru='Публичный текст', body_ro='Text public', translations_approved=True)
        return publish_local(self.db, draft['id'], draft['revision'])

    def test_visibility_saves_immediately_without_publishing_private_draft(self):
        from scena_publications import set_publication_visibility
        post = self.post()
        draft = save_draft(self.db, post['id'], body_ru='НЕ ПУБЛИКОВАТЬ')
        hidden = set_publication_visibility(self.db, post['id'], draft['revision'], [])
        self.assertIsNone(get_publication(self.db, post['public_id']))
        self.assertEqual(get_draft(self.db, post['id'])['body_ru'], 'НЕ ПУБЛИКОВАТЬ')
        set_publication_visibility(self.db, post['id'], hidden['revision'], ['model'])
        live = get_publication(self.db, post['public_id'])
        self.assertEqual(live['body_ru'], 'Публичный текст')
        self.assertTrue(live['show_model'])
        self.assertFalse(live['show_scene'])
        with self.assertRaises(PublicationValidationError):
            set_publication_visibility(self.db, post['id'], draft['revision'], ['scene'])

    def test_trash_is_recoverable_for_30_days_and_restore_stays_private(self):
        from scena_publications import trash_publication, restore_trashed_publication
        post = self.post()
        trash_publication(self.db, post['id'], post['revision'])
        with sqlite3.connect(self.db) as con:
            snapshot = json.loads(con.execute('SELECT published_json FROM publication_records WHERE post_id=?', (post['id'],)).fetchone()[0])
        self.assertFalse(any(snapshot[key] for key in ('show_scene', 'show_professional', 'show_model')))
        self.assertNotIn(post['id'], [p['id'] for p in list_publications(self.db)])
        public = get_publication(self.db, post['public_id'])
        self.assertEqual(public['status'], 'archived')
        self.assertNotIn('body_ru', public)
        self.assertNotIn('image_url', public)
        restored = restore_trashed_publication(self.db, post['id'])
        self.assertEqual(restored['body_ru'], 'Публичный текст')
        self.assertFalse(any(restored[key] for key in ('show_scene', 'show_professional', 'show_model')))
        self.assertIsNone(get_publication(self.db, post['public_id']))
        trash_publication(self.db, post['id'], restored['revision'])
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE publication_records SET updated_at=? WHERE post_id=?',
                        ((datetime.now(timezone.utc)-timedelta(days=31)).isoformat(), post['id']))
        with self.assertRaises(PublicationValidationError):
            restore_trashed_publication(self.db, post['id'])

    def test_bulk_schedule_is_atomic_and_does_not_change_other_days(self):
        from scena_core import save_dates_hours
        today = datetime.now().date() + timedelta(days=10)
        dates = [(today+timedelta(days=i)).isoformat() for i in range(3)]
        untouched = schedule_periods(self.db, dates[2])
        save_dates_hours(self.db, dates[:2], start_time='10:00', end_time='17:00', break_start='13:00', break_end='14:00')
        self.assertEqual([(a.isoformat(), b.isoformat()) for a,b in schedule_periods(self.db, dates[0])],
                         [('10:00:00', '13:00:00'), ('14:00:00', '17:00:00')])
        self.assertEqual(schedule_periods(self.db, dates[2]), untouched)
        before = schedule_periods(self.db, dates[0])
        with self.assertRaises(ValueError):
            save_dates_hours(self.db, [dates[0], 'invalid'], closed=True)
        self.assertEqual(schedule_periods(self.db, dates[0]), before)

    def test_signed_pro_renewal_preserves_remaining_days_and_is_once_only(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        from scena_licensing import owner_id, sign_code, redeem_code, LicenseError
        root = Path(self.temp.name)
        (root/'config').mkdir()
        key = Ed25519PrivateKey.generate()
        (root/'config/pro-issuer-public.pem').write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        with sqlite3.connect(self.db) as con:
            before = datetime.fromisoformat(con.execute("SELECT expires_at FROM pro_subscriptions WHERE owner_key='master'").fetchone()[0])
        code = sign_code(key, owner_id(self.db), 1)
        result = redeem_code(self.db, root, code)
        self.assertEqual(datetime.fromisoformat(result['expires_at']), before+timedelta(days=1))
        self.assertTrue(redeem_code(self.db, root, code)['already_used'])
        with self.assertRaises(LicenseError):
            redeem_code(self.db, root, code[:-2]+'xx')

    def test_pro_contact_dispatches_only_the_selected_message(self):
        from scena_cabinet import submit_support_message, dispatch_support_notifications
        old = submit_support_message(self.db, 'Не отправлять старое обращение', request_key='oldrequest12345678')
        new = submit_support_message(self.db, 'Продление PRO', request_key='newrequest12345678')
        class FakeTelegram:
            configured = True
            def __init__(self): self.bodies = []
            def send_support_message(self, **values):
                self.bodies.append(values['body'])
                return 'test-message-id'
        adapter = FakeTelegram()
        result = dispatch_support_notifications(self.db, adapter, message_id=new['id'])
        self.assertEqual(result['sent'], 1)
        self.assertEqual(len(adapter.bodies), 1)
        self.assertNotIn('старое', adapter.bodies[0])
        self.assertEqual(dispatch_support_notifications(self.db, adapter, message_id=new['id'])['sent'], 0)


if __name__ == '__main__':
    unittest.main()
