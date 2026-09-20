"""Stateless HTTP rendering. All mutable browser state lives in Turso/Blob."""
from __future__ import annotations
import asyncio
import html
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlencode, urlsplit, quote
import tornado.web
from . import bootstrap, storage, media, page_cache
from .context import RenderContext, Query, current, Rerun, Stop, FormError
from .forms import apply
from .business_card import card_routes
from scena_cloud_auth import COOKIE, valid_session
from deploy.serve_cloud import Login, Logout

ROOT=Path(__file__).resolve().parents[1]
BROWSER_COOKIE='__Host-scena_web'


def render_page(ctx, previous=None, values=None, files=None):
    token=current.set(ctx)
    started=time.monotonic()
    try:
        import scena_app
        if previous is not None:
            apply(ctx,previous,values,files)
        for attempt in range(8):
            ctx.reset()
            try:
                if ctx.fragment:
                    from scena_core import get_settings
                    from scena_booking_ui import render_booking_flow
                    from scena_web.widgets import st
                    settings = get_settings(os.environ['SCENA_DB_PATH'])
                    locale = scena_app.detected_locale(settings)
                    ctx.state['scena_ui_locale'] = locale
                    with st.container(key='booking_flow'):
                        render_booking_flow(Path(os.environ['SCENA_DB_PATH']), Path(os.environ.get('SCENA_APP_DIR', ROOT)), settings, locale)
                else:
                    scena_app.run()
                break
            except Rerun:
                ctx.action=''
                ctx.submitted=False
                continue
            except Stop:
                break
        else:
            raise RuntimeError('Page did not settle')
        form_token=storage.save_form(ctx.session_id,ctx.state,ctx.query,ctx.widgets) if ctx.widgets else ''
        if ctx.fragment:
            response = {'fragment': '.st-key-booking_flow', 'html': ctx.root.children[0].render(), 'token': form_token}
            return response, ctx.url, bool(ctx.widgets), round((time.monotonic()-started)*1000,1)
        resources=media.assets()
        css=resources.get('scena_web/static/web.css','')
        mobile_css=resources.get('scena_web/static/mobile.css','')
        js=resources.get('scena_web/static/web.js','')
        qr_js=resources.get('scena_web/static/intro-qr.js','')
        qr_css=resources.get('scena_web/static/intro-qr.css','')
        favicon=resources.get('scena_web/static/favicon.png','')
        measure=(ROOT/'scena_web/measure.js').read_text()
        styles='\n'.join(ctx.styles)
        from scena_home_style import shopping_labels
        body=shopping_labels(ctx.root.render())
        page = 'admin' if ctx.query.get('admin') == '1' else ctx.query.get('page','scene')
        from scena_seo import build_metadata, render_head, NOINDEX, public_base
        settings = ctx.seo_settings or {}
        locale = ctx.state.get('scena_ui_locale', ctx.query.get('lang', 'ru'))
        if not ctx.private and not ctx.submitted and not ctx.document:
            from scena_search_content import page_content
            help_copy = page_content(settings, ctx.query, locale)
            footer = '<div class="scena-footer">'
            body = body.replace(footer, help_copy + footer, 1) if footer in body else body + help_copy
        def public_image(value):
            if str(value).startswith('https://'):
                return value
            # Social previews must use durable public renditions, never a
            # signed owner image or a private-original download.
            return media.manifest().get(str(value), {}).get('public_url') or media.assets().get(str(value), '')
        ctx.seo = build_metadata(settings, ctx.query, locale,
                                 db_path=os.environ['SCENA_DB_PATH'], image_resolver=public_image)
        canonical_host = urlsplit(public_base(settings)).netloc
        preview_host = (os.environ.get('SCENA_WEB_TESTING') != '1' and canonical_host
                        and ctx.headers.get('Host', '').lower() != canonical_host)
        if ctx.submitted or ctx.state.get('booking_confirmation') or ctx.state.get('booking_receipt') or preview_host:
            ctx.seo.update(robots=NOINDEX, indexable=False, alternates={}, json_ld={}, image='', description='')
        if page == 'scene' and not ctx.submitted and not preview_host:
            ctx.seo['verification'] = {'google-site-verification':settings.get('seo_google_verification', ''),
                                       'msvalidate.01':settings.get('seo_bing_verification', ''),
                                       'yandex-verification':settings.get('seo_yandex_verification', '')}
        seo_head = render_head(ctx.seo)
        from scena_analytics import render_analytics
        seo_head += render_analytics(settings, ctx.seo, private=ctx.private, submitted=ctx.submitted, preview=bool(preview_host))
        if ctx.document:
            document = ctx.document.replace('<html ', '<html data-scena-runtime="native-html" ', 1)
            document = document.replace('<body>', '<body data-scena-page="model">', 1)
            document = document.replace('</head>', seo_head + f'\n<link rel="icon" href="{favicon}"><script>{measure}</script></head>', 1)
            from scena_urls import enabled, rewrite_links
            if enabled(settings):
                document = rewrite_links(document, public_base(settings))
            return document, ctx.url, False, round((time.monotonic()-started)*1000,1)
        # The existing scene markup supplies dimensions; the first visible image
        # is prioritized rather than competing with every below-fold photograph.
        body=re.sub(r'(<img\b[^>]*)(>)',lambda m:m[1].replace('loading="lazy"','loading="eager"')+' fetchpriority="high"'+m[2],body,count=1)
        document=f'''<!doctype html><html lang="{html.escape(ctx.state.get('scena_ui_locale',ctx.query.get('lang','ru')))}" data-scena-runtime="native-html"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">{seo_head}
<link rel="icon" href="{favicon}"><link rel="stylesheet" href="{css}"><style>{styles}</style><link rel="stylesheet" href="{mobile_css}"><script>{measure}</script><script src="{js}" defer></script><link rel="stylesheet" href="{qr_css}"><script src="{qr_js}" defer></script></head>
<body data-scena-page="{html.escape(str(page),quote=True)}"><div class="stApp" data-testid="stApp"><main class="stMain" data-testid="stMain"><div class="block-container stMainBlockContainer" data-testid="stMainBlockContainer">
<form id="scena-page" method="post" action="{html.escape(ctx.url,quote=True)}" enctype="multipart/form-data" novalidate>
<input type="hidden" name="_token" value="{form_token}">{body}</form></div></main></div>
<div id="scena-operation" role="status" aria-live="polite" hidden></div></body></html>'''
        from scena_urls import enabled, rewrite_links
        if enabled(settings):
            document = rewrite_links(document, public_base(settings))
        return document,ctx.url,bool(ctx.widgets),round((time.monotonic()-started)*1000,1)
    finally:
        current.reset(token)


def validate_action(ctx, previous, values, files):
    token = current.set(ctx)
    try:
        apply(ctx, previous, values, files)
    finally:
        current.reset(token)


class Base(tornado.web.RequestHandler):
    async def prepare(self):
        await asyncio.to_thread(bootstrap.initialize)
        self.owner=await asyncio.to_thread(valid_session,self.get_cookie(COOKIE))
        self.browser_id=self.get_cookie(BROWSER_COOKIE,'')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,80}',self.browser_id):
            self.browser_id=secrets.token_urlsafe(32)

    def set_default_headers(self):
        self.set_header('Cache-Control','no-store')
        self.set_header('X-Robots-Tag','noindex, nofollow')
        self.set_header('X-Content-Type-Options','nosniff')
        self.set_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.set_header('X-Frame-Options','SAMEORIGIN')

    def require_origin(self):
        origin=urlsplit(self.request.headers.get('Origin',''))
        if origin.netloc!=self.request.host or origin.scheme not in ('https','http'):
            raise tornado.web.HTTPError(403,reason='Обновите страницу и повторите действие.')

    def require_owner(self):
        if not self.owner:raise tornado.web.HTTPError(401,reason='Войдите в кабинет снова.')

    def remember_browser(self):
        self.set_cookie(BROWSER_COOKIE,self.browser_id,secure=True,httponly=True,samesite='Lax',path='/',max_age=storage.TTL)

    def write_error(self,status_code,**kwargs):
        from scena_i18n import tr, normalize_locale, translate_literaltext
        self.set_header('Cache-Control','no-store')
        locale = normalize_locale(self.get_query_argument('lang', 'ru'))
        message = translate_literaltext(locale, self._reason) if status_code < 500 else tr(locale,
            'Не удалось открыть страницу. Повторите попытку.', 'Pagina nu a putut fi deschisă. Încercați din nou.', 'Could not open the page. Please try again.')
        if status_code == 404:
            message = tr(locale, 'Страница не найдена.', 'Pagina nu a fost găsită.', 'Page not found.')
        retry = tr(locale, 'Открыть страницу снова', 'Deschide pagina din nou', 'Open the page again')
        self.finish('<!doctype html><html lang="'+locale+'"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex, nofollow"><title>SCENA</title><main style="max-width:600px;margin:12vh auto;padding:24px;font:18px system-ui"><h1>SCENA</h1><p>'+html.escape(message)+'</p><a href="'+html.escape(self.request.uri,quote=True)+'">'+retry+'</a></main></html>')


class Page(Base):
    async def head(self, route=None):
        await self.get(route)

    async def get(self, route=None):
        from scena_urls import query_from_path, public_path
        decoded = query_from_path(self.request.path) if route is not None else {}
        if decoded is None:
            raise tornado.web.HTTPError(404)
        query=Query({**decoded, **{k:self.get_query_argument(k) for k in self.request.query_arguments}})
        if route is not None:
            normalized = public_path(query)
            if normalized != self.request.uri:
                self.redirect(normalized, status=308); return
        elif self.request.host.split(':')[0] == 'mbstudio.scena.life' and query.get('lang') in ('ru', 'ro', 'en'):
            normalized = public_path(query)
            if not normalized.startswith('/?'):
                self.redirect(normalized, status=308); return
        if (query.get('page')=='admin' or query.get('admin')=='1') and not self.owner:
            self.redirect('/auth/login?'+urlencode({'next':self.request.uri}));return
        self.cache_key = page_cache.key(query, self.request.headers.get('Accept-Language', 'ru').split(',')[0], self.request.host) if not self.owner else None
        if self.cache_key:
            started = time.monotonic()
            try:
                self.cache_version, saved = await asyncio.to_thread(page_cache.lookup, self.cache_key)
            except sqlite3.DatabaseError:
                logging.getLogger(__name__).warning('Public page cache lookup unavailable; rendering page')
                self.cache_key, saved = None, None
                self.set_header('X-Scena-Page-Cache', 'BYPASS')
            if saved:
                self.set_header('Content-Type', 'text/html; charset=utf-8')
                self.set_header('X-Scena-Page-Cache', 'HIT')
                self.set_header('X-Scena-Runtime', 'native-html')
                self.set_header('Server-Timing', f'page-cache;dur={(time.monotonic()-started)*1000:.1f}')
                self.set_header('X-Scena-URL', saved[1])
                policy = re.search(r'<meta name="robots" content="([^"]+)"', saved[0])
                self.set_header('X-Robots-Tag', policy[1] if policy else 'noindex, nofollow')
                self.finish(saved[0]);return
        await self.output(RenderContext({},query,self.context_headers(),session_id=self.browser_id,private=self.owner))

    def context_headers(self):
        headers={k:v for k,v in self.request.headers.items() if not k.lower().startswith('x-scena-')}
        if self.owner:headers['X-Scena-Session']=self.get_cookie(COOKIE)
        return headers

    async def post(self, route=None):
        self.require_origin()
        try:
            previous=await asyncio.to_thread(storage.load_form,self.get_body_argument('_token',''),self.browser_id)
            query=Query(previous['query'])
            if query.get('page')=='admin' or query.get('admin')=='1':self.require_owner()
            values={k:self.get_body_arguments(k) for k in self.request.body_arguments}
            uploaded={}
            for identity,widget in previous['widgets'].items():
                if widget['kind']!='file':continue
                descriptor=values.get('_upload_'+identity)
                if descriptor:
                    self.require_owner()
                    descriptors=json.loads(descriptor[0])
                    if not isinstance(descriptors,list) or len(descriptors)>30:raise ValueError('Too many files')
                    files=[]
                    for item in descriptors:
                        refs=[]
                        if len(item['refs'])>180:raise ValueError('Too many chunks')
                        for identifier in item['refs']:
                            row=await asyncio.to_thread(storage.binary_record,identifier,self.browser_id)
                            if row[5]!='upload:'+identity:raise ValueError('Invalid upload')
                            refs.append(storage.BinaryRef(identifier,self.browser_id,row[0],row[1],row[2]))
                        size=sum(ref.size for ref in refs)
                        if size!=item['size']:raise ValueError('Incomplete file')
                        files.append(storage.Upload(refs,Path(item['name']).name,str(item['mime'])[:100],size))
                    uploaded[identity]=files if widget['multiple'] else files[0]
                elif identity in self.request.files:
                    self.require_owner()
                    files=[]
                    for file in self.request.files[identity]:
                        ref=await asyncio.to_thread(storage.store_binary,file.body,self.browser_id,Path(file.filename).name,file.content_type,'upload:'+identity)
                        files.append(storage.Upload([ref],ref.name,ref.mime,ref.size))
                    uploaded[identity]=files if widget['multiple'] else files[0]
            ctx=RenderContext(previous['state'],query,self.context_headers(),session_id=self.browser_id,
                action=values.get('_action',[''])[0],submitted=True,private=self.owner)
            ctx.fragment = query.get('page') == 'booking' and self.request.headers.get('X-Scena-Fragment') == 'booking'
            await asyncio.to_thread(validate_action,ctx,previous['widgets'],values,uploaded)
            # Invalid fields leave the form usable. Only a validated action can
            # consume its token, immediately before any domain mutation.
            await asyncio.to_thread(storage.load_form,self.get_body_argument('_token',''),self.browser_id,consume=True)
            await self.output(ctx)
        except (ValueError,KeyError,IndexError) as error:
            raise tornado.web.HTTPError(409,reason=str(error) if isinstance(error,ValueError) else 'Обновите страницу и повторите действие.') from None

    async def output(self,ctx,previous=None,values=None,files=None):
        document,url,interactive,elapsed=await asyncio.to_thread(render_page,ctx,previous,values,files)
        self.set_header('Content-Type','application/json; charset=utf-8' if ctx.fragment else 'text/html; charset=utf-8')
        self.set_header('Server-Timing',f'render;dur={elapsed}')
        self.set_header('X-Scena-URL',url)
        self.set_header('X-Scena-Runtime','native-html')
        status = ctx.seo.get('status', 200) if ctx.seo else 200
        self.set_status(status)
        self.set_header('X-Robots-Tag', ctx.seo['robots'] if ctx.seo else 'noindex, nofollow')
        if interactive:self.remember_browser()
        # No cookie/form token/personal state is ever stored in a shared cache.
        if status == 200 and not interactive and not self.owner and self.request.method=='GET':
            if getattr(self, 'cache_key', None):
                try:
                    await asyncio.to_thread(page_cache.save, self.cache_key, self.cache_version, document, url)
                    self.set_header('X-Scena-Page-Cache', 'MISS')
                except sqlite3.DatabaseError:
                    logging.getLogger(__name__).warning('Public page cache save unavailable; returning rendered page')
                    self.set_header('X-Scena-Page-Cache', 'BYPASS')
            # Shared DB snapshots are immediately invalidated by content edits.
            # Do not layer an independently stale CDN HTML cache above them.
        self.finish(document)


class UploadChunk(Base):
    async def post(self):
        self.require_origin();self.require_owner()
        previous=await asyncio.to_thread(storage.load_form,self.request.headers.get('X-Scena-Form',''),self.browser_id)
        identity=self.request.headers.get('X-Scena-Field','')
        widget=previous['widgets'].get(identity,{})
        if widget.get('kind')!='file' or widget.get('disabled'):raise tornado.web.HTTPError(403)
        if not 0<len(self.request.body)<=3*1024*1024:raise tornado.web.HTTPError(413)
        ref=await asyncio.to_thread(storage.store_binary,self.request.body,self.browser_id,'chunk','application/octet-stream','upload:'+identity)
        self.write({'id':ref.id,'size':ref.size})


class Download(Base):
    async def get(self,identifier):
        self.require_owner()
        try:
            row=await asyncio.to_thread(storage.binary_record,identifier,self.browser_id)
            data=await asyncio.to_thread(storage.read_binary,identifier,self.browser_id)
        except ValueError:raise tornado.web.HTTPError(404)
        name=Path(self.get_argument('name',row[0])).name
        self.set_header('Content-Type',row[1])
        self.set_header('Content-Disposition',"attachment; filename=SCENA-download; filename*=UTF-8''"+quote(name,safe=''))
        for offset in range(0,len(data),256*1024):
            self.write(data[offset:offset+256*1024])
            await self.flush()
        self.finish()


class Media(Base):
    async def get(self,token):
        try:
            descriptor=media.verify(token)
            if descriptor['private']:self.require_owner()
            data=await asyncio.to_thread(media.media_bytes,descriptor)
        except (ValueError,KeyError):raise tornado.web.HTTPError(404)
        self.set_header('Content-Type','image/webp')
        if not descriptor['private']:
            self.set_header('Cache-Control','public, max-age=3600')
            self.set_header('Vercel-CDN-Cache-Control','public, max-age=3600')
        self.finish(data)


class PhotoOriginal(Base):
    async def get(self, identifier):
        self.require_owner()
        from scena_photo_library import _files, photo_id, original_path
        root = Path(os.environ.get('SCENA_APP_DIR', ROOT))
        database = os.environ['SCENA_DB_PATH']
        def read():
            relative = next((path for path in _files(database, root) if photo_id(path) == identifier), None)
            if not relative:
                raise ValueError('Missing photo')
            path = original_path(database, root, relative)
            return path.name, path.read_bytes()
        try:
            name, data = await asyncio.to_thread(read)
        except ValueError:
            raise tornado.web.HTTPError(404) from None
        except OSError:
            raise tornado.web.HTTPError(503, reason='Original temporarily unavailable') from None
        self.set_header('Content-Type', 'application/octet-stream')
        self.set_header('Content-Disposition', "attachment; filename=SCENA-photo; filename*=UTF-8''" + quote(name, safe=''))
        self.finish(data)


class Assets(tornado.web.StaticFileHandler):
    def set_extra_headers(self,path):
        self.set_header('Cache-Control','public, max-age=31536000, immutable')
        self.set_header('Vercel-CDN-Cache-Control','public, max-age=31536000, immutable')
        self.set_header('X-Content-Type-Options','nosniff')


class NativeLogin(Base,Login):pass
class NativeLogout(Base,Logout):pass


class SearchDocument(Base):
    async def head(self, name):
        await self.get(name)

    async def get(self, name):
        from scena_core import get_settings
        from scena_seo import robots_txt, sitemap_xml, llms_txt
        def document():
            settings = get_settings(os.environ['SCENA_DB_PATH'])
            if name == 'robots.txt':
                return robots_txt(settings)
            return (sitemap_xml if name == 'sitemap.xml' else llms_txt)(settings, db_path=os.environ['SCENA_DB_PATH'])
        self.set_header('Content-Type', 'application/xml; charset=utf-8' if name == 'sitemap.xml' else 'text/plain; charset=utf-8')
        self.finish(await asyncio.to_thread(document))


class NotFound(Base):
    def prepare(self):
        raise tornado.web.HTTPError(404)


class Health(Base):
    def get(self):self.write(bootstrap.REPORT)


class TelegramWebhook(Base):
    async def post(self):
        if len(self.request.body) > 64 * 1024:
            raise tornado.web.HTTPError(413)
        from scena_shop_telegram import receive_update
        try:
            update = json.loads(self.request.body)
            await asyncio.to_thread(receive_update, os.environ['SCENA_DB_PATH'], update,
                self.request.headers.get('X-Telegram-Bot-Api-Secret-Token', ''))
        except PermissionError:
            raise tornado.web.HTTPError(403, reason='Invalid Telegram webhook') from None
        except (ValueError, TypeError, KeyError, AttributeError):
            raise tornado.web.HTTPError(400, reason='Invalid Telegram update') from None
        except Exception:
            # Return a retryable code without logging provider credentials.
            raise tornado.web.HTTPError(503, reason='Telegram update unavailable') from None
        self.write({'ok':True})


def application():
    return tornado.web.Application([
        *card_routes(),
        (r'/healthz',Health),(r'/auth/login',NativeLogin),(r'/auth/logout',NativeLogout),
        (r'/scena-telegram',TelegramWebhook),
        (r'/(robots\.txt|sitemap\.xml|llms\.txt)',SearchDocument),
        (r'/scena-assets/(.*)',Assets,{'path':str(ROOT/'public/scena-assets')}),
        (r'/scena-upload',UploadChunk),(r'/scena-download/([a-f0-9]{64})',Download),
        (r'/scena-media/([^/]+)',Media),(r'/',Page),
        (r'/((?:ru|ro|en)(?:/.*)?)',Page),
        (r'/scena-photo/([a-f0-9]{64})',PhotoOriginal),
        (r'/.*',NotFound),
    ],compress_response=True)


async def serve():
    application().listen(int(os.environ.get('PORT','80')),address='0.0.0.0',max_buffer_size=4*1024*1024)
    await asyncio.to_thread(bootstrap.initialize)
    await asyncio.Event().wait()
