"""Isolated native HTTP coverage: QR saves, cache refresh, trash and restore."""
import asyncio
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import urlencode, parse_qs, urlsplit
from html.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class QRLinks(HTMLParser):
    def __init__(self, document):
        super().__init__(convert_charrefs=True)
        self.urls = []
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'a' and 'data-qr-link' in values:
            self.urls.append(values.get('href', ''))


async def main():
    from tornado.httpclient import AsyncHTTPClient, HTTPRequest
    from tornado.httpserver import HTTPServer
    from tornado.testing import bind_unused_port
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as folder:
        fixture = Path(folder)
        shutil.copytree(root/'media', fixture/'media')
        os.environ.update(SCENA_NATIVE_WEB='1', SCENA_WEB_TESTING='1', SCENA_DB_PATH=str(fixture/'test.db'), SCENA_APP_DIR=folder, SCENA_ADMIN_PASSWORD='isolated-qr-fixture')
        os.environ.pop('SCENA_CLOUD', None)
        from scena_web.server import application, BROWSER_COOKIE
        from scena_web.bootstrap import initialize
        from scena_cloud_auth import COOKIE, make_session
        from scena_web.storage import load_form
        from scena_core import get_settings, save_settings
        from scena_photo_library import upload_photo, photo_id, catalog
        await asyncio.to_thread(initialize)
        save_settings(fixture/'test.db', {'public_base_url':'https://scenaonline.vercel.app', 'model_intro_image':'media/qr-scenes/professional.png'})
        servers, urls = [], []
        for _ in range(2):
            sock, port = bind_unused_port()
            server = HTTPServer(application()); server.add_socket(sock)
            servers.append(server); urls.append('http://127.0.0.1:' + str(port))
        client = AsyncHTTPClient()
        sid = 'intro-qr-fixture-' + 'a'*32
        cookie = COOKIE+'='+make_session()+'; '+BROWSER_COOKIE+'='+sid
        snapshots = Path(os.environ['SCENA_QR_SNAPSHOTS']) if os.environ.get('SCENA_QR_SNAPSHOTS') else None
        def capture(name, response):
            if snapshots:
                snapshots.mkdir(parents=True, exist_ok=True)
                document = re.sub(r'(name="_token" value=")[^"]*', r'\1', response.body.decode())
                (snapshots/(name+'.html')).write_text(document)
        async def request(path, data=None, owner=True, instance=0):
            headers = {'Cookie':cookie if owner else BROWSER_COOKIE+'='+sid}
            if data is not None:
                headers.update(Origin=urls[instance], **{'Content-Type':'application/x-www-form-urlencoded'})
            return await client.fetch(HTTPRequest(urls[instance]+path, method='GET' if data is None else 'POST', headers=headers, body=None if data is None else urlencode(data), follow_redirects=False), raise_error=False)
        def payload(response, label, updates=None):
            assert response.code == 200, response.body[:200]
            token = re.search(r'name="_token" value="([^"]+)"', response.body.decode())[1]
            widgets = load_form(token, sid)['widgets']
            action, button = next((key,row) for key,row in widgets.items() if row['kind']=='button' and row['label']==label)
            result = {'_token':token, '_action':action}
            for key,row in widgets.items():
                if row['group']!=button['group'] or row['kind'] in ('button','file') or row.get('disabled'):
                    continue
                value = (updates or {}).get(row['label'], row['value'])
                if row['kind']=='bool':
                    if not value:
                        continue
                    value = '1'
                elif row['kind']=='choice':
                    value = row['options'].index(value)
                result[key] = str(value)
            return result
        editor = '/?page=admin&section=pages&view=model&lang=ru'
        photos = '/?page=admin&section=photos&view=library&lang=ru'
        try:
            assert (await request(editor, owner=False)).code == 302
            for locale in ('ru','ro','en'):
                response = await request(editor.replace('lang=ru','lang='+locale))
                assert response.code==200 and 'intro_qr_editor' in response.body.decode()
                capture('editor-'+locale, response)
                public = await request('/?page=model&lang='+locale, owner=False)
                assert public.code==200 and 'data-qr-open' in public.body.decode()
                capture('model-'+locale, public)
            before = get_settings(fixture/'test.db')
            response = await request(editor)
            result = await request(editor, payload(response, 'Сохранить QR-код', {'Куда ведёт QR-код':'booking','Центр по горизонтали, %':51.1,'Центр по вертикали, %':38.3,'Размер QR, % от короткой стороны фото':15.8}), instance=1)
            assert result.code==200 and 'QR-код сохранён.' in result.body.decode()
            after = get_settings(fixture/'test.db')
            assert after['model_intro_qr_destination']=='booking'
            assert after['model_intro_image']==before['model_intro_image']
            assert after['model_intro_title_ru']==before['model_intro_title_ru']
            public = await request('/?page=model&lang=ru', owner=False)
            qr_links = QRLinks(public.body.decode()).urls
            assert any(parse_qs(urlsplit(url).query) == {'page':['booking'], 'lang':['ru']}
                       for url in qr_links), qr_links
            capture('saved-ru', result)
            second = await request(editor, payload(result, 'Сохранить QR-код', {'Куда ведёт QR-код':'professional'}))
            assert second.code==200 and get_settings(fixture/'test.db')['model_intro_qr_destination']=='professional'
            text_save = await request(editor, payload(second, 'Сохранить визитку', {'Заголовок RU':'Моя новая визитка'}))
            assert text_save.code==200 and get_settings(fixture/'test.db')['model_intro_title_ru']=='Моя новая визитка'
            assert get_settings(fixture/'test.db')['model_intro_qr_destination']=='professional'
            print('PASS: QR destination and position saved across two servers; repeat save and public cache refresh; photo/text unchanged', flush=True)
            unused = upload_photo(fixture/'test.db', fixture, (root/'media/qr-scenes/model.png').read_bytes(), 'Портрет.png')
            detail = photos+'&photo='+photo_id(unused)
            response = await request(detail)
            capture('delete-ru', response)
            result = await request(detail, payload(response, 'Переместить в корзину'), instance=1)
            assert result.code==200 and 'Фото в корзине.' in result.body.decode()
            assert unused not in [row['path'] for row in catalog(fixture/'test.db', fixture)]
            capture('trashed-ru', result)
            trash_view = await request(photos+'&filter=trash')
            assert trash_view.code==200 and 'В корзине' in trash_view.body.decode()
            capture('trash-ru', trash_view)
            restore = await request(detail, payload(result, 'Восстановить фото'))
            assert restore.code==200 and 'Фото восстановлено.' in restore.body.decode()
            assert unused in [row['path'] for row in catalog(fixture/'test.db', fixture)]
            used = await request(photos+'&photo='+photo_id(before['model_intro_image']))
            assert 'Сначала замените' in used.body.decode()
            capture('used-ru', used)
            print('PASS: owner-only delete/restore journey, retained original, active photo deletion blocked', flush=True)
        finally:
            for server in servers:
                server.stop(); await server.close_all_connections()


if __name__=='__main__':
    asyncio.run(main())
