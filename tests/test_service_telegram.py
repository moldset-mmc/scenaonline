"""Real booking transactions; all Telegram traffic is intercepted."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
import sqlite3
import unittest
from unittest.mock import patch

import test_shop_v17 as shop_tests
import test_shop_telegram as shop_telegram_tests
import scena_shop_telegram as tg
import scena_service_telegram as service_tg
from scena_core import (CHISINAU, RequestValidationError, create_service_request, generate_available_slots,
    get_settings, init_db, list_requests, list_services, list_sms_outbox, save_settings, update_request_status)


class ServiceTelegramTests(unittest.TestCase):
    setUp = shop_tests.ShopTests.setUp
    make_photo = staticmethod(shop_tests.ShopTests.make_photo)
    fields = staticmethod(shop_tests.ShopTests.fields)
    bind = shop_telegram_tests.ShopTelegramTests.bind
    update = shop_telegram_tests.ShopTelegramTests.update
    active_actions = shop_telegram_tests.ShopTelegramTests.active_actions

    def book(self, channel='telegram', **changes):
        save_settings(self.db, {'schedule_weekdays':'0,1,2,3,4,5,6', 'schedule_start':'08:00',
            'schedule_end':'18:00', 'minimum_lead_hours':'0'})
        self.moment = datetime.now(CHISINAU).replace(microsecond=0)
        service = list_services(self.db, 'Professional', kind='appointment')[0]
        day = (self.moment.date()+timedelta(days=3)).isoformat()
        slot = generate_available_slots(self.db,service['id'],day,now=self.moment)[0]
        values = dict(service_id=service['id'],slot_date=day,slot_time=slot,name='Booking fixture',phone='060000001',
            contact_channel=channel,telegram='@clientname' if channel=='telegram' else '',
            email='client@example.com' if channel=='email' else '',consent=True,locale='ru',now=self.moment)
        values.update(changes)
        return create_service_request(self.db,**values)

    def row(self, identity):
        with sqlite3.connect(self.db) as con:
            con.row_factory=sqlite3.Row
            return dict(con.execute('SELECT * FROM requests WHERE id=?',(identity,)).fetchone())

    def deliver(self, channel='telegram'):
        config=self.active_actions()
        self.callback_config = config.copy()
        identity=self.book(channel)
        with patch.object(tg.TelegramBotAdapter,'_call',return_value={'message_id':201}) as api:
            self.assertEqual(service_tg.dispatch(self.db,request_id=identity),'sent')
        return config,identity,api.call_args.args[1]

    def callback(self, payload, label):
        if label not in [b['text'] for line in payload['reply_markup']['inline_keyboard'] for b in line]:
            menu = self.callback(payload, 'Сменить статус')
            with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as api:
                tg.receive_update(self.db, menu, self.callback_config['webhook_secret'], now=self.moment.timestamp())
            payload = next(c.args[1] for c in api.call_args_list if c.args[0]=='editMessageText')
        data=next(button['callback_data'] for row in payload['reply_markup']['inline_keyboard'] for button in row if button['text']==label)
        return {'update_id':404,'callback_query':{'id':'service-query','from':{'id':501,'is_bot':False},
            'message':{'message_id':201,'chat':{'id':501,'type':'private'}},'data':data}}

    def test_channel_contact_validation_and_sms_choice_are_persisted(self):
        for channel,changes in [('telegram',{'telegram':''}),('telegram',{'telegram':'bad/name'}),('email',{'email':''}),('email',{'email':'bad'}),('other',{})]:
            with self.subTest(channel=channel,changes=changes),self.assertRaises(RequestValidationError):
                self.book(channel,**changes)
        for channel,prefix in [('phone','tel:'),('telegram','https://t.me/'),('sms','sms:')]:
            identity=self.book(channel)
            row=self.row(identity)
            self.assertEqual(row['contact_channel'],channel)
            self.assertEqual(row['telegram_status'],'queued')
            self.assertTrue(service_tg.reply_link(row).startswith(prefix))
            self.assertEqual(len([m for m in list_sms_outbox(self.db) if m['request_id']==identity]),1 if channel=='sms' else 0)
        identity=self.book('email')
        row=self.row(identity)
        self.assertEqual(row['contact_channel'],'email')
        self.assertEqual(service_tg.reply_link(row),'')
        self.assertEqual(len([m for m in list_sms_outbox(self.db) if m['request_id']==identity]),0)
        self.assertEqual(service_tg.validate_reply_contact('telegram','https://t.me/ClientName',''),'@clientname')

    def test_one_lead_contains_booking_contacts_channel_and_supported_buttons(self):
        config,identity,payload=self.deliver()
        row=self.row(identity)
        for value in (row['service'],datetime.fromisoformat(row['preferred_date']).strftime('%d.%m.%Y'),row['preferred_time'],'+37360000001','@clientname','Ответить в Telegram: @clientname'):
            self.assertIn(value,payload['text'])
        buttons=[b for line in payload['reply_markup']['inline_keyboard'] for b in line]
        self.assertEqual([b['text'] for b in buttons],['Открыть заявку','Ответить в Telegram','Сменить статус'])
        self.assertEqual(buttons[0]['url'],'https://scena.example'+service_tg.request_path(identity))
        self.assertEqual(buttons[1]['url'],'https://t.me/clientname')
        for b in buttons:
            if 'callback_data' in b:self.assertLessEqual(len(b['callback_data'].encode()),64)
        for channel in ('phone','sms','email'):
            row.update(contact_channel=channel,email='client@example.com')
            buttons=service_tg.lead_buttons(self.db,row,config)['reply_markup']['inline_keyboard']
            if channel in ('phone','email'):
                self.assertEqual([b[0]['text'] for b in buttons], ['Открыть заявку','Сменить статус'])
            else:
                self.assertTrue(buttons[1][0]['url'].endswith('#request-contact'))
        with patch.object(tg.TelegramBotAdapter,'_call') as api:
            self.assertEqual(service_tg.dispatch(self.db,request_id=identity),'idle')
        api.assert_not_called()

    def test_contact_then_confirm_updates_same_message_and_keeps_slot(self):
        config,identity,payload=self.deliver()
        contact=self.callback(payload,'Связались')
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as api:
            tg.receive_update(self.db,contact,config['webhook_secret'],now=self.moment.timestamp()+1)
        self.assertEqual((self.row(identity)['status'],self.row(identity)['revision']),('Связались',2))
        edited=next(c.args[1] for c in api.call_args_list if c.args[0]=='editMessageText')
        confirm=self.callback(edited,'Подтверждена')
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as api:
            tg.receive_update(self.db,confirm,config['webhook_secret'],now=self.moment.timestamp()+2)
            tg.receive_update(self.db,contact,config['webhook_secret'],now=self.moment.timestamp()+3)
        row=self.row(identity)
        self.assertEqual((row['status'],row['revision']),('Подтверждена',3))
        self.assertNotIn(row['preferred_time'],generate_available_slots(self.db,row['service_id'],row['preferred_date'],now=self.moment))
        edits=[c.args[1] for c in api.call_args_list if c.args[0]=='editMessageText']
        for edit in edits:
            self.assertEqual(edit['message_id'],201)
            self.assertIn('Подтверждена',edit['text'])
            self.assertTrue(any('callback_data' in b for line in edit['reply_markup']['inline_keyboard'] for b in line))
        self.assertFalse(list_sms_outbox(self.db),'Telegram choice must not queue customer SMS')

    def test_concurrent_confirmation_is_idempotent_and_queues_one_selected_sms(self):
        config,identity,payload=self.deliver('sms')
        update=self.callback(payload,'Подтверждена')
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=True):
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda _:tg.receive_update(self.db,update,config['webhook_secret'],now=self.moment.timestamp()+1),range(2)))
        self.assertEqual((self.row(identity)['status'],self.row(identity)['revision']),('Подтверждена',2))
        self.assertEqual([m['event'] for m in list_sms_outbox(self.db)],['request_received','confirmed'])

    def test_forged_owner_header_signature_message_and_binding_do_not_change_booking(self):
        config,identity,payload=self.deliver()
        update=self.callback(payload,'Подтверждена')
        with self.assertRaises(PermissionError):tg.receive_update(self.db,update,'wrong-secret')
        original_update = copy.deepcopy(update)
        variants=[]
        for path,value in [(('from','id'),999),(('message','message_id'),999),(('message','chat'),{'id':501,'type':'group'})]:
            changed=copy.deepcopy(update);changed['callback_query'][path[0]][path[1]]=value;variants.append(changed)
        changed=copy.deepcopy(update);changed['callback_query']['data']+='x';variants.append(changed)
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as api:
            for update in variants:tg.receive_update(self.db,update,config['webhook_secret'])
            config['action_secret']='different-owner-binding';tg._save(self.db,config)
            tg.receive_update(self.db,original_update,config['webhook_secret'])
        self.assertTrue(all(c.args[0]=='answerCallbackQuery' for c in api.call_args_list))
        self.assertEqual(self.row(identity)['revision'],1)

    def test_expired_and_past_bookings_cannot_be_confirmed(self):
        config,identity,payload=self.deliver()
        update=self.callback(payload,'Подтверждена')
        expires=datetime.fromisoformat(self.row(identity)['hold_expires_at']).timestamp()
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=True):
            tg.receive_update(self.db,update,config['webhook_secret'],now=expires+1)
        self.assertEqual(self.row(identity)['status'],'Срок подтверждения истёк')
        # Even an inconsistent long hold may not confirm a past appointment.
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE requests SET status='Ожидает подтверждения',revision=1,hold_expires_at=? WHERE id=?",((self.moment+timedelta(days=10)).isoformat(),identity))
        slot=datetime.fromisoformat(self.row(identity)['slot_start']).timestamp()
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as api:
            tg.receive_update(self.db,update,config['webhook_secret'],now=slot+1)
        self.assertEqual(self.row(identity)['status'],'Ожидает подтверждения')
        self.assertIn('уже прошло',api.call_args.args[1]['text'])

    def test_occupied_time_and_newer_cabinet_status_block_old_action(self):
        config,identity,payload=self.deliver()
        original=self.row(identity)
        other=self.book('phone')
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE requests SET slot_start=?,slot_block_end=?,status='Подтверждена' WHERE id=?",(original['slot_start'],original['slot_block_end'],other))
        update=self.callback(payload,'Подтверждена')
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as api:
            tg.receive_update(self.db,update,config['webhook_secret'],now=self.moment.timestamp()+1)
        self.assertIn('уже занято',api.call_args.args[1]['text'])
        self.assertEqual(self.row(identity)['revision'],1)
        update_request_status(self.db,identity,'Отменена',expected_revision=1)
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=True):
            tg.receive_update(self.db,update,config['webhook_secret'])
        self.assertEqual(self.row(identity)['status'],'Отменена')
        with self.assertRaises(RequestValidationError):
            update_request_status(self.db,identity,'Связались',expected_revision=1)

    def test_send_failure_preserves_booking_retry_lease_sends_once(self):
        config=self.active_actions();identity=self.book('phone')
        with patch.object(tg.TelegramBotAdapter,'_call',side_effect=TimeoutError('never expose token')):
            self.assertEqual(service_tg.dispatch(self.db,request_id=identity,now=1000),'retry')
        self.assertEqual(self.row(identity)['status'],'Ожидает подтверждения')
        with patch.object(tg.TelegramBotAdapter,'_call',return_value={'message_id':201}) as api:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:service_tg.dispatch(self.db,now=2000),range(2)))
        self.assertEqual(sorted(results),['idle','sent']);api.assert_called_once()

    def test_edit_timeout_keeps_confirmed_booking_and_retries_only_message(self):
        config,identity,payload=self.deliver()
        update=self.callback(payload,'Подтверждена')
        with patch.object(tg.TelegramBotAdapter,'_call',side_effect=[TimeoutError(),True]):
            tg.receive_update(self.db,update,config['webhook_secret'])
        self.assertEqual(self.row(identity)['status'],'Подтверждена')
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=True):
            tg.receive_update(self.db,update,config['webhook_secret'])
        self.assertEqual(self.row(identity)['revision'],2)

    def test_additive_migration_does_not_send_historical_requests(self):
        identity=self.book('phone')
        with sqlite3.connect(self.db) as con:
            for name in ('revision','contact_telegram','telegram_status','telegram_attempts','telegram_retry_at','telegram_message_id'):
                con.execute('ALTER TABLE requests DROP COLUMN '+name)
        init_db(self.db)
        row=self.row(identity)
        self.assertEqual(row['name'],'Booking fixture')
        self.assertEqual(row['telegram_status'],'skipped')
        self.assertEqual(service_tg.dispatch(self.db),'unconfigured')

    def test_menu_back_all_statuses_and_refresh_leave_booking_unchanged(self):
        from scena_core import REQUEST_STATUSES
        config,identity,payload=self.deliver('phone')
        before=self.row(identity)
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as api:
            tg.receive_update(self.db,self.callback(payload,'Сменить статус'),config['webhook_secret'],now=self.moment.timestamp())
            menu=next(c.args[1] for c in api.call_args_list if c.args[0]=='editMessageText')
            labels=[b['text'] for line in menu['reply_markup']['inline_keyboard'] for b in line]
            for status in REQUEST_STATUSES:self.assertTrue(any(status in label for label in labels))
            tg.receive_update(self.db,self.callback(menu,'Назад'),config['webhook_secret'],now=self.moment.timestamp())
            tg.refresh_lead(self.db,'service',identity)
        self.assertEqual(self.row(identity),before)
        self.assertTrue(all(c.args[0] in ('editMessageText','answerCallbackQuery') for c in api.call_args_list))
        self.assertNotIn('Позвонить',json.dumps(api.call_args.args[1],ensure_ascii=False))
        self.assertNotIn('Канал ответа',payload['text'])
        self.assertEqual(payload['text'].count('Кишинёв'),1)
        self.assertNotIn(before['preferred_date'],payload['text'])

    def test_menu_closed_statuses_and_expiry_cannot_reclaim_occupied_slot(self):
        config,identity,payload=self.deliver()
        for status in ('Отклонена','Новая','Завершена','Отменена'):
            update=self.callback(payload,status)
            with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as api:
                tg.receive_update(self.db,update,config['webhook_secret'],now=self.moment.timestamp())
            self.assertEqual(self.row(identity)['status'],status)
            payload=next(c.args[1] for c in api.call_args_list if c.args[0]=='editMessageText')
        original=self.row(identity)
        self.book('phone',slot_date=original['preferred_date'],slot_time=original['preferred_time'])
        for status in ('Ожидает подтверждения','Связались','Подтверждена'):
            with self.subTest(status=status),self.assertRaisesRegex(RequestValidationError,'уже занято'):
                update_request_status(self.db,identity,status,expected_revision=original['revision'],now=self.moment)
        self.assertEqual(self.row(identity),original)

    def test_previously_delivered_service_button_still_works(self):
        config,identity,payload=self.deliver('phone')
        value=f's:{identity}:1:c'
        update=self.callback(payload,'Сменить статус')
        update['callback_query']['data']=value+':'+tg._signature(config,value)
        with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as api:
            tg.receive_update(self.db,update,config['webhook_secret'],now=self.moment.timestamp())
        self.assertEqual(self.row(identity)['status'],'Связались')
        edited=next(c.args[1] for c in api.call_args_list if c.args[0]=='editMessageText')
        self.assertEqual([line[0]['text'] for line in edited['reply_markup']['inline_keyboard']],['Открыть заявку','Сменить статус'])
