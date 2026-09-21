"""Real local HTTP tests for host, method, path and query preservation."""
from pathlib import Path
import unittest
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application, RequestHandler
from scena_web.domain_redirect import with_legacy_redirects


class ExistingHandler(RequestHandler):
    def get(self):
        self.write("existing handler")
    def head(self):
        self.get()
    def post(self):
        self.write("existing POST handler")


class DomainRedirectTests(AsyncHTTPTestCase):
    def get_app(self):
        return with_legacy_redirects(Application([(r"/.*", ExistingHandler)]))

    def request(self, path, host="scenaonline.vercel.app", method="GET"):
        return self.fetch(path, method=method, body=b"test" if method == "POST" else None,
                          headers={"Host": host}, follow_redirects=False)

    def test_public_reads_preserve_exact_path_and_query(self):
        cases = {
            '/': '/', '/?page=model&lang=ro': '/ro/model/',
            '/?page=scene&lang=ru': '/ru/',
            '/?page=professional&lang=en&utm_source=QR%20code': '/en/makeup/?utm_source=QR+code',
            '/?page=portfolio&lang=ru&view=model': '/ru/portfolio/model/',
            '/robots.txt': '/robots.txt', '/sitemap.xml': '/sitemap.xml', '/llms.txt': '/llms.txt',
            '/scena-assets/abc.webp?version=1': '/scena-assets/abc.webp?version=1',
            '/ro/model/': '/ro/model/',
            '/card': '/card', '/card/?utm_source=nfc': '/card/?utm_source=nfc',
            '/card/assets/portrait.webp': '/card/assets/portrait.webp',
        }
        for host in ('scenaonline.vercel.app', 'scena.life'):
            for path, target in cases.items():
                with self.subTest(path=path, host=host):
                    response = self.request(path, host=host)
                    self.assertEqual(response.code, 308)
                    self.assertEqual(response.headers['Location'], 'https://mbstudio.scena.life' + target)
                    self.assertNotIn('X-Robots-Tag', response.headers)

    def test_head_redirects(self):
        response = self.request("/?page=model&lang=ro", method="HEAD")
        self.assertEqual(response.code, 308)
        self.assertEqual(response.body, b"")
        self.assertEqual(response.headers["Location"], "https://mbstudio.scena.life/ro/model/")

    def test_other_hosts_have_no_redirect_or_loop(self):
        for host in ("mbstudio.scena.life", "localhost", "scenaonline-preview.vercel.app",
                     "scenaonline.vercel.app.evil.example", "xscenaonline.vercel.app"):
            with self.subTest(host=host):
                response = self.request("/?page=scene&lang=ru", host=host)
                self.assertEqual(response.code, 200)
                self.assertEqual(response.body, b"existing handler")

    def test_post_actions_and_webhooks_are_not_redirected(self):
        for path in ("/?page=booking&lang=ru", "/scena-telegram", "/scena-upload", "/auth/login"):
            with self.subTest(path=path):
                response = self.request(path, method="POST")
                self.assertEqual(response.code, 200)
                self.assertEqual(response.body, b"existing POST handler")

    def test_private_routes_health_and_404_keep_existing_handlers(self):
        for path in ("/healthz", "/scena-photo/private", "/scena-download/private",
                     "/scena-media/private", "/auth/login", "/nonexistent"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path).code, 200)

    def test_production_entrypoint_uses_redirect_gateway(self):
        entry = (Path(__file__).resolve().parents[1] / "deploy/start_web.py").read_text()
        self.assertIn("from scena_web.domain_redirect import serve", entry)


if __name__ == "__main__":
    unittest.main()
