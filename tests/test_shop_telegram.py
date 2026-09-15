"""Real order outbox and binding boundaries; all Telegram calls are fake adapters."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import unittest
from unittest.mock import patch

import test_shop_v17 as shop_tests
import scena_shop_telegram as tg
from scena_shop import list_orders, init_shop, dial_number

TOKEN = '123456789:'+'a'*32


class ShopTelegramTests(unittest.TestCase):
    setUp = shop_tests.ShopTests.setUp
    make_photo = staticmethod(shop_tests.ShopTests.make_photo)
    fields = staticmethod(shop_tests.ShopTests.fields)
    buy = shop_tests.ShopTests.buy

    def bind(self):
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE profile_settings SET value='https://t.me/ownername' WHERE key='telegram_url'")
        patcher=patch.dict(os.environ,{'SCENA_TELEGRAM_CREDENTIAL_KEY':'test-only-encryption-key'})
        patcher.start();self.addCleanup(patcher.stop)
        with patch.object(tg.TelegramBotAdapter,'_call',return_value={'is_bot':True,'username':'OwnerTestBot'}):
            status=tg.begin_connection(self.db,TOKEN,now=1000)
        return status['pending']['code']

    def update(self, code, **changes):
        message={'text':code,'date':1001,'chat':{'id':501,'type':'private','username':'ownername'},'from':{'id':501,'is_bot':False}}
        message.update(changes)
        return [{'message':message}]

    def test_binds_exact_owner_private_chat_without_exposing_token(self):
        code=self.bind()
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=self.update(code)) as api:
            status=tg.confirm_connection(self.db,now=1002)
        self.assertTrue(status['connected'])
        self.assertNotIn(TOKEN,json.dumps(status))
        self.assertEqual(api.call_args.args[0],'getUpdates')
        with sqlite3.connect(self.db) as con:
            self.assertNotIn(TOKEN,con.execute('SELECT payload FROM shop_telegram_connection').fetchone()[0])
            con.execute("UPDATE profile_settings SET value='@otherowner' WHERE key='telegram_url'")
        self.assertFalse(tg.connection_status(self.db)['connected'])
        self.assertEqual(tg.dispatch(self.db),'unconfigured')
        with patch.dict(os.environ,{'SCENA_TELEGRAM_CREDENTIAL_KEY':'rotated-test-only-key'}), patch.object(tg.TelegramBotAdapter,'_call',return_value={'is_bot':True,'username':'ReplacementBot'}):
            self.assertEqual(tg.begin_connection(self.db,TOKEN,now=2000)['pending']['bot'],'ReplacementBot')

    def test_wrong_username_group_forward_and_expired_code_are_rejected(self):
        code=self.bind()
        for change in ({'chat':{'id':501,'type':'private','username':'stranger'}},
            {'chat':{'id':501,'type':'group','username':'ownername'}}, {'forward_origin':{'type':'user'}}, {'date':1}):
            with patch.object(tg.TelegramBotAdapter,'_call',return_value=self.update(code,**change)), self.assertRaises(tg.ConnectionError):
                tg.confirm_connection(self.db,now=1002)
        with patch.object(tg.TelegramBotAdapter,'_call') as api,self.assertRaises(tg.ConnectionError):
            tg.confirm_connection(self.db,now=1601)
        api.assert_not_called()

    def test_delivery_retries_preserve_order_and_double_dispatch_sends_once(self):
        order=self.buy()
        adapter=tg.TelegramBotAdapter(bot_token=TOKEN,admin_chat_id='501')
        with patch.object(adapter,'_call',side_effect=TimeoutError('credential must not escape')):
            self.assertEqual(tg.dispatch(self.db,order_id=order['id'],now=1000,adapter=adapter),'retry')
        saved=list_orders(self.db)[0]
        self.assertEqual(saved['status'],'new')
        self.assertEqual(saved['telegram_status'],'retry')
        self.assertEqual(saved['total_cents'],order['total_cents'])
        with patch.object(adapter,'_call',return_value={'message_id':99}) as api:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:tg.dispatch(self.db,now=2000,adapter=adapter),range(2)))
        self.assertEqual(sorted(results),['idle','sent'])
        api.assert_called_once()
        message=api.call_args.args[1]
        self.assertEqual(message['chat_id'],'501')
        for text in (order['reference'],dial_number(order['phone']),order['customer_name'],order['note'],order['items'][0]['name_ru']):
            self.assertIn(text,message['text'])
        self.assertNotIn('parse_mode',message)
        self.assertEqual(list_orders(self.db)[0]['telegram_message_id'],'99')

    def test_refresh_expired_binding_without_reentering_or_sending_token(self):
        old_code=self.bind()
        with patch.object(tg.TelegramBotAdapter,'_call') as api:
            tg.refresh_code(self.db,now=2000)
        api.assert_not_called()
        pending=tg.connection_status(self.db)['pending']
        self.assertNotEqual(pending['code'],old_code)
        self.assertEqual(pending['bot'],'OwnerTestBot')
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=self.update(pending['code'],date=2001)):
            self.assertTrue(tg.confirm_connection(self.db,now=2002)['connected'])

    def test_phone_is_plain_international_text_for_telegram_dialing(self):
        order=self.buy(contacts={**self.contact,'phone':'069 123-456'})
        self.assertIn('\nТелефон: +37369123456\n',tg.lead_text(order))
        for source in ('+373 (69) 123-456','069 123456','69123456','37369123456','0037369123456'):
            self.assertEqual(dial_number(source),'+37369123456')
        self.assertEqual(dial_number('+49 (151) 12345678'),'+4915112345678')
        for source in ('javascript:alert(1)','123#45678','+3731;ext=5','no phone'):
            self.assertEqual(dial_number(source),'')

    def test_no_connection_keeps_new_lead_and_migration_skips_historical_orders(self):
        self.buy()
        self.assertEqual(tg.dispatch(self.db),'unconfigured')
        self.assertEqual(list_orders(self.db)[0]['telegram_status'],'queued')
        with sqlite3.connect(self.db) as con:
            for name in ('telegram_status','telegram_attempts','telegram_retry_at','telegram_message_id'):
                con.execute('ALTER TABLE shop_orders DROP COLUMN '+name)
        init_shop(self.db)
        self.assertEqual(list_orders(self.db)[0]['telegram_status'],'skipped')

    def test_private_backup_removes_connection_credentials(self):
        self.bind()
        from scena_transfer import _remove_runtime_state
        with sqlite3.connect(self.db) as con:
            _remove_runtime_state(con)
            self.assertFalse(con.execute("SELECT 1 FROM sqlite_master WHERE name='shop_telegram_connection'").fetchone())
