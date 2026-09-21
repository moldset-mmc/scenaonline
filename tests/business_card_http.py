"""Native owner form: preview/save, anonymous and cross-origin rejection, uploads."""
import asyncio
import html
import io
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main():
    from PIL import Image
    from tornado.httpclient import AsyncHTTPClient, HTTPRequest
    from tornado.httpserver import HTTPServer
    from tornado.testing import bind_unused_port

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        database = root / 'test.db'
        os.environ.update(SCENA_NATIVE_WEB='1', SCENA_WEB_TESTING='1', SCENA_DB_PATH=str(database),
                          SCENA_APP_DIR=folder, SCENA_ADMIN_PASSWORD='isolated-card-fixture')
        os.environ.pop('SCENA_CLOUD', None)
        from scena_web.server import application, BROWSER_COOKIE
        from scena_web.bootstrap import initialize
        from scena_cloud_auth import COOKIE, make_session
        from scena_web.storage import load_form
        from scena_business_card import get_card, DEFAULT_CARD
        from scena_core import get_settings, save_settings
        await asyncio.to_thread(initialize)
        save_settings(database, {'public_base_url': 'https://mbstudio.scena.life'})
        servers, urls = [], []
        for _ in range(2):
            sock, port = bind_unused_port()
            server = HTTPServer(application())
            server.add_socket(sock)
            servers.append(server)
            urls.append('http://127.0.0.1:' + str(port))
        client = AsyncHTTPClient()
        sid = 'card-fixture-' + 'a' * 32
        cookie = COOKIE + '=' + make_session() + '; ' + BROWSER_COOKIE + '=' + sid
        snapshots = Path(os.environ['SCENA_CARD_SNAPSHOTS']) if os.environ.get('SCENA_CARD_SNAPSHOTS') else None
        def capture(name, response):
            if snapshots:
                snapshots.mkdir(parents=True, exist_ok=True)
                text = re.sub(r'(name="_token" value=")[^"]*', r'\1', response.body.decode())
                (snapshots / (name + '.html')).write_text(text)
        async def request(path, data=None, *, owner=True, instance=0, origin=None, upload=None):
            headers = {'Cookie': cookie if owner else BROWSER_COOKIE + '=' + sid}
            body = None
            if data is not None:
                headers['Origin'] = origin or urls[instance]
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                body = urlencode(data)
            if upload:
                boundary = 'card-fixture-boundary'
                chunks = []
                for key, value in data.items():
                    chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n').encode())
                chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{upload[0]}"; filename="portrait.png"\r\nContent-Type: image/png\r\n\r\n').encode() + upload[1] + b'\r\n')
                chunks.append((f'--{boundary}--\r\n').encode())
                body = b''.join(chunks)
                headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
            return await client.fetch(HTTPRequest(urls[instance] + path, method='GET' if data is None else 'POST',
                headers=headers, body=body, follow_redirects=False), raise_error=False)
        def payload(response, label, updates=None):
            assert response.code == 200, response.body[:300]
            token = re.search(r'name="_token" value="([^"]+)"', response.body.decode())[1]
            widgets = load_form(token, sid)['widgets']
            action, button = next((key, row) for key, row in widgets.items() if row['kind'] == 'button' and row['label'] == label)
            result = {'_token': token, '_action': action}
            for key, row in widgets.items():
                if row['group'] != button['group'] or row['kind'] in ('button', 'file') or row.get('disabled'):
                    continue
                value = (updates or {}).get(row['label'], row['value'])
                if row['kind'] == 'choice':
                    value = row['options'].index(value)
                result[key] = str(value)
            return result, widgets
        editor = '/?page=admin&section=pages&view=card&lang=ru'
        try:
            assert (await request(editor, owner=False)).code == 302
            for locale in ('ru', 'ro', 'en'):
                response = await request(editor.replace('lang=ru', 'lang=' + locale))
                assert response.code == 200
                assert 'business_card_editor' in response.body.decode()
                capture('editor-' + locale, response)
            before = get_settings(database)
            response = await request(editor)
            data, _ = payload(response, 'Обновить предпросмотр', {'Имя': 'Анна', 'Фамилия': 'Тестовая'})
            preview = await request(editor, data, instance=1)
            assert preview.code == 200 and 'Анна' in html.unescape(preview.body.decode())
            assert get_card(database) == DEFAULT_CARD
            assert 'Анна' not in (await request('/card/', owner=False)).body.decode()
            print('PASS draft preview is independent of public card', flush=True)
            # A valid owner form cannot be used anonymously or from another origin.
            data, _ = payload(preview, 'Сохранить визитку')
            assert (await request(editor, data, owner=False)).code == 401
            assert (await request(editor, data, origin='https://untrusted.example')).code == 403
            assert get_card(database) == DEFAULT_CARD
            saved = await request(editor, data, instance=1)
            assert saved.code == 200 and 'Визитка сохранена.' in saved.body.decode()
            assert get_card(database)['first_name'] == 'Анна'
            assert get_settings(database) == before
            for path in ('/card/', '/card/index.html', '/card/mbstudio.vcf'):
                public = await request(path, owner=False)
                assert public.code == 200 and 'Анна' in public.body.decode()
            print('PASS real owner save reaches page/vCard across instances; main profile unchanged', flush=True)
            fresh = await request(editor)
            assert 'value="Анна"' in fresh.body.decode()
            stale = await request(editor)
            data, _ = payload(fresh, 'Сохранить визитку', {'Имя': 'Елена'})
            assert (await request(editor, data)).code == 200
            data, _ = payload(stale, 'Сохранить визитку', {'Имя': 'Старая вкладка'})
            refused = await request(editor, data)
            assert 'другом окне' in refused.body.decode()
            assert get_card(database)['first_name'] == 'Елена'
            print('PASS stale tab cannot overwrite newer data', flush=True)
            fresh = await request(editor)
            data, _ = payload(fresh, 'Сохранить визитку', {'Сайт': 'javascript:alert(1)'})
            invalid = await request(editor, data)
            assert 'https://' in invalid.body.decode()
            assert get_card(database)['site_url'] == DEFAULT_CARD['site_url']
            data, _ = payload(invalid, 'Сохранить визитку', {'Сайт': DEFAULT_CARD['site_url']})
            corrected = await request(editor, data)
            assert 'Визитка сохранена.' in corrected.body.decode()
            # Exercise the same multipart upload field used by the cabinet.
            output = io.BytesIO()
            Image.new('RGB', (500, 700), 'navy').save(output, 'PNG')
            data, widgets = payload(corrected, 'Обновить предпросмотр')
            field = next(key for key, row in widgets.items() if row['kind'] == 'file')
            photo_preview = await request(editor, data, upload=(field, output.getvalue()))
            assert 'data:image/webp;base64,' in html.unescape(photo_preview.body.decode())
            assert get_card(database)['photo'] == ''
            data, _ = payload(photo_preview, 'Сохранить визитку')
            photo_saved = await request(editor, data)
            assert 'Визитка сохранена.' in photo_saved.body.decode()
            assert get_card(database)['photo'].startswith('media/business-card/')
            image = await request('/card/portrait.webp', owner=False)
            assert image.code == 200 and image.headers['Content-Type'] == 'image/webp'
            assert get_settings(database) == before
            print('PASS invalid values are recoverable; photo preview then save persists and serves a rendition', flush=True)
            capture('saved-editor', photo_saved)
        finally:
            for server in servers:
                server.stop()
                await server.close_all_connections()


if __name__ == '__main__':
    asyncio.run(main())
