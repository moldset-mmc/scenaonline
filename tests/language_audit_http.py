"""Isolated language/navigation inventory of every public page and cabinet view.

Run separately: native UI environment must be set before application imports.
Writes an optional audit inventory to SCENA_LANGUAGE_AUDIT (no live data).
"""
import asyncio
import html
from collections import Counter
from html.parser import HTMLParser
import json
import io
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import parse_qs, urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class VisibleDocument(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.text = []
        self.links = []
        self.active_link = None
        self.language = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.language = attrs.get('lang')
        if tag in ('script', 'style', 'textarea'):
            self.stack.append(tag)
        if tag == 'a':
            self.active_link = {'href':attrs.get('href', ''), 'label':'', 'current':attrs.get('aria-current')}
            self.links.append(self.active_link)
        if tag == 'iframe' and attrs.get('srcdoc'):
            frame = VisibleDocument(); frame.feed(attrs['srcdoc'])
            self.text.extend(frame.text)
            self.links.extend(frame.links)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        if tag == 'a':
            self.active_link = None

    def handle_data(self, data):
        if self.stack or not data.strip():
            return
        clean = ' '.join(data.split())
        self.text.append(clean)
        if self.active_link is not None:
            self.active_link['label'] += clean


async def main():
    from tornado.httpclient import AsyncHTTPClient, HTTPRequest
    from tornado.httpserver import HTTPServer
    from tornado.testing import bind_unused_port
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as folder:
        fixture = Path(folder)
        shutil.copytree(root/'media', fixture/'media')
        os.environ.update(SCENA_NATIVE_WEB='1', SCENA_WEB_TESTING='1', SCENA_DB_PATH=str(fixture/'test.db'), SCENA_APP_DIR=folder, SCENA_ADMIN_PASSWORD='isolated-language-fixture')
        os.environ.pop('SCENA_CLOUD', None)
        from scena_web.server import application, BROWSER_COOKIE
        from scena_web.bootstrap import initialize
        from scena_cloud_auth import COOKIE, make_session
        from scena_core import get_settings, save_settings, list_services, create_request
        from scena_photo_library import photo_id
        await asyncio.to_thread(initialize)
        import scena_app
        from scena_i18n import CATALOG
        save_settings(fixture/'test.db', {'public_base_url':'https://scenaonline.vercel.app'})
        sock, port = bind_unused_port()
        server = HTTPServer(application()); server.add_socket(sock)
        base = 'http://127.0.0.1:' + str(port)
        client = AsyncHTTPClient()
        sid = 'language-fixture-' + 'a'*32
        cookie = COOKIE+'='+make_session()+'; '+BROWSER_COOKIE+'='+sid
        evidence = {'kind':'isolated native HTTP fixtures, not live owner data', 'pages':[], 'failures':[], 'cyrillic_inventory':{}, 'owner_translation_gaps':[], 'auth_checks':[]}
        services = list_services(fixture/'test.db')
        # Use actual isolated records so status/contact widgets are covered too.
        from scena_shop import PRODUCT_FIELDS, save_product, create_order, quote_cart
        from PIL import Image
        picture = io.BytesIO(); Image.new('RGB', (600, 700), 'ivory').save(picture, 'PNG')
        product = save_product(fixture/'test.db', fixture,
            {**{field:'Fixture '+field for field in PRODUCT_FIELDS}, 'price':'100', 'status':'published'}, upload=picture.getvalue())
        cart = {product['id']:1}
        order = create_order(fixture/'test.db', cart, {'name':'Fixture Customer','phone':'+37360000000','consent':True,'preferred_contact':'phone'},
            reviewed_quote=quote_cart(fixture/'test.db',cart)['fingerprint'], request_key='language-fixture-order-00001', locale='en')
        request_id = create_request(fixture/'test.db', request_type='model_application', name='Fixture Client', phone='+37360000000', consent=True, locale='en', city='Chișinău', experience='Fixture experience')
        from scena_database import connect
        with connect(fixture/'test.db') as database:
            database.execute("UPDATE requests SET request_type='service_request', service='Fixture Service', telegram_status='queued' WHERE id=?", (request_id,))
        from scena_publications import save_draft, publish_local
        publication = save_draft(fixture/'test.db', title_ru='Fixture post RU', title_ro='Fixture post RO', title_en='Fixture post EN', body_ru='Fixture body RU', body_ro='Fixture body RO', body_en='Fixture body EN', image_url='media/qr-scenes/model.png', translations_approved=True, show_scene=True, show_model=True)
        publication = publish_local(fixture/'test.db', publication['post_id'], publication['revision'], media_root=fixture)
        course = next(item for item in services if item['kind']=='course')
        routes = [(page, {'page':page}, False) for page in ('scene','portfolio','professional','model','booking','course','join-model','invite-model','post','posts','shop')]
        routes += [(section+'/'+view, {'page':'admin','section':section,'view':view}, True) for section, views in scena_app.ADMIN_VIEWS.items() for view in views]
        routes += [
            ('portfolio-model', {'page':'portfolio','view':'model'}, False),
            ('posts-model', {'page':'posts','destination':'model'}, False),
            ('post-detail', {'page':'post','post':publication['public_id']}, False),
            ('booking-service', {'page':'booking','service':str(services[0]['id'])}, False),
            ('course-service', {'page':'course','service':str(course['id'])}, False),
            ('photos-detail', {'page':'admin','section':'photos','view':'library','photo':photo_id('media/qr-scenes/model.png'),'filter':'model'}, True),
            ('photos-target', {'page':'admin','section':'photos','view':'library','target':'model_intro_image','mode':'replace','filter':'model'}, True),
            ('orders', {'page':'admin','section':'pages','view':'shop','orders':'1'}, True),
            ('order-detail', {'page':'admin','section':'pages','view':'shop','order':order['id']}, True),
            ('request-detail', {'page':'admin','section':'work','view':'requests','request':str(request_id)}, True),
        ]
        try:
            for locale in ('ru','ro','en'):
                cyrillic = Counter()
                for name, params, owner in routes:
                    path = '/?' + urlencode({**params, 'lang':locale})
                    response = await client.fetch(HTTPRequest(base+path, headers={'Cookie':cookie if owner else BROWSER_COOKIE+'='+sid}, follow_redirects=False, request_timeout=40), raise_error=False)
                    document = VisibleDocument(); document.feed(response.body.decode())
                    switches = [link for link in document.links if link['label'] in ('RU','RO','EN')]
                    row = {'route':name, 'locale':locale, 'status':response.code, 'html_lang':document.language, 'language_links':switches, 'cyrillic_visible':list(dict.fromkeys(text for text in document.text if re.search('[А-Яа-яЁё]', text))) if locale != 'ru' else []}
                    if name == 'promotion/search' and os.environ.get('SCENA_LANGUAGE_AUDIT'):
                        capture_path = Path(os.environ['SCENA_LANGUAGE_AUDIT'])
                        capture_path.mkdir(parents=True, exist_ok=True)
                        snapshot = re.sub(r'(name="_token" value=")[^"]*', r'\1', response.body.decode())
                        (capture_path/('promotion-search-'+locale+'.html')).write_text(snapshot)

                    evidence['pages'].append(row)
                    expected_status = 404 if (params['page']=='course' and not params.get('service')) or (params['page']=='post' and not params.get('post')) else 200
                    row['expected_status'] = expected_status
                    if response.code != expected_status or document.language != locale:
                        evidence['failures'].append({'route':name, 'locale':locale, 'error':'HTTP/language mismatch'})
                    for wanted in ('ru','ro','en'):
                        candidates = [link for link in switches if link['label']==wanted.upper()]
                        if not candidates:
                            evidence['failures'].append({'route':name, 'locale':locale, 'error':'missing '+wanted+' switch'})
                            continue
                        query = parse_qs(urlsplit(candidates[0]['href']).query)
                        for key, value in {**params, 'lang':wanted}.items():
                            # Photo detail normalizes the filter independently of the selected image.
                            if key == 'filter':
                                continue
                            if query.get(key) != [str(value)]:
                                evidence['failures'].append({'route':name, 'locale':locale, 'error':'switch loses '+key, 'target':candidates[0]['href']})
                    if locale != 'ru':
                        for text in document.text:
                            if re.search('[А-Яа-яЁё]', text):
                                cyrillic[text] += 1
                evidence['cyrillic_inventory'][locale] = [{'text':text,'occurrences':count,'exact_platform_literal':text in CATALOG} for text,count in cyrillic.most_common()]
            # The sign-in page must retain the requested language and record.
            from deploy.serve_cloud import LOGIN_NONCE
            for locale in ('ru','ro','en'):
                target = '/?' + urlencode({'page':'admin','lang':locale,'section':'work','view':'requests','request':request_id})
                response = await client.fetch(HTTPRequest(base+'/auth/login?'+urlencode({'next':target}), follow_redirects=False),raise_error=False)
                document = VisibleDocument(); document.feed(response.body.decode())
                assert response.code == 200 and document.language == locale
                assert 'noindex' in response.headers.get('X-Robots-Tag','')
                switches = [link for link in document.links if link['label'] in ('RU','RO','EN')]
                assert len(switches) == 3
                for link in switches:
                    outer = parse_qs(urlsplit(link['href']).query)
                    destination = parse_qs(urlsplit(outer['next'][0]).query)
                    assert destination['request'] == [str(request_id)]
                    assert destination['lang'] == [link['label'].lower()]
                if locale != 'ru':
                    assert not re.search('[А-Яа-яЁё]', ' '.join(document.text)), document.text
                nonce = re.search(r'name="nonce" value="([^"]+)"',response.body.decode())[1]
                headers = {'Origin':base,'Cookie':LOGIN_NONCE+'='+nonce,'Content-Type':'application/x-www-form-urlencoded'}
                failed = await client.fetch(HTTPRequest(base+'/auth/login',method='POST',headers=headers,
                    body=urlencode({'nonce':nonce,'next':target,'lang':locale,'password':'incorrect-fixture-password'}),follow_redirects=False),raise_error=False)
                error_page = VisibleDocument(); error_page.feed(failed.body.decode())
                assert failed.code == 401 and error_page.language == locale
                if locale != 'ru':
                    assert not re.search('[А-Яа-яЁё]', ' '.join(error_page.text)), error_page.text
                new_nonce = re.search(r'name="nonce" value="([^"]+)"',failed.body.decode())[1]
                headers['Cookie'] = LOGIN_NONCE+'='+new_nonce
                signed_in = await client.fetch(HTTPRequest(base+'/auth/login',method='POST',headers=headers,
                    body=urlencode({'nonce':new_nonce,'next':target,'lang':locale,'password':os.environ['SCENA_ADMIN_PASSWORD']}),follow_redirects=False),raise_error=False)
                assert signed_in.code == 302 and signed_in.headers['Location'] == target
                logged_out = await client.fetch(HTTPRequest(base+'/auth/logout?'+urlencode({'lang':locale}),headers={'Cookie':cookie},follow_redirects=False),raise_error=False)
                assert logged_out.code == 302 and parse_qs(urlsplit(logged_out.headers['Location']).query)['lang'] == [locale]
                after_logout = await client.fetch(HTTPRequest(base+logged_out.headers['Location'],follow_redirects=False),raise_error=False)
                logout_page = VisibleDocument(); logout_page.feed(after_logout.body.decode())
                assert logout_page.language == locale
                default_target = html.unescape(re.search(r'name="next" value="([^"]+)"',after_logout.body.decode())[1])
                assert parse_qs(urlsplit(default_target).query)['lang'] == [locale]
                evidence['auth_checks'].append({'locale':locale,'login':response.code,'invalid_password':failed.code,'success_redirect':signed_in.code,'record_and_locale_retained':True,'noindex':True,'logout_language_retained':True})
            settings = get_settings(fixture/'test.db')
            for key, value in settings.items():
                if key.endswith('_ru') and value.strip():
                    base_key = key[:-3]
                    for locale in ('ro','en'):
                        if base_key+'_'+locale in settings and not settings[base_key+'_'+locale].strip():
                            evidence['owner_translation_gaps'].append({'field':base_key, 'locale':locale})
            output = os.environ.get('SCENA_LANGUAGE_AUDIT')
            if output:
                directory = Path(output); directory.mkdir(parents=True, exist_ok=True)
                (directory/'inventory.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
            print(json.dumps({'pages':len(evidence['pages']), 'failures':len(evidence['failures']), 'cyrillic_unique':{locale:len(items) for locale,items in evidence['cyrillic_inventory'].items()}, 'fixture_translation_gaps':len(evidence['owner_translation_gaps']), 'auth_locales':len(evidence['auth_checks'])}, ensure_ascii=False), flush=True)
            if os.environ.get('SCENA_LANGUAGE_INVENTORY_ONLY') != '1':
                assert not evidence['failures'], evidence['failures']
        finally:
            server.stop(); await server.close_all_connections()


if __name__ == '__main__':
    asyncio.run(main())
