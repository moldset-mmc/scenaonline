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

    def test_change_recipient_here_requires_new_private_chat_proof(self):
        code = self.bind()
        with patch.object(tg.TelegramBotAdapter, '_call', return_value=self.update(code)):
            tg.confirm_connection(self.db, now=1002)
        old = tg._load(self.db)
        tg.change_recipient(self.db, '@newowner')
        self.assertFalse(tg.connection_status(self.db)['connected'])
        with patch.object(tg.TelegramBotAdapter, '_call', return_value={'is_bot':True, 'username':'OwnerTestBot'}):
            pending = tg.begin_connection(self.db, '', now=1010)['pending']
        with patch.object(tg.TelegramBotAdapter, '_call', return_value=self.update(pending['code'], date=1011)):
            with self.assertRaises(tg.ConnectionError):
                tg.confirm_connection(self.db, now=1012)
        good = self.update(pending['code'], date=1011, chat={'id':502, 'type':'private', 'username':'newowner'}, **{'from':{'id':502, 'is_bot':False}})
        with patch.object(tg.TelegramBotAdapter, '_call', return_value=good):
            self.assertTrue(tg.confirm_connection(self.db, now=1012)['connected'])
        self.assertEqual(tg._load(self.db)['chat_id'], '502')
        self.assertNotEqual(tg._load(self.db)['action_secret'], old['action_secret'])
        with self.assertRaises(tg.ConnectionError):
            tg.change_recipient(self.db, 'https://evil.example/owner')
        self.assertTrue(tg.connection_status(self.db)['connected'])

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

    def test_checkout_rejects_incomplete_moldovan_number(self):
        from scena_shop import _contacts, ShopError
        for phone in ('+3737475858','003737475858','+373747585899'):
            with self.subTest(phone=phone),self.assertRaises(ShopError):
                _contacts({**self.contact,'phone':phone})
        self.assertEqual(_contacts({**self.contact,'phone':'+37374758589'})['phone'],'+37374758589')

    def test_order_menu_all_statuses_back_and_refresh_do_not_duplicate_orders(self):
        from scena_shop import ORDER_STATES, _t
        config,order,update=self.delivered_action()
        before=list_orders(self.db)[0]
        for state in ORDER_STATES:
            row=list_orders(self.db)[0]
            markup=tg.lead_buttons(self.db,row,config)
            update['callback_query']['data']=markup['reply_markup']['inline_keyboard'][1][0]['callback_data']
            with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as api:
                tg.receive_update(self.db,update,config['webhook_secret'])
                self.assertEqual(list_orders(self.db)[0],row)
                menu=next(c.args[1] for c in api.call_args_list if c.args[0]=='editMessageText')
                choices=[b for line in menu['reply_markup']['inline_keyboard'] for b in line]
                self.assertEqual(len(choices),len(ORDER_STATES)+1)
                update['callback_query']['data']=next(b['callback_data'] for b in choices if b['text'].removeprefix('✓ ')==_t(state,'ru'))
                tg.receive_update(self.db,update,config['webhook_secret'])
            self.assertEqual(list_orders(self.db)[0]['status'],state)
        final=list_orders(self.db)[0]
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as api:
            tg.refresh_lead(self.db,'order',order['id'])
        api.assert_called_once()
        self.assertEqual(api.call_args.args[0],'editMessageText')
        self.assertEqual(list_orders(self.db)[0],final)
        self.assertEqual(final['items'],before['items'])

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

    def active_actions(self):
        code = self.bind()
        with patch.object(tg.TelegramBotAdapter, '_call', return_value=self.update(code)):
            tg.confirm_connection(self.db, now=1002)
        patcher = patch.dict(os.environ, {'SCENA_NATIVE_WEB':'1', 'SCENA_PUBLIC_BASE_URL':'https://scena.example'})
        patcher.start(); self.addCleanup(patcher.stop)
        with patch.object(tg.TelegramBotAdapter, '_call', side_effect=[{'url':''}, True, {'url':'https://scena.example/scena-telegram'}]) as api:
            tg.enable_actions(self.db)
        self.assertEqual([c.args[0] for c in api.call_args_list], ['getWebhookInfo','setWebhook','getWebhookInfo'])
        registration = api.call_args_list[1].args[1]
        self.assertFalse(registration['drop_pending_updates'])
        self.assertEqual(registration['allowed_updates'], ['message','callback_query'])
        self.assertTrue(tg.connection_status(self.db)['actions_ready'])
        self.assertNotIn('secret', json.dumps(tg.connection_status(self.db)))
        return tg._load(self.db)

    def delivered_action(self):
        config = self.active_actions()
        order = self.buy()
        with patch.object(tg.TelegramBotAdapter, '_call', return_value={'message_id':99}) as api:
            self.assertEqual(tg.dispatch(self.db, order_id=order['id']), 'sent')
        buttons = api.call_args.args[1]['reply_markup']['inline_keyboard']
        self.assertEqual([row[0]['text'] for row in buttons], ['Открыть заказ','Сменить статус'])
        self.assertEqual(buttons[0][0]['url'], 'https://scena.example'+tg.order_path(order['id']))
        self.assertLessEqual(len(buttons[1][0]['callback_data'].encode()), 64)
        callback = {'update_id':77, 'callback_query':{'id':'fixture-query', 'from':{'id':501,'is_bot':False},
            'message':{'message_id':99, 'chat':{'id':501,'type':'private'}}, 'data':buttons[1][0]['callback_data']}}
        with patch.object(tg.TelegramBotAdapter, '_call', return_value=True) as api:
            tg.receive_update(self.db, callback, config['webhook_secret'])
        menu = next(c.args[1] for c in api.call_args_list if c.args[0]=='editMessageText')
        callback['callback_query']['data'] = next(b['callback_data'] for line in menu['reply_markup']['inline_keyboard'] for b in line if b['text']=='Связались')
        return config, order, callback

    def test_owner_callback_commits_once_updates_same_message_and_removes_action(self):
        config, order, update = self.delivered_action()
        with patch.object(tg.TelegramBotAdapter, '_call', return_value=True) as api:
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda _: tg.receive_update(self.db, update, config['webhook_secret']), range(2)))
        saved = list_orders(self.db)[0]
        self.assertEqual((saved['status'], saved['revision']), ('contacted',2))
        self.assertEqual(saved['items'], order['items'])
        edits = [c.args[1] for c in api.call_args_list if c.args[0] == 'editMessageText']
        self.assertEqual(len(edits), 2)
        for edit in edits:
            self.assertEqual(edit['message_id'], 99)
            self.assertEqual(edit['chat_id'], '501')
            self.assertIn('Статус: Связались', edit['text'])
            self.assertTrue(edit['reply_markup']['inline_keyboard'])

    def test_callback_rejects_wrong_header_owner_chat_message_signature_and_old_binding(self):
        import copy
        config, order, update = self.delivered_action()
        with patch.object(tg.TelegramBotAdapter, '_call') as api, self.assertRaises(PermissionError):
            tg.receive_update(self.db, update, 'wrong-header')
        api.assert_not_called()
        variants = []
        for path, value in [(('from','id'),999), (('message','message_id'),100), (('message','chat'),{'id':501,'type':'group'})]:
            changed = copy.deepcopy(update)
            changed['callback_query'][path[0]][path[1]] = value
            variants.append(changed)
        tampered = copy.deepcopy(update)
        tampered['callback_query']['data'] += 'x'
        variants.append(tampered)
        with patch.object(tg.TelegramBotAdapter, '_call', return_value=True) as api:
            for variant in variants:
                tg.receive_update(self.db, variant, config['webhook_secret'])
            config['action_secret'] = 'replacement-binding-key'
            tg._save(self.db, config)
            tg.receive_update(self.db, update, config['webhook_secret'])
        self.assertTrue(all(c.args[0]=='answerCallbackQuery' for c in api.call_args_list))
        self.assertEqual(list_orders(self.db)[0]['status'], 'new')

    def test_old_callback_never_downgrades_cabinet_status_or_overwrites_new_revision(self):
        from scena_shop import update_order_status
        config, order, update = self.delivered_action()
        for status in ('confirmed','fulfilled','cancelled','new'):
            saved = list_orders(self.db)[0]
            update_order_status(self.db, order['id'], status, expected_revision=saved['revision'])
            before = list_orders(self.db)[0]
            with patch.object(tg.TelegramBotAdapter, '_call', return_value=True):
                tg.receive_update(self.db, update, config['webhook_secret'])
            self.assertEqual(list_orders(self.db)[0], before)

    def test_edit_failure_keeps_saved_status_and_repeated_tap_retries_message_only(self):
        config, order, update = self.delivered_action()
        with patch.object(tg.TelegramBotAdapter, '_call', side_effect=[TimeoutError('never expose token'),True]) as api:
            tg.receive_update(self.db, update, config['webhook_secret'])
        self.assertEqual(list_orders(self.db)[0]['status'], 'contacted')
        self.assertIn('В SCENA сохранён', api.call_args.args[1]['text'])
        with patch.object(tg.TelegramBotAdapter, '_call', return_value=True):
            tg.receive_update(self.db, update, config['webhook_secret'])
        self.assertEqual(list_orders(self.db)[0]['revision'], 2)

    def test_registration_never_replaces_foreign_hook_and_can_retry_timeout(self):
        config = self.active_actions()
        with patch.object(tg.TelegramBotAdapter, '_call', return_value={'url':'https://other.example/bot'}) as api, self.assertRaises(tg.ConnectionError):
            tg.enable_actions(self.db)
        api.assert_called_once_with('getWebhookInfo', {})
        self.assertEqual(tg._load(self.db), config)
        with patch.object(tg.TelegramBotAdapter, '_call', side_effect=[{'url':config['webhook_url']},TimeoutError('private-token')]), self.assertRaises(tg.ConnectionError) as error:
            tg.enable_actions(self.db)
        self.assertNotIn('private-token', str(error.exception))
        self.assertFalse(tg.connection_status(self.db)['actions_ready'])
        with patch.object(tg.TelegramBotAdapter, '_call', side_effect=[{'url':config['webhook_url']},True,{'url':config['webhook_url']}]) as api:
            tg.enable_actions(self.db)
        self.assertEqual(api.call_args_list[1].args[1]['secret_token'], config['webhook_secret'])
        self.assertTrue(tg.connection_status(self.db)['actions_ready'])

    def test_rebinding_uses_webhook_challenge_and_refresh_revokes_previous_code(self):
        config = self.active_actions()
        with patch.object(tg.TelegramBotAdapter, '_call', return_value={'is_bot':True,'username':'OwnerTestBot'}):
            pending = tg.begin_connection(self.db, TOKEN, now=2000)['pending']
        message = self.update(pending['code'], date=2001)[0]
        tg.receive_update(self.db, message, config['webhook_secret'], now=2002)
        tg.refresh_code(self.db, now=2003)
        with patch.object(tg.TelegramBotAdapter, '_call') as api, self.assertRaises(tg.ConnectionError):
            tg.confirm_connection(self.db, now=2004)
        api.assert_not_called()
        pending = tg.connection_status(self.db)['pending']
        tg.receive_update(self.db, self.update(pending['code'], date=2004)[0], config['webhook_secret'], now=2005)
        with patch.object(tg.TelegramBotAdapter, '_call') as api:
            self.assertTrue(tg.confirm_connection(self.db, now=2006)['connected'])
        api.assert_not_called()
        rebound = tg._load(self.db)
        self.assertEqual(rebound['webhook_secret'], config['webhook_secret'])
        self.assertNotEqual(rebound['action_secret'], config['action_secret'])
