"""Real shop persistence and ordering boundaries, independent of network services."""
from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from PIL import Image

from scena_core import get_settings, init_db
from scena_shop import (
    PRODUCT_FIELDS, SHOP_DEFAULT_SETTINGS, ShopError, archive_product, create_order,
    get_product, init_shop, list_orders, list_products, price_to_cents,
    public_shop_data, quote_cart, save_product, update_order_status,
)


class ShopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'fixture.db'
        init_db(self.db)
        init_shop(self.db)
        with sqlite3.connect(self.db) as con:
            con.executemany('INSERT OR IGNORE INTO profile_settings(key,value) VALUES(?,?)', SHOP_DEFAULT_SETTINGS.items())
        self.photo = self.make_photo()
        self.product = save_product(self.db, self.root, self.fields(), upload=self.photo)
        self.contact = {'name': 'Анна Тест', 'phone': '+373 69123456', 'email': 'anna@example.com', 'telegram': '@annatest', 'preferred_contact': 'telegram', 'note': 'После 18:00', 'consent': True}

    @staticmethod
    def make_photo(color='ivory'):
        image = io.BytesIO()
        Image.new('RGB', (600, 700), color).save(image, 'PNG')
        return image.getvalue()

    @staticmethod
    def fields(**changes):
        result = {field: f'Test {field}' for field in PRODUCT_FIELDS}
        result.update(price='259,75', status='published')
        result.update(changes)
        return result

    def buy(self, *, cart=None, contacts=None, quote=None, key=None):
        cart = cart or {self.product['id']: 2}
        return create_order(self.db, cart, contacts or self.contact,
                            reviewed_quote=quote or quote_cart(self.db, cart)['fingerprint'],
                            request_key=key or str(uuid.uuid4()))

    def expire(self):
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE pro_subscriptions SET expires_at='2000-01-01T00:00:00+00:00'")

    def test_additive_init_preserves_catalog_and_owner_data(self):
        init_shop(self.db)
        with sqlite3.connect(self.db) as con:
            init_shop(con)
        self.assertEqual(get_product(self.db, self.product['id']), self.product)
        self.assertTrue(get_settings(self.db)['master_name'])

    def test_price_precision_rejects_nonfinite_rounding_and_negative(self):
        self.assertEqual(price_to_cents('259,75'), 25975)
        self.assertEqual(price_to_cents('0.01'), 1)
        for value in ['0', '-1', '12.009', 'NaN', 'Infinity', '1000000.01', '1e100', True]:
            with self.subTest(value=value), self.assertRaises(ShopError):
                price_to_cents(value)

    def test_originals_survive_replacement_and_stale_edit_cannot_leave_photo(self):
        old = self.product['image']
        updated = save_product(self.db, self.root, {'name_en': 'Updated name'}, product_id=self.product['id'], expected_revision=1, upload=self.make_photo('tan'))
        self.assertNotEqual(old, updated['image'])
        self.assertEqual((self.root / old).read_bytes(), self.photo)
        with self.assertRaisesRegex(ShopError, 'stale'):
            save_product(self.db, self.root, {'name_en': 'Stale name'}, product_id=self.product['id'], expected_revision=1, upload=self.make_photo('navy'))
        self.assertEqual(len(list((self.root / 'media/shop').iterdir())), 2)
        restored = save_product(self.db, self.root, {'image': old}, product_id=self.product['id'], expected_revision=updated['revision'])
        self.assertEqual(restored['image'], old)

    def test_bad_image_and_path_rejected_without_catalog_changes(self):
        for upload in [b'not-a-photo', b'123' * (7 * 1024 * 1024)]:
            with self.assertRaises(ShopError):
                save_product(self.db, self.root, self.fields(), upload=upload)
        for image in ['../../secrets.png', 'https://example.com/photo.jpg', '/etc/passwd']:
            with self.assertRaises(ShopError):
                save_product(self.db, self.root, {'image': image}, product_id=self.product['id'], expected_revision=1)
        self.assertEqual(len(list_products(self.db)), 1)
        self.assertEqual(get_product(self.db, self.product['id']), self.product)

    def test_publication_requires_photo_and_all_three_languages(self):
        with self.assertRaisesRegex(ShopError, 'photo_missing'):
            save_product(self.db, self.root, self.fields())
        with self.assertRaisesRegex(ShopError, 'translations'):
            save_product(self.db, self.root, self.fields(name_en=''), upload=self.photo)
        draft = save_product(self.db, self.root, {'name_ru': 'Черновик', 'price': '50', 'status': 'draft'})
        self.assertIsNone(get_product(self.db, draft['id'], public=True))

    def test_server_does_not_accept_client_price_fields(self):
        with self.assertRaisesRegex(ShopError, 'fields'):
            save_product(self.db, self.root, {'price_cents': 1}, product_id=self.product['id'], expected_revision=1)
        quote = quote_cart(self.db, {self.product['id']: 2})
        order = self.buy(quote=quote['fingerprint'])
        self.assertEqual(order['total_cents'], 51950)
        self.assertEqual(order['items'][0]['unit_price_cents'], 25975)
        self.assertNotIn('paid', order)

    def test_revised_price_requires_fresh_explicit_review(self):
        quote = quote_cart(self.db, {self.product['id']: 2})
        save_product(self.db, self.root, {'price': '300'}, product_id=self.product['id'], expected_revision=1)
        with self.assertRaisesRegex(ShopError, 'changed'):
            self.buy(quote=quote['fingerprint'])
        self.assertEqual(list_orders(self.db), [])
        self.assertEqual(self.buy()['total_cents'], 60000)

    def test_order_snapshot_survives_price_text_and_status_changes(self):
        order = self.buy()
        changed = save_product(self.db, self.root, {'price': '999', 'name_ru': 'Новое имя'}, product_id=self.product['id'], expected_revision=1)
        archive_product(self.db, self.product['id'], expected_revision=changed['revision'], confirmed=True)
        reloaded = list_orders(self.db)[0]
        self.assertEqual(reloaded['total_cents'], 51950)
        self.assertEqual(reloaded['items'][0]['name_ru'], self.product['name_ru'])
        self.assertEqual(reloaded['id'], order['id'])

    def test_duplicate_order_is_idempotent_even_when_price_changes_after_first_order(self):
        key = str(uuid.uuid4())
        quote = quote_cart(self.db, {self.product['id']: 2})
        first = self.buy(key=key, quote=quote['fingerprint'])
        save_product(self.db, self.root, {'price': '500'}, product_id=self.product['id'], expected_revision=1)
        second = self.buy(key=key, quote=quote['fingerprint'])
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(list_orders(self.db)), 1)
        with self.assertRaisesRegex(ShopError, 'duplicate_conflict'):
            self.buy(key=key, cart={self.product['id']: 3})

    def test_simultaneous_double_submit_has_one_order(self):
        key = str(uuid.uuid4())
        quote = quote_cart(self.db, {self.product['id']: 2})
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(lambda _: self.buy(key=key, quote=quote['fingerprint']), range(2)))
        self.assertEqual(result[0]['id'], result[1]['id'])
        self.assertEqual(len(list_orders(self.db)), 1)

    def test_hidden_or_archived_product_cannot_be_ordered(self):
        quote = quote_cart(self.db, {self.product['id']: 2})
        with self.assertRaisesRegex(ShopError, 'confirmation'):
            archive_product(self.db, self.product['id'], expected_revision=1)
        archive_product(self.db, self.product['id'], expected_revision=1, confirmed=True)
        with self.assertRaisesRegex(ShopError, 'unavailable'):
            self.buy(quote=quote['fingerprint'])
        self.assertEqual(list_products(self.db, public=True), [])

    def test_expired_pro_preserves_published_catalog_ordering_and_fulfillment(self):
        self.expire()
        self.assertEqual(len(list_products(self.db, public=True)), 1)
        with self.assertRaisesRegex(ShopError, 'pro'):
            save_product(self.db, self.root, self.fields(), upload=self.photo)
        order = self.buy()
        update_order_status(self.db, order['id'], 'fulfilled', expected_revision=1)
        self.assertEqual(list_orders(self.db)[0]['status'], 'fulfilled')
        updated = save_product(self.db, self.root, {'recommendation_en': 'My updated recommendation'}, product_id=self.product['id'], expected_revision=1)
        self.assertEqual(updated['status'], 'published')
        hidden = save_product(self.db, self.root, {'status': 'hidden'}, product_id=self.product['id'], expected_revision=2)
        with self.assertRaisesRegex(ShopError, 'pro'):
            save_product(self.db, self.root, {'status': 'published'}, product_id=hidden['id'], expected_revision=hidden['revision'])

    def test_contacts_consent_and_preferred_channel_required(self):
        for changes in [{'consent': False}, {'name': ''}, {'phone': 'hello'}, {'email': 'bad'}, {'telegram': 'bad'}, {'preferred_contact': 'email', 'email': ''}, {'preferred_contact': 'sms'}]:
            with self.subTest(changes=changes), self.assertRaises(ShopError):
                self.buy(contacts={**self.contact, **changes})
        self.assertEqual(list_orders(self.db), [])

    def test_cart_and_store_visibility_checked_server_side(self):
        for cart in [{}, {self.product['id']: 0}, {self.product['id']: 1.5}, {self.product['id']: True}, {self.product['id']: 100}, {'missing': 1}]:
            with self.subTest(cart=cart), self.assertRaises(ShopError):
                quote_cart(self.db, cart)
        quote = quote_cart(self.db, {self.product['id']: 2})
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE profile_settings SET value='0' WHERE key='shop_enabled'")
        with self.assertRaisesRegex(ShopError, 'closed'):
            self.buy(quote=quote['fingerprint'])

    def test_order_status_updates_reject_stale_owner_tabs(self):
        order = self.buy()
        update_order_status(self.db, order['id'], 'contacted', expected_revision=1)
        with self.assertRaisesRegex(ShopError, 'stale'):
            update_order_status(self.db, order['id'], 'cancelled', expected_revision=1)
        self.assertEqual(list_orders(self.db)[0]['status'], 'contacted')

    def test_public_interchange_has_only_published_products_not_buyer_or_draft(self):
        self.buy()
        save_product(self.db, self.root, self.fields(status='draft', name_ru='SECRET DRAFT'), upload=self.photo)
        with sqlite3.connect(self.db) as con:
            data = public_shop_data(con)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['image'], self.product['image'])
        self.assertNotIn('SECRET DRAFT', str(data))
        self.assertNotIn(self.contact['phone'], str(data))
        self.assertNotIn(self.contact['note'], str(data))

    def test_admin_changes_are_durable_and_all_locales_render(self):
        from streamlit.testing.v1 import AppTest
        for locale in ('ru', 'ro', 'en'):
            source = f'''from scena_shop import render_shop_admin
from scena_core import get_settings
render_shop_admin({str(self.db)!r}, {str(self.root)!r}, get_settings({str(self.db)!r}), {locale!r})'''
            app = AppTest.from_string(source).run()
            self.assertEqual(len(app.exception), 0, app.exception)
        source = f'''from scena_shop import render_shop_admin
from scena_core import get_settings
render_shop_admin({str(self.db)!r}, {str(self.root)!r}, get_settings({str(self.db)!r}), 'ru')'''
        app = AppTest.from_string(source).run()
        next(widget for widget in app.selectbox if widget.label == 'Какой товар редактируем?').set_value(self.product['id']).run()
        next(widget for widget in app.text_input if widget.label == 'Название RU').set_value('Сохранённый товар')
        next(widget for widget in app.button if widget.label == 'Сохранить товар').click().run()
        self.assertEqual(len(app.exception), 0, app.exception)
        self.assertEqual(get_product(self.db, self.product['id'])['name_ru'], 'Сохранённый товар')

    def test_customer_review_and_confirmation_create_exactly_one_real_order(self):
        from streamlit.testing.v1 import AppTest
        source = f'''from scena_shop import render_shop
from scena_core import get_settings
render_shop({str(self.db)!r}, {str(self.root)!r}, get_settings({str(self.db)!r}), 'ru')'''
        app = AppTest.from_string(source).run()
        self.assertEqual(len(app.exception), 0, app.exception)
        next(w for w in app.button if w.label == 'В корзину').click().run()
        next(w for w in app.button if w.label == 'Перейти к оформлению').click().run()
        next(w for w in app.text_input if w.label == 'Ваше имя').set_value('Анна Тест')
        next(w for w in app.text_input if w.label == 'Телефон').set_value('+37369123456')
        next(w for w in app.checkbox if w.label.startswith('Согласна')).check()
        next(w for w in app.button if w.label == 'Проверить заказ').click().run()
        self.assertEqual(list_orders(self.db), [])
        next(w for w in app.button if w.label == 'Подтвердить заказ').click().run()
        self.assertEqual(len(app.exception), 0, app.exception)
        self.assertEqual(len(list_orders(self.db)), 1)
        self.assertEqual(list_orders(self.db)[0]['total_cents'], 25975)
        self.assertTrue(any('Заказ принят' in w.value for w in app.success))

    def test_new_product_save_opens_saved_product_and_repeat_save_does_not_duplicate(self):
        from streamlit.testing.v1 import AppTest
        source = f'''from scena_shop import render_shop_admin
from scena_core import get_settings
render_shop_admin({str(self.db)!r}, {str(self.root)!r}, get_settings({str(self.db)!r}), 'ru')'''
        app = AppTest.from_string(source).run()
        next(w for w in app.text_input if w.label == 'Название RU').set_value('Новый черновик')
        next(w for w in app.text_input if w.label == 'Цена, MDL').set_value('100')
        next(w for w in app.button if w.label == 'Сохранить товар').click().run()
        self.assertEqual(len(app.exception), 0, app.exception)
        selected = next(w for w in app.selectbox if w.label == 'Какой товар редактируем?').value
        self.assertTrue(selected)
        self.assertEqual(len(list_products(self.db)), 2)
        next(w for w in app.button if w.label == 'Сохранить товар').click().run()
        self.assertEqual(len(list_products(self.db)), 2)
        self.assertEqual(len(app.exception), 0, app.exception)


if __name__ == '__main__':
    unittest.main()
