import base64
import concurrent.futures
import json
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from scena_core import init_db
from scena_licensing import LicenseError, initialize_licensing, owner_id, redeem_code, sign_code
from scena_pro_operator import create_issuer_keys, install_public_key
from scena_prompts import PromptError, initialize_prompts, list_projects, list_versions, restore_version, save_prompt, scenario_catalog, template_catalog, template_text


class PROFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.app = self.directory / 'app'
        self.app.mkdir()
        self.db = self.app / 'scena_master.db'
        self.now = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
        init_db(self.db, now=self.now)
        with sqlite3.connect(self.db) as connection:
            initialize_prompts(connection)
            initialize_licensing(connection)
        self.key = Ed25519PrivateKey.generate()
        source = self.directory / 'public.pem'
        source.write_bytes(self.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        install_public_key(source, self.app)

    def code(self, **kwargs):
        return sign_code(self.key, kwargs.pop('profile_id', owner_id(self.db)), kwargs.pop('days', 30), now=self.now, **kwargs)

    def status(self):
        with sqlite3.connect(self.db) as connection:
            return connection.execute("SELECT expires_at,tier,status FROM pro_subscriptions WHERE owner_key='master'").fetchone()

    def expire(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE pro_subscriptions SET tier='FREE',status='expired',expires_at=?", ((self.now - timedelta(days=1)).isoformat(),))


class CodeTests(PROFixtures):
    def test_valid_code_preserves_days_and_replay_is_idempotent(self):
        before = datetime.fromisoformat(self.status()[0])
        code = self.code()
        receipt = redeem_code(self.db, self.app, code, now=self.now)
        self.assertFalse(receipt['already_used'])
        self.assertEqual(datetime.fromisoformat(receipt['expires_at']), before + timedelta(days=30))
        replay = redeem_code(self.db, self.app, code, now=self.now + timedelta(days=20))
        self.assertTrue(replay['already_used'])
        self.assertEqual(receipt['expires_at'], self.status()[0])

    def test_expired_subscription_extends_from_today(self):
        self.expire()
        receipt = redeem_code(self.db, self.app, self.code(days=90), now=self.now)
        self.assertEqual(datetime.fromisoformat(receipt['expires_at']), self.now + timedelta(days=90))
        self.assertEqual(self.status()[1:], ('PRO', 'active'))

    def test_forged_body_and_wrong_signer_never_mutate(self):
        before = self.status()
        token = self.code()
        prefix, body, sig = token.split('.')
        payload = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
        payload['days'] = 730
        forged = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        with self.assertRaises(LicenseError):
            redeem_code(self.db, self.app, f'{prefix}.{forged}.{sig}', now=self.now)
        wrong = sign_code(Ed25519PrivateKey.generate(), owner_id(self.db), 30, now=self.now)
        with self.assertRaises(LicenseError):
            redeem_code(self.db, self.app, wrong, now=self.now)
        self.assertEqual(before, self.status())

    def test_wrong_owner_and_expired_code_rejected(self):
        before = self.status()
        with self.assertRaisesRegex(LicenseError, 'другого профиля'):
            redeem_code(self.db, self.app, self.code(profile_id=str(uuid.uuid4())), now=self.now)
        with self.assertRaisesRegex(LicenseError, 'истёк'):
            redeem_code(self.db, self.app, self.code(valid_days=1), now=self.now + timedelta(days=2))
        self.assertEqual(before, self.status())

    def test_parallel_redemption_extends_exactly_once(self):
        before = datetime.fromisoformat(self.status()[0])
        code = self.code()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: redeem_code(self.db, self.app, code, now=self.now), range(4)))
        self.assertEqual(sum(not r['already_used'] for r in results), 1)
        self.assertEqual(datetime.fromisoformat(self.status()[0]), before + timedelta(days=30))
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM pro_code_redemptions').fetchone()[0], 1)

    def test_key_generation_stays_outside_client_and_is_encrypted(self):
        with self.assertRaises(ValueError):
            create_issuer_keys(self.app / 'keys', 'long-enough-password', app_dir=self.app)
        private, public = create_issuer_keys(self.directory / 'operator', 'long-enough-password', app_dir=self.app)
        self.assertIn(b'ENCRYPTED PRIVATE KEY', private.read_bytes())
        with self.assertRaises(ValueError):
            create_issuer_keys(private.parent, 'long-enough-password', app_dir=self.app)
        self.assertTrue(public.exists())
        self.assertFalse(any(b'PRIVATE KEY' in p.read_bytes() for p in (self.app / 'config').glob('*')))

    def test_malformed_tokens_and_missing_issuer(self):
        for token in ('', 'SCENA1', 'SCENA1.bad.bad', 'SCENA1.' + 'a' * 4000, 'SCENA1.а.б'):
            with self.assertRaises(LicenseError):
                redeem_code(self.db, self.app, token, now=self.now)
        (self.app / 'config' / 'pro-issuer-public.pem').unlink()
        with self.assertRaises(LicenseError):
            redeem_code(self.db, self.app, self.code(), now=self.now)


class PromptTests(PROFixtures):
    def test_restoring_basic_after_renewal_preserves_original(self):
        self.expire()
        basic = save_prompt(self.db, template_id='scene', title='Base', body='Original base', now=self.now)
        redeem_code(self.db, self.app, self.code(), now=self.now)
        restored = restore_version(self.db, basic['id'], now=self.now)
        self.assertNotEqual(restored['id'], basic['id'])
        self.assertNotEqual(restored['project_id'], basic['project_id'])
        self.assertEqual(restored['restored_from'], basic['id'])
        self.assertEqual(restored['state'], 'draft')
        self.assertEqual(list_versions(self.db, 'basic-gloss'), [basic])

    def test_free_catalog_visible_pro_text_gated(self):
        self.expire()
        for locale in ('ru', 'ro', 'en'):
            catalog = scenario_catalog(locale)
            self.assertEqual(len(catalog), 5)
            self.assertTrue(all(c['name'] and c['description'] for c in catalog))
        self.assertIn('same adult person', template_text(self.db, 'model_intro', now=self.now))
        with self.assertRaises(PromptError):
            template_text(self.db, 'club_main', now=self.now)

    def test_free_one_project_one_editable_version_persists(self):
        self.expire()
        first = save_prompt(self.db, template_id='model_intro', title='Мой первый', body='Original brief', now=self.now)
        second = save_prompt(self.db, template_id='gloss_1', title='Уточнённый', body='Refined brief', now=self.now)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(list_projects(self.db)), 1)
        self.assertEqual(len(list_versions(self.db)), 1)
        init_db(self.db, now=self.now)
        self.assertEqual(list_versions(self.db)[0]['body'], 'Refined brief')
        with self.assertRaises(PromptError):
            save_prompt(self.db, template_id='club_main', title='Closed', body='Text', now=self.now)

    def test_pro_history_after_expiry_readonly_and_free_remains_available(self):
        first = save_prompt(self.db, template_id='club_main', title='Night', body='My own scene', now=self.now)
        second = save_prompt(self.db, template_id='club_main', title='Night 2', body='My edited scene', project_id=first['project_id'], now=self.now)
        restored = restore_version(self.db, first['id'], now=self.now)
        self.assertEqual(restored['state'], 'draft')
        self.assertEqual(restored['restored_from'], first['id'])
        self.assertEqual(restored['body'], first['body'])
        self.expire()
        history = list_versions(self.db)
        with self.assertRaises(PromptError):
            restore_version(self.db, second['id'], now=self.now)
        with self.assertRaises(PromptError):
            save_prompt(self.db, template_id='club_main', title='New', body='Text', project_id=first['project_id'], now=self.now)
        free = save_prompt(self.db, template_id='scene', title='Basic', body='Basic free brief', now=self.now)
        self.assertEqual(free['project_id'], 'basic-gloss')
        self.assertEqual([v for v in list_versions(self.db) if v['project_id'] != 'basic-gloss'], history)

    def test_concurrent_pro_versions_numbered_without_loss(self):
        first = save_prompt(self.db, template_id='club_main', title='Start', body='Start', now=self.now)
        def save(number):
            return save_prompt(self.db, template_id='club_main', title=f'v{number}', body=f'body{number}', project_id=first['project_id'], now=self.now)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(save, range(4)))
        self.assertEqual({r['version'] for r in results}, {2, 3, 4, 5})
        self.assertEqual(len(list_versions(self.db, first['project_id'])), 5)

    def test_qr_briefs_are_distinct_and_require_real_verified_codes(self):
        entries = [item for item in template_catalog() if item['id'].startswith('qr_')]
        self.assertEqual(len(entries), 4)
        texts = [template_text(self.db, entry['id'], now=self.now, target_url='https://example.test/?page=' + entry['id']) for entry in entries]
        self.assertEqual(len(set(texts)), 4)
        self.assertTrue(all('Decode the FINAL composite' in body and 'four-module quiet border' in body for body in texts))

    def test_invalid_text_does_not_create_project(self):
        with self.assertRaises(PromptError):
            save_prompt(self.db, template_id='scene', title='', body='body', now=self.now)
        self.assertEqual(list_projects(self.db), [])


if __name__ == '__main__':
    unittest.main()
