"""Intake HTTP contract, isolated persistence, upload safety and delivery guarantees."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, AsyncMock
import uuid

from PIL import Image
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application, HTTPError
from scena_web.intake import Config, Store, Telegram, MAX_PHOTO, intake_routes, telegram_text
from scena_web.newcard import newcard_routes


def payload(photos=()):
    return {'id': str(uuid.uuid4()), 'website': '', 'photos': list(photos), 'answers': {
        'name': 'Проверка SCENA', 'brand': '', 'specialty': 'Визажист', 'city': '',
        'features': ['Запись на услуги'], 'languages': ['Русский'], 'services': '',
        'booking': 'Обсудим вместе', 'style': 'Доверюсь вам', 'inspiration': '', 'about': '',
        'domainStatus': 'Создадим вместе', 'domain': '', 'github': 'Создадим вместе', 'vercel': 'Создадим вместе',
        'accountEmail': '', 'contact': '@test_scena', 'timing': 'Без спешки', 'notes': '', 'consent': True,
    }}


def picture(padded=False):
    buf = BytesIO()
    Image.new('RGB', (20, 20), (220, 180, 190)).save(buf, format='JPEG')
    data = buf.getvalue()
    if padded:
        data += b'\0' * (MAX_PHOTO - len(data))
    return data, {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'type': 'image/jpeg'}


class FakeTelegram:
    calls = 0
    result = ('sent', 123)

    async def ready(self):
        return True

    async def send(self, text):
        self.calls += 1
        self.text = text
        return self.result


class IntakeTests(AsyncHTTPTestCase):
    def get_app(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'intake.db'
        def connect():
            db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
            db.row_factory = sqlite3.Row
            return db
        config = Config('libsql://intake.test', 'test', 'test-private-store-key', '123:test', '123456', True)
        self.store, self.telegram = Store(config, connect), FakeTelegram()
        self.blobs = {}
        def put(path, content, mime):
            self.blobs[path] = content
            return path
        self.store.write_blob = put
        return Application([*newcard_routes(), *intake_routes((self.store, self.telegram))])

    def get_httpserver_options(self):
        return {'max_buffer_size': MAX_PHOTO}

    def request(self, path, data=None, token=None, method='POST', origin='https://scena.life', mime='application/json'):
        headers = {'Origin': origin, 'Content-Type': mime}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        return self.fetch(path, method=method, headers=headers, body=body if method not in ('GET','HEAD') else None)

    def start(self, p):
        response = self.request('/api/intake/start', p)
        self.assertEqual(response.code, 200, response.body)
        return json.loads(response.body)['uploadToken']

    def test_text_delivery_and_retry_exactly_one_message(self):
        p = payload(); token = self.start(p)
        path = f"/api/intake/{p['id']}/send"
        r = self.request(path, token=token)
        self.assertEqual(json.loads(r.body), {'stored': True, 'delivered': True})
        self.assertEqual(json.loads(self.request(path, token=token).body), {'stored': True, 'delivered': True})
        self.start(p)
        self.assertEqual(self.telegram.calls, 1)
        self.assertEqual(self.store.row(p['id'])['message_id'], 123)
        self.assertIn('@test_scena', self.telegram.text)

    def test_six_four_megabyte_photos_fit_individual_requests_and_block_early_send(self):
        data, meta = picture(padded=True)
        p = payload([meta] * 6); token = self.start(p)
        base = f"/api/intake/{p['id']}"
        self.assertEqual(self.request(base+'/send', token=token).code, 409)
        for i in range(6):
            r = self.request(base+f'/photos/{i}', data, token, 'PUT', mime='image/jpeg')
            self.assertEqual(r.code, 200, r.body)
        self.assertEqual(len(self.blobs), 6)
        r = self.request(base+'/send', token=token)
        self.assertEqual(json.loads(r.body)['delivered'], True)
        self.assertEqual(self.telegram.calls, 1)
        self.assertIn('/newcard/photos/', self.telegram.text)
        self.assertNotIn('?token=', self.telegram.text)
        self.assertEqual(self.request(base+'/photos/0', data, token, 'PUT', mime='image/jpeg').code, 409)

    def test_invalid_photo_and_storage_failure_do_not_send(self):
        data = b'not-a-jpeg'
        p = payload([{'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'type':'image/jpeg'}])
        token = self.start(p); base = f"/api/intake/{p['id']}"
        self.assertEqual(self.request(base+'/photos/0', data, token, 'PUT', mime='image/jpeg').code, 400)
        data, meta = picture(); p = payload([meta]); token = self.start(p); base = f"/api/intake/{p['id']}"
        with patch.object(self.store, 'write_blob', side_effect=RuntimeError('SECRET-TOKEN')):
            r = self.request(base+'/photos/0', data, token, 'PUT', mime='image/jpeg')
        self.assertEqual(r.code, 500)
        self.assertNotIn(b'SECRET', r.body)
        self.assertEqual(self.request(base+'/send', token=token).code, 409)
        self.assertEqual(self.telegram.calls, 0)

    def test_uncertain_send_saved_without_false_success_or_retry(self):
        self.telegram.result = ('uncertain', None)
        p = payload(); token = self.start(p); path = f"/api/intake/{p['id']}/send"
        for _ in range(2):
            self.assertEqual(json.loads(self.request(path, token=token).body), {'stored': True, 'delivered': False})
        self.assertEqual(self.telegram.calls, 1)
        self.assertEqual(self.store.row(p['id'])['state'], 'uncertain')

    def test_capabilities_are_separate_and_expire(self):
        p = payload(); upload = self.start(p); row = self.store.row(p['id'])
        gallery = self.store.token('gallery', row); base=f"/api/intake/{p['id']}"
        self.assertEqual(self.request(base+'/gallery', token=upload, method='GET').code, 404)
        r = self.request(base+'/gallery', token=gallery, method='GET')
        self.assertEqual(r.code, 200)
        self.assertEqual(r.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.request(base+'/send', token=gallery).code, 404)
        self.store.run(lambda db: db.execute('UPDATE intake SET expires=0'))
        self.assertEqual(self.request(base+'/gallery', token=gallery, method='GET').code, 404)
        shell = self.fetch('/newcard/photos/'+p['id'])
        self.assertEqual(shell.code, 200)
        self.assertNotIn(p['answers']['name'].encode(), shell.body)
        self.assertEqual(shell.headers['Referrer-Policy'], 'no-referrer')

    def test_strict_validation_origin_and_conflicting_retry(self):
        p=payload(); p['answers']['consent']=False
        self.assertEqual(self.request('/api/intake/start', p).code, 400)
        p=payload(); p['website']='spam'
        self.assertEqual(self.request('/api/intake/start', p).code, 400)
        p=payload(); p['extra']='no'
        self.assertEqual(self.request('/api/intake/start', p).code, 400)
        p=payload()
        self.assertEqual(self.request('/api/intake/start', p, origin='https://evil.test').code, 403)
        self.start(p); p['answers']['notes']='changed'
        self.assertEqual(self.request('/api/intake/start', p).code, 409)

    def test_rate_limit_and_storage_quota(self):
        for _ in range(4):
            self.start(payload())
        self.assertEqual(self.request('/api/intake/start', payload()).code, 429)
        self.store.run(lambda db: db.execute('DELETE FROM intake'))
        self.store.config=replace(self.store.config,max_bytes=1)
        _, meta=picture()
        self.assertEqual(self.request('/api/intake/start', payload([meta])).code, 429)

    def test_simultaneous_delivery_claim_has_single_winner(self):
        p=payload(); token=self.start(p)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _: self.store.claim(p['id'],token)[1],range(6)))
        self.assertEqual(sum(results),1)

    def test_gallery_photo_integrity_and_private_access(self):
        data,meta=picture(); p=payload([meta]); upload=self.start(p); base=f"/api/intake/{p['id']}"
        self.request(base+'/photos/0',data,upload,'PUT',mime='image/jpeg')
        gallery=self.store.token('gallery',self.store.row(p['id']))
        from types import SimpleNamespace
        with patch('vercel.blob.get',return_value=SimpleNamespace(status_code=200,content=data)):
            r=self.request(base+'/photos/0',token=gallery,method='GET')
        self.assertEqual(r.body,data)
        self.assertEqual(r.headers['Cache-Control'],'no-store')
        with patch('vercel.blob.get',return_value=SimpleNamespace(status_code=200,content=b'corrupt')):
            self.assertEqual(self.request(base+'/photos/0',token=gallery,method='GET').code,502)
        self.assertEqual(self.request(base+'/photos/0',token='0'*64,method='GET').code,404)

    @gen_test
    async def test_bot_identity_and_telegram_confirmation_required(self):
        telegram=Telegram(self.store.config)
        with patch.object(telegram,'call',new=AsyncMock(side_effect=[
            {'ok':True,'result':{'username':'another_bot'}},
            {'ok':True,'result':{'id':123456,'type':'private'}}])):
            self.assertFalse(await telegram.ready())
        telegram=Telegram(self.store.config)
        with patch.object(telegram,'call',new=AsyncMock(side_effect=[
            {'ok':True,'result':{'username':'scenalive_bot'}},
            {'ok':True,'result':{'id':123456,'type':'private'}}])):
            self.assertTrue(await telegram.ready())
        for result, expected in [({'ok':True,'result':{}},'uncertain'),({'ok':False},'failed'),
                                ({'ok':True,'result':{'message_id':7,'chat':{'id':123456}}},'sent')]:
            with patch.object(telegram,'call',new=AsyncMock(return_value=result)):
                self.assertEqual((await telegram.send('test'))[0],expected)
        with patch.object(telegram,'call',new=AsyncMock(side_effect=TimeoutError)):
            self.assertEqual((await telegram.send('test'))[0],'uncertain')

    def test_dedicated_config_never_falls_back_to_salon(self):
        with patch.dict(os.environ,{'SCENA_TURSO_TURSO_DATABASE_URL':'libsql://salon','SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN':'salon-secret'},clear=True):
            config=Config.from_env()
            self.assertFalse(config.configured())
            self.assertEqual(config.database,'')
            self.assertEqual(config.blob,'')


if __name__ == '__main__':
    unittest.main()
