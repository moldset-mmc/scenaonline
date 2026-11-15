import re
import unittest
from xml.etree import ElementTree

from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application, RequestHandler

from scena_web.domain_redirect import with_legacy_redirects
from scena_web.newcard import newcard_routes


class Salon(RequestHandler):
    def get(self, *args):
        self.write('unchanged salon handler')
    def post(self, *args):
        self.write('unchanged post handler')


class PlatformIsolationTests(AsyncHTTPTestCase):
    def get_app(self):
        return with_legacy_redirects(Application([*newcard_routes(),(r'/.*',Salon)]))

    def get(self,path,host='scena.life',**kwargs):
        return self.fetch(path,headers={'Host':host},follow_redirects=False,**kwargs)

    def test_root_is_platform_with_own_canonical_and_romanian_default(self):
        r=self.get('/')
        self.assertEqual(r.code,200)
        self.assertNotIn('Location',r.headers)
        self.assertIn(b'<html lang="ro">',r.body)
        self.assertIn(b'<link rel="canonical" href="https://scena.life/">',r.body)
        self.assertIn(b'<meta property="og:url" content="https://scena.life/">',r.body)
        self.assertNotIn('noindex',r.headers['X-Robots-Tag'])
        self.assertIn(b'content="index, follow, max-image-preview:large"',r.body)
        self.assertNotIn(b'window.fetch=async function',r.body)
        self.assertNotIn(b'window.__SCENA_PREVIEW__=true',r.body)
        self.assertNotIn('Set-Cookie',r.headers)
        self.assertIn(b"connect-src 'self'",r.body)

    def test_russian_is_self_canonical_with_reciprocal_hreflang(self):
        r=self.get('/ru/')
        self.assertEqual(r.code,200)
        self.assertIn(b'<html lang="ru">',r.body)
        self.assertIn(b'<link rel="canonical" href="https://scena.life/ru/">',r.body)
        for path in ('/','/ru/'):
            body=self.get(path).body
            for lang,url in [('ro','/'),('ru','/ru/'),('x-default','/')]:
                self.assertIn(f'hreflang="{lang}" href="https://scena.life{url}"'.encode(),body)

    def test_loading_keeps_the_localized_fallback_outside_the_react_root(self):
        for path, heading in (('/', 'Mereu pe scenă'), ('/ru/', 'Всегда на сцене')):
            with self.subTest(path=path):
                initial_html = self.get(path).body.split(b'<body>', 1)[1].split(b'<script>', 1)[0]
                self.assertIn(b'<div id="root"></div><noscript>', initial_html)
                before_fallback, _, fallback = initial_html.partition(b'<noscript>')
                self.assertNotIn(b'<main>', before_fallback)
                self.assertIn(f'<h1>{heading}</h1>'.encode(), fallback)
                self.assertIn(b'href="/" lang="ro"', fallback)
                self.assertIn(b'href="/ru/" lang="ru"', fallback)
                self.assertNotIn(b'href="#example"', fallback)

    def test_normalization_preserves_tracking_and_stays_on_platform(self):
        for path,target in [('/ro/','/'),('/ro','/'),('/ru','/ru/'),('/?lang=ru&utm_source=test','/ru/?utm_source=test'),('/?lang=ro','/')]:
            r=self.get(path)
            self.assertEqual(r.code,308)
            self.assertEqual(r.headers['Location'],target)

    def test_unpublished_language_routes_do_not_redirect_to_salon(self):
        for path in ('/en','/en/','/en/newcard','/ro/newcard','/ru/newcard'):
            r=self.get(path)
            self.assertEqual(r.code,404)
            self.assertNotIn('Location',r.headers)
            self.assertIn('noindex',r.headers['X-Robots-Tag'])

    def test_salon_hosts_and_pages_are_unchanged(self):
        for path in ('/','/ru/','/ro/','/en/','/robots.txt','/sitemap.xml'):
            r=self.get(path,'mbstudio.scena.life')
            self.assertEqual(r.code,200)
            self.assertEqual(r.body,b'unchanged salon handler')
        legacy=self.get('/ru/makiyazh/')
        self.assertEqual(legacy.code,308)
        self.assertEqual(legacy.headers['Location'],'https://mbstudio.scena.life/ru/makiyazh/')
        old=self.get('/','scenaonline.vercel.app')
        self.assertEqual(old.code,308)
        self.assertEqual(old.headers['Location'],'https://mbstudio.scena.life/')

    def test_private_and_post_routes_retain_their_handlers(self):
        for path in ('/','/scena-telegram','/api/intake/start'):
            r=self.get(path,method='POST',body='')
            self.assertEqual(r.code,200)
            self.assertEqual(r.body,b'unchanged post handler')
        for path in ('/healthz','/scena-download/'+'a'*64):
            self.assertEqual(self.get(path).body,b'unchanged salon handler')

    def test_search_documents_have_no_salon_urls_and_valid_xml(self):
        robots=self.get('/robots.txt')
        self.assertEqual(robots.code,200)
        self.assertIn(b'Sitemap: https://scena.life/sitemap.xml',robots.body)
        self.assertNotIn(b'mbstudio',robots.body)
        sitemap=self.get('/sitemap.xml')
        root=ElementTree.fromstring(sitemap.body)
        urls=[e.text for e in root.findall('{*}url/{*}loc')]
        self.assertEqual(urls,['https://scena.life/','https://scena.life/ru/','https://scena.life/newcard'])
        for url in urls:
            r=self.get(url.removeprefix('https://scena.life'))
            self.assertEqual(r.code,200)
            self.assertNotIn('noindex',r.headers['X-Robots-Tag'])
            self.assertIn(f'<link rel="canonical" href="{url}">'.encode(),r.body)

    def test_newcard_is_indexable_only_on_platform_not_preview_or_salon(self):
        for host,indexable in [('scena.life',True),('mbstudio.scena.life',False),('preview.vercel.app',False)]:
            r=self.get('/newcard',host)
            self.assertEqual(r.code,200)
            self.assertEqual('noindex' not in r.headers['X-Robots-Tag'],indexable)
            self.assertEqual(b'content="noindex,follow"' not in r.body,indexable)
            self.assertIn(b'<link rel="canonical" href="https://scena.life/newcard">',r.body)
        r=self.fetch('/newcard',headers={'Host':'preview.vercel.app','X-Forwarded-Host':'scena.life'},follow_redirects=False)
        self.assertIn('noindex',r.headers['X-Robots-Tag'])

    def test_head_has_same_status_and_no_body(self):
        for path in ('/','/ru/','/robots.txt','/sitemap.xml','/newcard'):
            r=self.get(path,method='HEAD')
            self.assertEqual(r.code,200)
            self.assertEqual(r.body,b'')


if __name__=='__main__':unittest.main()
