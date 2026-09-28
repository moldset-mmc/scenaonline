"""Serve the isolated MBstudio design preview without the SCENA application."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path


class PreviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?', 1)[0] in ('/cabinet', '/cabinet/'):
            self.path = '/index.html'
        super().do_GET()

    def do_HEAD(self):
        if self.path.split('?', 1)[0] in ('/cabinet', '/cabinet/'):
            self.path = '/index.html'
        super().do_HEAD()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Robots-Tag', 'noindex, nofollow')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()


if __name__ == '__main__':
    site = Path(__file__).resolve().parent / 'site'
    handler = partial(PreviewHandler, directory=str(site))
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '80'))), handler).serve_forever()
