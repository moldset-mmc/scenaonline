"""Run separately: real native HTTP, isolated data, owner-only originals."""
import asyncio
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main():
    from PIL import Image
    from tornado.httpclient import AsyncHTTPClient, HTTPRequest
    from tornado.httpserver import HTTPServer
    from tornado.testing import bind_unused_port
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as folder:
        fixture = Path(folder)
        shutil.copytree(root / 'media', fixture / 'media')
        os.environ.update(SCENA_NATIVE_WEB='1', SCENA_WEB_TESTING='1', SCENA_DB_PATH=str(fixture / 'test.db'), SCENA_APP_DIR=str(fixture), SCENA_ADMIN_PASSWORD='isolated-photo-fixture')
        os.environ.pop('SCENA_CLOUD', None)
        from scena_web.server import application, BROWSER_COOKIE
        from scena_web.bootstrap import initialize
        from scena_cloud_auth import COOKIE, make_session
        from scena_web.storage import load_form
        from scena_core import get_settings, save_settings
        from scena_photo_library import upload_photo, photo_id, targets
        await asyncio.to_thread(initialize)
        servers, urls = [], []
        for _ in range(2):
            sock, port = bind_unused_port()
            server = HTTPServer(application())
            server.add_socket(sock)
            servers.append(server)
            urls.append('http://127.0.0.1:' + str(port))
        client = AsyncHTTPClient()
        sid = 'photo-fixture-browser-' + 'a' * 30
        cookie = COOKIE + '=' + make_session() + '; ' + BROWSER_COOKIE + '=' + sid
        route = '/?page=admin&section=photos&view=library&lang=ru'
        def make_photo(color):
            output = io.BytesIO()
            Image.new('RGB', (800, 1100), color).save(output, 'PNG')
            return output.getvalue()
        first_bytes, second_bytes = make_photo('navy'), make_photo('maroon')
        first = upload_photo(fixture / 'test.db', fixture, first_bytes, 'Портрет.png')
        second = upload_photo(fixture / 'test.db', fixture, second_bytes, 'Второй портрет.png')
        snapshots = Path(os.environ['SCENA_PHOTO_SNAPSHOTS']) if os.environ.get('SCENA_PHOTO_SNAPSHOTS') else None
        def capture(name, response):
            if snapshots:
                snapshots.mkdir(exist_ok=True, parents=True)
                # A preview contains no reusable form credentials, even test ones.
                document = re.sub(r'(name="_token" value=")[^"]*', r'\1', response.body.decode())
                (snapshots / (name + '.html')).write_text(document)
        async def request(path, *, owner=True, data=None, instance=0, raw=None, headers=None):
            h = {'Cookie': cookie if owner else BROWSER_COOKIE + '=' + sid, **(headers or {})}
            body = raw if raw is not None else urlencode(data, doseq=True) if data is not None else None
            if body is not None:
                h['Origin'] = urls[instance]
                h.setdefault('Content-Type', 'application/x-www-form-urlencoded')
            return await client.fetch(HTTPRequest(urls[instance] + path, method='POST' if body is not None else 'GET', headers=h, body=body, follow_redirects=False, request_timeout=40), raise_error=False)
        def saved_form(response):
            assert response.code == 200, (response.code, response.body.decode()[:400])
            token = re.search(r'name="_token" value="([^"]+)"', response.body.decode())[1]
            return token, load_form(token, sid)
        def payload(response, label):
            token, saved = saved_form(response)
            action, button = next((key, widget) for key, widget in saved['widgets'].items() if widget['kind'] == 'button' and widget['label'] == label)
            result = {'_token': token, '_action': action}
            for identity, widget in saved['widgets'].items():
                if widget['group'] != button['group'] or widget.get('disabled') or widget['kind'] in ('button', 'file'):
                    continue
                value = widget['value']
                if widget['kind'] == 'bool':
                    if value:
                        result[identity] = '1'
                elif widget['kind'] == 'choice':
                    result[identity] = str(widget['options'].index(value))
                else:
                    result[identity] = str(value)
            return result
        try:
            assert (await request(route, owner=False)).code == 302
            assert (await request('/scena-photo/' + photo_id(first), owner=False)).code == 401
            response = await request('/scena-photo/' + photo_id(first))
            assert response.code == 200 and response.body == first_bytes
            assert 'no-store' in response.headers['Cache-Control']
            assert (await request('/scena-photo/' + '0' * 64)).code == 404
            for locale in ('ru', 'ro', 'en'):
                local_route = route.replace('lang=ru', 'lang=' + locale)
                response = await request(local_route)
                assert response.code == 200 and 'scena-photo-grid' in response.body.decode()
                assert response.body.decode().count('class="scena-photo-card"') <= 12
                capture('gallery-' + locale, response)
                for suffix, name in (('&photo=' + photo_id(first), 'photo'), ('&mode=upload', 'upload')):
                    response = await request(local_route + suffix)
                    assert response.code == 200
                    capture(name + '-' + locale, response)
                if snapshots:
                    from scena_photo_library import catalog
                    response = await request(local_route + '&photo=' + photo_id('media/model-slider/01-black-halo.webp') + '&target=avatar_url')
                    assert response.code == 200
                    capture('assign-' + locale, response)
                    for row in catalog(fixture / 'test.db', fixture, locale)[:12]:
                        response = await request(local_route + '&photo=' + row['id'])
                        assert response.code == 200
                        capture('detail-' + row['id'] + '-' + locale, response)
                    for group in ('scene', 'professional', 'model', 'shop', 'posts', 'saved'):
                        response = await request(local_route + '&filter=' + group)
                        assert response.code == 200
                        capture('filter-' + group + '-' + locale, response)
            # Assign through one replica, consume/save the form on the other.
            target_route = route + '&photo=' + photo_id(first) + '&target=avatar_url'
            response = await request(target_route)
            result = await request(target_route, data=payload(response, 'Использовать здесь'), instance=1)
            assert result.code == 200, result.body.decode()[:500]
            assert get_settings(fixture / 'test.db')['avatar_url'] == first
            capture('saved-ru', result)
            # A newer cabinet edit wins over this older form.
            stale_route = route + '&photo=' + photo_id(second) + '&target=avatar_url'
            response = await request(stale_route)
            newer = 'media/scena-v13/my-scena-hero.webp'
            save_settings(fixture / 'test.db', {'avatar_url': newer})
            stale = await request(stale_route, data=payload(response, 'Использовать здесь'), instance=1)
            assert stale.code == 200 and 'уже изменилось' in stale.body.decode()
            assert get_settings(fixture / 'test.db')['avatar_url'] == newer
            # Actual upload chunks and form submission, no in-process shortcut.
            upload_route = route + '&mode=upload'
            response = await request(upload_route)
            token, saved = saved_form(response)
            field = next(key for key, widget in saved['widgets'].items() if widget['kind'] == 'file')
            third_bytes = make_photo('green')
            chunk = await request('/scena-upload', raw=third_bytes, headers={'X-Scena-Form': token, 'X-Scena-Field': field, 'Content-Type': 'application/octet-stream'})
            assert chunk.code == 200
            body = payload(response, 'Сохранить фото')
            body['_upload_' + field] = json.dumps([{'refs': [json.loads(chunk.body)['id']], 'size': len(third_bytes), 'name': 'Третье фото.png', 'mime': 'image/png'}])
            result = await request(upload_route, data=body, instance=1)
            assert result.code == 200 and 'Фото сохранено' in result.body.decode()
            identifier = re.search(r'href="/scena-photo/([a-f0-9]{64})"', result.body.decode())[1]
            assert (await request('/scena-photo/' + identifier, instance=1)).body == third_bytes
            assert (await request(upload_route, data=body, instance=1)).code == 409
            print('PHOTO_HTTP_PASS: owner authorization, exact originals, 3 locales, 12-card pages, two-replica assignment, stale forms, chunk upload, duplicate submission')
        finally:
            for server in servers:
                server.stop()
                await server.close_all_connections()


if __name__ == '__main__':
    asyncio.run(main())
