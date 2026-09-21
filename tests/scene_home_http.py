"""Editable service heading/introduction and compact public links on the homepage."""
import asyncio
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main():
    from tornado.httpclient import AsyncHTTPClient
    from tornado.httpserver import HTTPServer
    from tornado.testing import bind_unused_port

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as folder:
        shutil.copytree(root / 'media', Path(folder) / 'media')
        db = Path(folder) / 'test.db'
        os.environ.update(SCENA_NATIVE_WEB='1', SCENA_WEB_TESTING='1',
                          SCENA_DB_PATH=str(db), SCENA_APP_DIR=folder,
                          SCENA_ADMIN_PASSWORD='homepage-isolated-fixture')
        os.environ.pop('SCENA_CLOUD', None)
        from scena_web.bootstrap import initialize
        from scena_web.server import application
        from scena_web.mbstudio_migration import migrate
        from scena_core import save_settings

        initialize()
        save_settings(db, {'public_base_url': 'https://scena.life'})
        migrate(db, {'VERCEL': '1', 'VERCEL_ENV': 'production'})
        save_settings(db, {'shop_enabled': '1', 'model_published': '1',
                           'model_in_scene': '1', 'professional_published': '1',
                           'professional_in_scene': '1',
                           'instagram_url': 'https://www.instagram.com/example/'})
        introductions = {'ru': 'Макияж для ваших событий.\nВыберите услугу и время.',
                         'ro': 'Machiaj pentru evenimentele tale.\nAlege serviciul și ora.',
                         'en': 'Makeup for your occasions.\nChoose a service and time.'}
        titles = {'ru': 'Макияж и обучение', 'ro': 'Machiaj și instruire', 'en': 'Makeup and lessons'}
        save_settings(db, {**{'scene_services_text_'+lang: value for lang, value in introductions.items()},
                           **{'scene_services_title_'+lang: value for lang, value in titles.items()},
                           'booking_cta_ru': 'Изучить мои услуги'})
        socket, port = bind_unused_port()
        server = HTTPServer(application())
        server.add_socket(socket)
        client = AsyncHTTPClient()
        requests = 0

        async def home(locale='ru'):
            nonlocal requests
            response = await client.fetch(f'http://127.0.0.1:{port}/{locale}/')
            requests += 1
            assert response.code == 200
            return response.body.decode()

        def introduction(document):
            match = re.search(r'<div class="scene-service-intro"><p>(.*?)</p></div>', document, re.S)
            return match[1] if match else ''

        def secondary_links(document):
            match = re.search(r'<div class="scene-secondary-links">(.*?)</div>', document, re.S)
            return match[1] if match else ''

        try:
            for locale in ('ru', 'ro', 'en'):
                document = await home(locale)
                section = introduction(document)
                assert section and document.index(section) < document.index('class="scena-cta primary"')
                assert section == html.escape(introductions[locale])
                assert document.count('<h1 ') == 1
                brand = re.search(r'<a class="scena-logo scene-home-brand"([^>]+)>(.*?)</a>', document, re.S)
                assert brand and f'href="/{locale}/"' in brand[1]
                assert 'aria-label="MB Studio. SCENA.live"' in brand[1]
                assert 'class="scene-brand-logo"' in brand[2] and 'alt="SCENA.live"' in brand[2]
                assert 'class="scene-brand-initials">MB</span>' in brand[2] and '>Studio.</span>' in brand[2]
                name = html.unescape(re.search(r'<h1 class="scena-personal-name">(.*?)</h1>', document)[1])
                assert '<span class="scene-signature">' + html.escape(name.split(maxsplit=1)[0]) + '</span>' in document
                assert 'class="scene-manifesto"' in document
                heading = '<h2 id="scene-services-title" class="scene-section-title">' + html.escape(titles[locale]) + '</h2>'
                assert heading in document and document.index(heading) < document.index(section)
                links = secondary_links(document)
                assert f'href="/{locale}/model/"' in links
                assert document.index('class="scena-cta primary"') < document.index(links) < document.index('st-key-scene_publications')
                assert 'class="scene-model-link"' not in document

            document = await home()
            nav = re.search(r'<nav class="scena-nav">(.*?)</nav>', document, re.S)[1]
            labels = [html.unescape(re.sub(r'<[^>]+>', '', value)) for value in re.findall(r'<a\b[^>]*>(.*?)</a>', nav, re.S)]
            assert labels == ['Моя Сцена', 'Услуги и курсы', 'shopping', 'Портфолио', 'Model', 'Стать моделью'], labels
            assert '<span class="shopping-word">shopping</span>' in nav
            assert 'aria-current="page"' in nav
            assert 'href="/ru/zapis/"' in document
            assert '>Изучить мои услуги</a>' in document
            assert 'href="https://www.instagram.com/example/" target="_self"' in document
            links = re.findall(r'<a class="scene-social-link[^\"]*"[^>]*>(.*?)</a>', secondary_links(document), re.S)
            assert len(links) == 2
            assert '<span>model</span>' in links[0] and '<span>SCENA</span>' in links[0]
            crown_url = re.search(r'<img src="([^"]+)"', links[0])[1]
            crown = await client.fetch(f'http://127.0.0.1:{port}' + crown_url)
            requests += 1
            from scena_web.media import assets
            assert crown_url == assets()['scena_web/static/model-crown.svg']
            assert crown.code == 200 and crown.body == (root / 'public' / crown_url.lstrip('/')).read_bytes()
            for name in ('cormorant-regular', 'cormorant-italic', 'manrope-regular', 'manrope-medium', 'marck-script'):
                font_url = assets()['scena_web/static/' + name + '.woff2']
                assert font_url in document
                font = await client.fetch(f'http://127.0.0.1:{port}' + font_url)
                requests += 1
                assert font.code == 200 and font.body[:4] == b'wOF2'
                assert font.body == (root / 'public' / font_url.lstrip('/')).read_bytes()
            assert '<svg ' in links[1] and '<span>Instagram</span>' in links[1]
            save_settings(db, {'scene_services_text_ru': 'Makeup <script> & "test"',
                               'scene_services_title_ru': 'Lessons <script> & "test"'})
            document = await home()
            escaped = introduction(document)
            assert 'Makeup &lt;script&gt; &amp; &quot;test&quot;' in escaped and '<script>' not in escaped
            assert '>Lessons &lt;script&gt; &amp; &quot;test&quot;</h2>' in document

            for flag in ('professional_published', 'professional_in_scene'):
                save_settings(db, {flag: '0'})
                hidden = await home()
                assert not introduction(hidden) and 'class="scena-cta primary"' not in hidden
                assert 'id="scene-services-title"' not in hidden
                save_settings(db, {flag: '1'})
            for flag in ('model_published', 'model_in_scene'):
                save_settings(db, {flag: '0'})
                assert '<span>SCENA</span>' not in secondary_links(await home())
                save_settings(db, {flag: '1'})
            save_settings(db, {'scene_services_text_'+lang: '' for lang in ('ru', 'ro', 'en')})
            document = await home()
            assert not introduction(document) and 'id="scene-services-title"' in document
            save_settings(db, {'scene_services_title_'+lang: '' for lang in ('ru', 'ro', 'en')})
            document = await home()
            assert 'id="scene-services-title"' not in document and '>Изучить мои услуги</a>' in document
            print(json.dumps({'result': 'PASS', 'http_requests': requests,
                              'checks': 'RU/RO/EN owner heading and introduction; branded homepage link, crown and self-hosted fonts; localized signature; custom CTA preserves booking URL; model SCENA and Instagram below CTA; visibility; empty and escaped owner content'}))
        finally:
            server.stop()
            await server.close_all_connections()


if __name__ == '__main__':
    asyncio.run(main())
