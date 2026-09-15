"""Real local HTTP SEO acceptance; isolated data, no browser or external writes."""
import asyncio
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import parse_qs, urlencode, urlsplit
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Document(HTMLParser):
    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.head = False
        self.tag = ''
        self.titles, self.metas, self.links, self.json_ld = [], [], [], []
        self.visible, self.anchors = [], []
        self.language = ''
        self.iframe_count = 0
        self.script_type = ''
        self.script = ''
        self.ignored = 0
        self.anchor = None
        self.feed(value)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tag = tag
        if tag == 'html': self.language = a.get('lang', '')
        if tag == 'head': self.head = True
        if tag == 'iframe': self.iframe_count += 1
        if tag == 'script':
            self.script_type, self.script = a.get('type', ''), ''
        if tag in ('script', 'style'): self.ignored += 1
        if self.head and tag == 'title': self.titles.append('')
        if self.head and tag == 'meta': self.metas.append(a)
        if self.head and tag == 'link': self.links.append(a)
        if tag == 'a': self.anchor = {'href': a.get('href', ''), 'target': a.get('target', ''), 'qr': 'data-qr-link' in a, 'text': ''}

    def handle_data(self, data):
        if self.tag == 'title' and self.head: self.titles[-1] += data
        if self.script_type == 'application/ld+json': self.script += data
        if not self.head and not self.ignored: self.visible.append(data)
        if self.anchor and not self.ignored: self.anchor['text'] += data

    def handle_endtag(self, tag):
        if tag == 'script':
            if self.script_type == 'application/ld+json': self.json_ld.append(json.loads(self.script))
            self.script_type, self.script = '', ''
        if tag in ('script', 'style'): self.ignored = max(0, self.ignored - 1)
        if tag == 'head': self.head = False
        if tag == 'a' and self.anchor:
            self.anchors.append(self.anchor); self.anchor = None
        self.tag = ''

    def named(self, key):
        return [item.get('content', '') for item in self.metas if item.get('name') == key]

    def canonical(self):
        return [item.get('href', '') for item in self.links if item.get('rel') == 'canonical']

    def alternates(self):
        return {item['hreflang']: item['href'] for item in self.links if item.get('rel') == 'alternate' and 'hreflang' in item}


async def main():
    from tornado.httpclient import AsyncHTTPClient, HTTPRequest
    from tornado.httpserver import HTTPServer
    from tornado.testing import bind_unused_port
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as folder:
        fixture = Path(folder)
        shutil.copytree(root / 'media', fixture / 'media')
        db = fixture / 'test.db'
        os.environ.update(SCENA_NATIVE_WEB='1', SCENA_WEB_TESTING='1', SCENA_DB_PATH=str(db),
                          SCENA_APP_DIR=folder, SCENA_ADMIN_PASSWORD='isolated-seo-fixture')
        os.environ.pop('SCENA_CLOUD', None)
        from scena_web.server import application, BROWSER_COOKIE
        from scena_web.bootstrap import initialize
        from scena_cloud_auth import COOKIE, make_session
        from scena_core import get_settings, save_settings
        from scena_web.storage import load_form
        from scena_publications import save_draft, publish_local, archive_publication
        from scena_seo import build_metadata, public_catalog, INDEX, NOINDEX
        await asyncio.to_thread(initialize)
        save_settings(db, {'public_base_url': 'https://scenaonline.vercel.app',
                           'master_name_ru': 'Тестовая владелица', 'master_name_ro': 'Proprietară de test',
                           'master_name_en': 'Test owner', 'location': 'Кишинёв',
                           'location_ro': 'Chișinău', 'location_en': 'Chișinău',
                           'bio': 'Публичная история для проверки.', 'bio_ro': 'Poveste publică de test.',
                           'bio_en': 'Public test story.', 'seo_google_verification': 'GSC_FIXTURE_SAFE_TOKEN',
                           'seo_bing_verification': '0123456789ABCDEF0123456789ABCDEF'})
        post = save_draft(db, title_ru='Тестовая публикация RU', title_ro='Publicație de test RO',
                          title_en='Test publication EN', body_ru='Публичный текст без черновика.',
                          body_ro='Text public fără ciornă.', body_en='Published text without draft.',
                          show_scene=True, translations_approved=True)
        publish_local(db, post['id'], post['revision'])
        save_draft(db, post['id'], body_ru='SECRET DRAFT MUST NEVER BE EXPOSED')
        draft = save_draft(db, body_ru='SECRET UNPUBLISHED POST')
        archived = save_draft(db, body_ru='ARCHIVED BODY SECRET', body_ro='Text arhivat', translations_approved=True)
        publish_local(db, archived['id'], archived['revision']); archive_publication(db, archived['id'])
        servers, urls = [], []
        for _ in range(2):
            sock, port = bind_unused_port()
            server = HTTPServer(application()); server.add_socket(sock)
            servers.append(server); urls.append('http://127.0.0.1:' + str(port))
        client = AsyncHTTPClient()
        sid = 'seo-fixture-' + 'a' * 32
        cookie = COOKIE + '=' + make_session() + '; ' + BROWSER_COOKIE + '=' + sid
        snapshots = Path(os.environ['SCENA_SEO_SNAPSHOTS']) if os.environ.get('SCENA_SEO_SNAPSHOTS') else None
        report, failures, captured = [], [], []
        if snapshots: snapshots.mkdir(parents=True, exist_ok=True)

        def check(condition, message):
            if not condition: failures.append(message)

        def capture(name, response):
            if snapshots:
                content = re.sub(r'(name="_token" value=")[^"]*', r'\1', response.body.decode())
                suffix = '.html' if 'text/html' in response.headers.get('Content-Type', '') else '.xml' if 'xml' in response.headers.get('Content-Type', '') else '.txt'
                (snapshots / (name + suffix)).write_text(content)
                captured.append(name + suffix)

        async def request(path, *, owner=False, instance=0, headers=None, method='GET', data=None):
            request_headers = {'Cookie': cookie if owner else BROWSER_COOKIE + '=' + sid,
                               'Host': 'scenaonline.vercel.app', **(headers or {})}
            if data is not None:
                method = 'POST'
                request_headers.update(Origin='http://' + request_headers['Host'],
                                       **{'Content-Type':'application/x-www-form-urlencoded'})
            response = await client.fetch(HTTPRequest(urls[instance] + path, method=method,
                headers=request_headers, body=urlencode(data, doseq=True) if data is not None else None,
                follow_redirects=False, request_timeout=45), raise_error=False)
            report.append({'path': path, 'method': method, 'status': response.code, 'bytes': len(response.body),
                           'robots': response.headers.get('X-Robots-Tag', ''),
                           'cache': response.headers.get('X-Scena-Page-Cache', '')})
            return response

        try:
            settings = get_settings(db)
            catalog = public_catalog(settings, db_path=db)
            check({item['page'] for item in catalog} == {'scene', 'professional', 'model', 'portfolio', 'booking',
                  'course', 'join-model', 'invite-model', 'posts', 'post', 'shop'}, 'Catalog covers all eleven public routes')
            print('CATALOG', len(catalog), 'localized public URLs', flush=True)
            for i, expected in enumerate(catalog):
                url = urlsplit(expected['canonical'])
                path = url.path + '?' + url.query
                response = await request(path, instance=i % 2)
                name = expected['page'] + '-' + '-'.join(expected['params'].values()) + '-' + expected['locale']
                capture(name.strip('-'), response)
                check(response.code == 200, path + ': HTTP 200')
                doc = Document(response.body.decode())
                check(doc.language == expected['locale'], path + ': html lang matches')
                check(doc.titles == [expected['title']], path + ': exactly one matching title')
                check(doc.canonical() == [expected['canonical']], path + ': exactly one self canonical')
                check(doc.alternates() == expected['alternates'], path + ': reciprocal hreflang')
                check(doc.named('robots') == [INDEX], path + ': one indexable robots meta')
                check(response.headers.get('X-Robots-Tag') == INDEX, path + ': indexable HTTP policy matches')
                check(doc.named('description') == [expected['description']], path + ': localized description')
                if expected['page'] == 'scene':
                    check(doc.named('google-site-verification') == ['GSC_FIXTURE_SAFE_TOKEN'], path + ': Google verification on localized home')
                    check(doc.named('msvalidate.01') == ['0123456789ABCDEF0123456789ABCDEF'], path + ': Bing verification on localized home')
                else:
                    check(not doc.named('google-site-verification') and not doc.named('msvalidate.01'), path + ': verification is confined to home')
                check(len(doc.json_ld) == 1 and bool(doc.json_ld[0].get('@graph')), path + ': one JSON-LD graph')
                check(not re.search(r'SECRET DRAFT|SECRET UNPUBLISHED|ARCHIVED BODY SECRET', response.body.decode()), path + ': private publication text excluded')
                language_links = {item['text'].strip().lower(): item['href'] for item in doc.anchors if item['text'].strip() in ('RU', 'RO', 'EN')}
                for lang in ('ru', 'ro', 'en'):
                    check(lang in language_links, path + ': visible language link ' + lang)
                    if lang in language_links:
                        target = parse_qs(urlsplit(language_links[lang]).query)
                        check(target.get('page') == [expected['page']] and target.get('lang') == [lang], path + ': language keeps page')
                        for key, value in expected['params'].items():
                            check(target.get(key) == [value], path + ': language keeps ' + key)
                if expected['page'] == 'model':
                    check(doc.iframe_count == 0, path + ': Model rendered directly without iframe')
                    visible = ' '.join(doc.visible)
                    check(settings['model_intro_text_' + expected['locale']] in visible, path + ': visible model introduction in main HTML')
                    check('data-qr-open' in response.body.decode(), path + ': interactive QR markup retained')
                    internal = [link for link in doc.anchors if parse_qs(urlsplit(link['href']).query).get('page') in (['scene'], ['portfolio'], ['invite-model'], ['model'])]
                    # The separately labelled QR destination may intentionally open a new tab.
                    navigation = [link for link in internal if not link['qr']]
                    check(len(navigation) >= 7 and all(link['target'] == '_self' for link in navigation), path + ': standalone Model navigation stays in the current tab')
            print('CHECKED localized head/body/links/JSON-LD on', len(catalog), 'URLs', flush=True)
            sitemap = await request('/sitemap.xml')
            capture('sitemap', sitemap)
            check(sitemap.code == 200 and 'xml' in sitemap.headers.get('Content-Type', ''), 'Sitemap XML response')
            tree = ET.fromstring(sitemap.body)
            ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9', 'h': 'http://www.w3.org/1999/xhtml'}
            locs = [node.find('s:loc', ns).text for node in tree]
            check(set(locs) == {row['canonical'] for row in catalog} and len(locs) == len(set(locs)), 'Sitemap exact catalog, no duplicates')
            for node in tree:
                loc = node.find('s:loc', ns).text
                langs = {tag.attrib['hreflang']: tag.attrib['href'] for tag in node.findall('h:link', ns)}
                check(langs == next(row['alternates'] for row in catalog if row['canonical'] == loc), 'Sitemap alternates match head')
            for path in ('/robots.txt', '/llms.txt'):
                response = await request(path); capture(path[1:].split('.')[0], response)
                check(response.code == 200 and 'text/plain' in response.headers.get('Content-Type', ''), path + ': text response')
                text = response.body.decode()
                check('SECRET' not in text, path + ': private data absent')
                if path == '/robots.txt':
                    for directive in ('User-agent: *', 'Allow: /', 'Disallow: /auth/login', 'Disallow: /scena-download/', 'Sitemap: https://scenaonline.vercel.app/sitemap.xml'):
                        check(directive in text, 'Robots actual policy: ' + directive)
                else:
                    check(all(url in text for url in locs), 'llms directory contains every public canonical')
            for path in ('/?page=unknown&lang=en', '/missing-resource', '/?page=post&post=missing&lang=ro',
                         '/?page=course&service=missing', '/?page=post&post=' + draft['public_id'],
                         '/?page=post&post=' + archived['public_id']):
                response = await request(path)
                check(response.code == 404, path + ': true404')
                check(response.headers.get('X-Robots-Tag') == NOINDEX, path + ':404 noindex')
                check(response.headers.get('X-Scena-Page-Cache') != 'HIT', path + ':404 not cached')
            for path in ('/?page=admin&lang=ru', '/?admin=1'):
                response = await request(path)
                check(response.code == 302 and response.headers.get('Location', '').startswith('/auth/login?'), path + ': owner auth redirect')
                check(response.headers.get('X-Robots-Tag') == NOINDEX, path + ': auth redirect noindex')
            for path in ('/auth/login', '/healthz'):
                response = await request(path)
                check(response.code == 200 and response.headers.get('X-Robots-Tag') == NOINDEX, path + ': nonsearchable private/operational page')
            response = await request('/scena-photo/' + 'a' * 64)
            check(response.code in (401, 404) and response.headers.get('X-Robots-Tag') == NOINDEX, 'Photo original requires auth and noindex')
            response = await request('/?page=admin&lang=ru&section=photos&view=library', owner=True)
            check(response.code == 200 and response.headers.get('X-Robots-Tag') == NOINDEX, 'Owner cabinet200 noindex')
            print('CHECKED discovery endpoints, 404/private/auth restrictions', flush=True)
            # HEAD follows the same route/canonical variant and response policy as GET.
            for path in ('/?page=scene&lang=ro', '/?page=model&lang=en', '/robots.txt', '/sitemap.xml', '/llms.txt'):
                get = await request(path)
                head = await request(path, method='HEAD', instance=1)
                check(head.code == get.code == 200 and head.body == b'', path + ': HEAD200 with empty body')
                check(head.headers.get('X-Robots-Tag') == get.headers.get('X-Robots-Tag'), path + ': HEAD and GET robot policy match')
                check(head.headers.get('Content-Type') == get.headers.get('Content-Type'), path + ': HEAD content type matches GET')
                # The client decompresses GET bodies; Content-Length describes
                # the transferred (possibly gzip) representation on both methods.
                check(head.headers.get('Content-Length') == get.headers.get('Content-Length'), path + ': HEAD length matches GET representation')
                if path.startswith('/?'):
                    canonical = Document(get.body.decode()).canonical()[0]
                    check(parse_qs(urlsplit(head.headers.get('X-Scena-URL', '')).query) == parse_qs(urlsplit(canonical).query), path + ': HEAD preserves canonical route and locale')
            # Empty course form is rejected in the product, but its submitted
            # contacts/form state must still never become indexable or cached.
            course = next(row for row in catalog if row['page'] == 'course' and row['locale'] == 'ru')
            path = '/?' + urlsplit(course['canonical']).query
            form = await request(path)
            token = re.search(r'name="_token" value="([^"]+)"', form.body.decode())[1]
            widgets = load_form(token, sid)['widgets']
            action, button = next((key, row) for key, row in widgets.items() if row['kind'] == 'button' and row['label'] == 'Предварительно записаться')
            payload = {'_token':token, '_action':action}
            for key, row in widgets.items():
                if row['group'] != button['group'] or row['kind'] in ('button','file') or row.get('disabled'):
                    continue
                value = 'PRIVATE FORM NAME' if row['label'] == 'Ваше имя *' else row['value']
                if row['kind'] == 'bool':
                    if value: payload[key] = '1'
                elif row['kind'] == 'choice':
                    payload[key] = str(row['options'].index(value)) if value in row['options'] else ''
                else:
                    payload[key] = str(value or '')
            submitted = await request(path, data=payload, instance=1)
            check(submitted.code == 200, 'Validation form POST remains usable')
            posted = Document(submitted.body.decode())
            check('PRIVATE FORM NAME' in submitted.body.decode() and not any('PRIVATE FORM NAME' in value for value in posted.titles + posted.named('description')),
                  'Private submitted form value stays outside search metadata')
            check(posted.named('robots') == [NOINDEX] and submitted.headers.get('X-Robots-Tag') == NOINDEX,
                  'Form POST response is noindex in HTML and HTTP')
            check(not posted.alternates() and not posted.json_ld and 'X-Scena-Page-Cache' not in submitted.headers,
                  'Form POST response has no index metadata and no shared cache')
            # Saving malformed verification values cannot inject markup, even if
            # a caller bypasses the validated settings form.
            poison = '\"/><script>alert(\"verification\")</script>'
            save_settings(db, {'seo_google_verification':poison, 'seo_bing_verification':poison})
            poisoned = await request('/?page=scene&lang=ru')
            parsed = Document(poisoned.body.decode())
            check(not parsed.named('google-site-verification') and not parsed.named('msvalidate.01'),
                  'Malformed verification tokens are omitted')
            check('<script>alert(' not in poisoned.body.decode() and len(parsed.titles) == 1,
                  'Verification values cannot inject HTML')
            save_settings(db, {'seo_google_verification':'GSC_FIXTURE_SAFE_TOKEN',
                               'seo_bing_verification':'0123456789ABCDEF0123456789ABCDEF'})
            print('CHECKED HEAD, verification tokens, same-tab Model links and private POST policy', flush=True)
            await request('/?page=scene&lang=ru')
            cached = await request('/?page=scene&lang=ru', instance=1)
            check(cached.headers.get('X-Scena-Page-Cache') == 'HIT', 'Second server receives shared cache HIT')
            check(cached.headers.get('X-Robots-Tag') == INDEX and Document(cached.body.decode()).named('robots') == [INDEX], 'Cache HIT retains matching metadata policy')
            # Two domains can share the same DB cache. A preview must not inherit
            # indexability from a canonical-host cached page.
            os.environ['SCENA_WEB_TESTING'] = '0'
            preview = await request('/?page=scene&lang=ru', headers={'Host': 'preview.example.invalid'})
            check(preview.headers.get('X-Robots-Tag') == NOINDEX and Document(preview.body.decode()).named('robots') == [NOINDEX], 'Preview host remains noindex on a warmed canonical cache')
            os.environ['SCENA_WEB_TESTING'] = '1'
            for area, page in (('profile', 'scene'), ('professional', 'professional'), ('model', 'model')):
                save_settings(db, {area + '_indexed': '0'})
                path = '/?page=' + page + '&lang=ru'
                first = await request(path); second = await request(path, instance=1)
                check(second.headers.get('X-Scena-Page-Cache') == 'HIT', area + ': noindex cache shared across replicas')
                for response in (first, second):
                    check(response.code == 200, area + ': disabling indexing preserves public200')
                    check(response.headers.get('X-Robots-Tag') == NOINDEX, area + ': noindex HTTP after invalidation and cache')
                    doc = Document(response.body.decode())
                    check(doc.named('robots') == [NOINDEX] and not doc.alternates() and not doc.json_ld, area + ': noindex head and no discovery metadata')
                save_settings(db, {area + '_indexed': '1'})
                restored = await request(path)
                check(restored.headers.get('X-Robots-Tag') == INDEX, area + ': restored indexing invalidates cached noindex')
                save_settings(db, {area + '_published': '0'})
                hidden = await request(path)
                check(hidden.code == 404 and hidden.headers.get('X-Robots-Tag') == NOINDEX, area + ': hidden page404 noindex')
                save_settings(db, {area + '_published': '1'})
            # An unavailable optional HTML cache must not make a healthy
            # application page fail or change its indexing policy.
            from unittest.mock import patch
            import sqlite3
            from scena_web import page_cache
            save_settings(db, {'bio':'Обновлённая публичная история для проверки.'})
            with patch.object(page_cache, 'save', side_effect=sqlite3.DatabaseError('fixture cache write unavailable')):
                fallback = await request('/?page=scene&lang=ru')
            check(fallback.code == 200 and fallback.headers.get('X-Scena-Page-Cache') == 'BYPASS',
                  'Optional cache write failure preserves HTTP200 with BYPASS')
            fallback_doc = Document(fallback.body.decode())
            check(fallback.headers.get('X-Robots-Tag') == INDEX and fallback_doc.named('robots') == [INDEX]
                  and fallback_doc.canonical() == ['https://scenaonline.vercel.app/?page=scene&lang=ru'],
                  'Cache failure preserves canonical and indexing policy')
            final = {'requests': len(report), 'public_urls': len(catalog), 'failures': failures, 'responses': report, 'snapshots': captured}
            if snapshots:
                # Remove only obsolete snapshots generated by earlier runs of
                # this fixture, whose public post UUID changes each time.
                for previous in snapshots.glob('post-*.html'):
                    if previous.name not in captured: previous.unlink()
                (snapshots / 'http-report.json').write_text(json.dumps(final, ensure_ascii=False, indent=2))
            if failures:
                print(json.dumps({'FAILURES': failures}, ensure_ascii=False, indent=2), flush=True)
                raise AssertionError(str(len(failures)) + ' SEO HTTP checks failed')
            print('PASS:', len(report), 'HTTP requests; all catalog routes/locales, direct Model, discovery, private/index policy and cache', flush=True)
        finally:
            os.environ['SCENA_WEB_TESTING'] = '1'
            for server in servers:
                server.stop(); await server.close_all_connections()


if __name__ == '__main__':
    asyncio.run(main())
