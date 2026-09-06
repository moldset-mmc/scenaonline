"""V1.7 release gate: portable business data and strict public/private separation."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
import zipfile

from PIL import Image
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scena_cabinet import list_support_messages, submit_support_message
from scena_core import get_settings, init_db, save_settings
from scena_licensing import owner_id, redeem_code, sign_code
from scena_model_builder import create_model_design, list_model_designs, save_model_draft_photo
from scena_prompts import list_projects, list_versions, restore_version, save_prompt
from scena_shop import (
    PRODUCT_FIELDS, SHOP_TABLES, create_order, get_product, list_orders,
    list_products, quote_cart, save_product,
)
from scena_transfer import build_backup, build_platform_export, inspect_backup, restore_backup


class ReleaseTransferV17Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'owner-app'
        self.app.mkdir()
        self.media = self.app / 'media'
        self.media.mkdir()
        self.db = self.app / 'scena_master.db'
        init_db(self.db)
        # Use the actual schema initializer; missing V1.7 tables must fail here.
        with sqlite3.connect(self.db) as con:
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.required = set(SHOP_TABLES) | {'prompt_projects', 'prompt_versions', 'pro_code_redemptions', 'support_reply_preferences'}
        self.assertTrue(self.required.issubset(tables), self.required - tables)
        save_settings(self.db, {'shop_enabled': '1', 'master_name_ru': 'Имя владельца', 'master_name_ro': 'Nume proprietar', 'master_name_en': 'Owner name'})
        self.original_photo = self.photo('#dcceaa')
        fields = {field: f'PUBLIC {field}' for field in PRODUCT_FIELDS}
        product = save_product(self.db, self.app, {**fields, 'price': '275.25', 'status': 'published'}, upload=self.original_photo)
        self.old_photo = product['image']
        self.published_photo = self.photo('#9a998b')
        product = save_product(self.db, self.app, {'description_en': 'PUBLIC personal recommendation context'}, product_id=product['id'], expected_revision=1, upload=self.published_photo)
        quote = quote_cart(self.db, {product['id']: 2})
        self.order = create_order(self.db, {product['id']: 2}, {
            'name': 'PRIVATE_BUYER_NAME', 'phone': '+37369123456', 'email': 'private-buyer@example.com',
            'telegram': '@privatebuyer', 'preferred_contact': 'email', 'note': 'PRIVATE_ORDER_NOTE', 'consent': True,
        }, reviewed_quote=quote['fingerprint'], request_key=str(uuid.uuid4()), locale='en')
        # Orders retain their reviewed historical price even if the live card changes.
        self.product = save_product(self.db, self.app, {'price': '310', 'name_ru': 'PUBLIC новое название'}, product_id=product['id'], expected_revision=product['revision'])
        self.draft = save_product(self.db, self.app, {**fields, 'name_ru': 'PRIVATE_DRAFT_PRODUCT', 'price': '500', 'status': 'draft'}, upload=self.photo('#274959'))
        first = save_prompt(self.db, template_id='club_main', title='PRIVATE_PROMPT_TITLE', body='PRIVATE_PROMPT_VERSION_ONE')
        save_prompt(self.db, template_id='club_main', title='PRIVATE_PROMPT_TITLE', body='PRIVATE_PROMPT_VERSION_TWO', project_id=first['project_id'])
        self.restored_prompt = restore_version(self.db, first['id'])
        self.support = submit_support_message(self.db, 'PRIVATE_SUPPORT_MESSAGE', reply_channel='telegram', contact='@privatesupport', locale='ro', request_key=uuid.uuid4().hex)
        # A real signed fixture code exercises retention of replay metadata.
        key = Ed25519PrivateKey.generate()
        (self.app / 'config').mkdir()
        (self.app / 'config/pro-issuer-public.pem').write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.code = sign_code(key, owner_id(self.db), 30)
        self.redemption = redeem_code(self.db, self.app, self.code)
        # The builder initializes lazily; its drafts and photos must also restore.
        self.design = create_model_design(self.db, 'PRIVATE_MODEL_DESIGN', 'custom')
        save_model_draft_photo(self.db, self.design, 'model_intro_image', self.photo('#806581'), self.app, 1)
        self.design_photo = json.loads(list_model_designs(self.db)[0]['snapshot_json'])['model_intro_image']

    @staticmethod
    def photo(color):
        output = io.BytesIO()
        Image.new('RGB', (640, 800), color).save(output, 'PNG')
        return output.getvalue()

    @staticmethod
    def rows(db, table):
        with sqlite3.connect(db) as con:
            con.row_factory = sqlite3.Row
            return [dict(row) for row in con.execute(f'SELECT * FROM {table} ORDER BY 1')]

    def test_private_backup_restore_and_reinit_preserve_new_business_records(self):
        before_tables = self.required | {'support_threads', 'support_messages', 'integration_outbox', 'pro_subscriptions', 'model_designs'}
        before = {table: self.rows(self.db, table) for table in before_tables}
        original_settings = get_settings(self.db)
        archive = build_backup(self.db, self.media)
        inspected = inspect_backup(archive)
        self.assertTrue(inspected['contains_private_data'])
        restored = restore_backup(archive, self.root / 'restored')
        restored_db = Path(restored['db_path'])
        init_db(restored_db)
        self.assertEqual({table: self.rows(restored_db, table) for table in before_tables}, before)
        self.assertEqual(get_settings(restored_db), original_settings)
        self.assertEqual(owner_id(restored_db), owner_id(self.db))
        self.assertEqual(list_products(restored_db), list_products(self.db))
        self.assertEqual(list_orders(restored_db), list_orders(self.db))
        self.assertEqual(list_orders(restored_db)[0]['total_cents'], 55050)
        self.assertEqual(list_orders(restored_db)[0]['items'][0]['unit_price_cents'], 27525)
        self.assertEqual(get_product(restored_db, self.product['id'])['price_cents'], 31000)
        self.assertEqual(list_projects(restored_db), list_projects(self.db))
        self.assertEqual(list_versions(restored_db), list_versions(self.db))
        self.assertEqual(list_support_messages(restored_db), list_support_messages(self.db))
        restored_version = next(item for item in list_versions(restored_db) if item['id'] == self.restored_prompt['id'])
        self.assertEqual(restored_version['state'], 'draft')
        self.assertTrue(restored_version['restored_from'])
        self.assertEqual(list_model_designs(restored_db), list_model_designs(self.db))
        for reference in (self.product['image'], self.old_photo, self.draft['image'], self.design_photo):
            self.assertEqual((restored_db.parent / reference).read_bytes(), (self.app / reference).read_bytes())
        again = inspect_backup(build_backup(restored_db, restored['media_dir']))
        self.assertEqual(again['identity'], inspected['identity'])

    def test_public_export_includes_three_language_shop_and_only_live_product_photo(self):
        export = build_platform_export(self.db, self.media)
        self.assertFalse(inspect_backup(export)['contains_private_data'])
        with zipfile.ZipFile(io.BytesIO(export)) as archive:
            content = json.loads(archive.read('public-content.json'))
            files = {item['path']: item for item in json.loads(archive.read('manifest.json'))['files']}
            self.assertEqual(len(content['shop']), 1)
            public_product = content['shop'][0]
            self.assertEqual(public_product['id'], self.product['id'])
            self.assertEqual(public_product['price_cents'], 31000)
            for field in PRODUCT_FIELDS:
                self.assertEqual(public_product[field], self.product[field])
            self.assertEqual(public_product['image'], self.product['image'])
            self.assertEqual(archive.read(self.product['image']), self.published_photo)
            self.assertEqual(files[self.product['image']]['sha256'], hashlib.sha256(self.published_photo).hexdigest())
            for reference in (self.old_photo, self.draft['image'], self.design_photo):
                self.assertNotIn(reference, archive.namelist())
                self.assertNotIn(reference, files)
            self.assertNotIn('scena_master.db', archive.namelist())
            self.assertNotIn('photo_history', public_product)
            # No private business tables, messages, contacts, prompt bodies or code.
            text = archive.read('public-content.json').decode()
            for private in ('PRIVATE_', 'photo_history', 'shop_orders', 'shop_order_items', 'prompt_projects', 'prompt_versions', 'pro_code_redemptions', 'support_messages', 'support_reply_preferences', 'model_designs', '+37369123456', 'private-buyer@example.com', '@privatesupport', self.code):
                self.assertNotIn(private, text)

    def test_hidden_market_suppresses_public_catalog_and_all_its_photos(self):
        save_settings(self.db, {'shop_enabled': '0'})
        with zipfile.ZipFile(io.BytesIO(build_platform_export(self.db, self.media))) as archive:
            content = json.loads(archive.read('public-content.json'))
            self.assertNotIn('shop', content)
            for reference in (self.product['image'], self.old_photo, self.draft['image']):
                self.assertNotIn(reference, archive.namelist())
        # Visibility does not delete paid work, private originals or customer orders.
        restored = restore_backup(build_backup(self.db, self.media), self.root / 'private-hidden-copy')
        init_db(restored['db_path'])
        self.assertEqual(get_settings(restored['db_path'])['shop_enabled'], '0')
        self.assertEqual(len(list_products(restored['db_path'])), 2)
        self.assertEqual(len(list_orders(restored['db_path'])), 1)


if __name__ == '__main__':
    unittest.main()
