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
import time
from urllib.parse import urlencode, urlsplit, quote
import tornado.web
from . import bootstrap, storage, media
from .context import RenderContext, Query, current, Rerun, Stop, FormError
from .forms import apply
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
        resources=media.assets()
        css=resources.get('scena_web/static/web.css','')
        js=resources.get('scena_web/static/web.js','')
        favicon=resources.get('scena_web/static/favicon.png','')
        measure=(ROOT/'scena_web/measure.js').read_text()
        styles='\n'.join(ctx.styles)
        body=ctx.root.render()
        # The existing scene markup supplies dimensions; the first visible image
        # is prioritized rather than competing with every below-fold photograph.
        body=re.sub(r'(<img\b[^>]*)(>)',lambda m:m[1].replace('loading="lazy"','loading="eager"')+' fetchpriority="high"'+m[2],body,count=1)
        document=f'''<!doctype html><html lang="{html.escape(ctx.query.get('lang','ru'))}" data-scena-runtime="native-html"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(ctx.title)}</title>
<link rel="icon" href="{favicon}"><link rel="stylesheet" href="{css}"><style>{styles}</style><script>{measure}</script><script src="{js}" defer></script></head>
<body><div class="stApp" data-testid="stApp"><main class="stMain" data-testid="stMain"><div class="block-container stMainBlockContainer" data-testid="stMainBlockContainer">
<form id="scena-page" method="post" action="{html.escape(ctx.url,quote=True)}" enctype="multipart/form-data" novalidate>
<input type="hidden" name="_token" value="{form_token}">{body}</form></div></main></div>
<div id="scena-operation" role="status" aria-live="polite" hidden></div></body></html>'''
        return document,ctx.url,bool(ctx.widgets),round((time.monotonic()-started)*1000,1)
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
        self.set_header('Cache-Control','no-store')
        message=self._reason if status_code<500 else 'Не удалось открыть страницу. Повторите попытку.'
        self.finish('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCENA</title><main style="max-width:600px;margin:12vh auto;padding:24px;font:18px system-ui"><h1>SCENA</h1><p>'+html.escape(message)+'</p><a href="'+html.escape(self.request.uri,quote=True)+'">Открыть страницу снова</a></main></html>')


class Page(Base):
    async def get(self):
        query=Query({k:self.get_query_argument(k) for k in self.request.query_arguments})
        if (query.get('page')=='admin' or query.get('admin')=='1') and not self.owner:
            self.redirect('/auth/login?'+urlencode({'next':self.request.uri}));return
        await self.output(RenderContext({},query,self.context_headers(),session_id=self.browser_id,private=self.owner))

    def context_headers(self):
        headers={k:v for k,v in self.request.headers.items() if not k.lower().startswith('x-scena-')}
        if self.owner:headers['X-Scena-Session']=self.get_cookie(COOKIE)
        return headers

    async def post(self):
        self.require_origin()
        try:
            previous=await asyncio.to_thread(storage.load_form,self.get_body_argument('_token',''),self.browser_id,consume=True)
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
            await self.output(ctx,previous['widgets'],values,uploaded)
        except (ValueError,KeyError,IndexError) as error:
            raise tornado.web.HTTPError(409,reason=str(error) if isinstance(error,ValueError) else 'Обновите страницу и повторите действие.') from None

    async def output(self,ctx,previous=None,values=None,files=None):
        document,url,interactive,elapsed=await asyncio.to_thread(render_page,ctx,previous,values,files)
        self.set_header('Content-Type','text/html; charset=utf-8')
        self.set_header('Server-Timing',f'render;dur={elapsed}')
        self.set_header('X-Scena-URL',url)
        self.set_header('X-Scena-Runtime','native-html')
        if interactive:self.remember_browser()
        # No cookie/form token/personal state is ever stored in a shared cache.
        if not interactive and not self.owner and self.request.method=='GET':
            self.set_header('Cache-Control','public, max-age=0, must-revalidate')
            self.set_header('Vercel-CDN-Cache-Control','public, max-age=15, stale-while-revalidate=15')
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


class Assets(tornado.web.StaticFileHandler):
    def set_extra_headers(self,path):
        self.set_header('Cache-Control','public, max-age=31536000, immutable')
        self.set_header('Vercel-CDN-Cache-Control','public, max-age=31536000, immutable')
        self.set_header('X-Content-Type-Options','nosniff')


class NativeLogin(Base,Login):pass
class NativeLogout(Base,Logout):pass


class Health(Base):
    def get(self):self.write(bootstrap.REPORT)


def application():
    return tornado.web.Application([
        (r'/healthz',Health),(r'/auth/login',NativeLogin),(r'/auth/logout',NativeLogout),
        (r'/scena-assets/(.*)',Assets,{'path':str(ROOT/'public/scena-assets')}),
        (r'/scena-upload',UploadChunk),(r'/scena-download/([a-f0-9]{64})',Download),
        (r'/scena-media/([^/]+)',Media),(r'/',Page),
    ],compress_response=True)


async def serve():
    application().listen(int(os.environ.get('PORT','80')),address='0.0.0.0',max_buffer_size=4*1024*1024)
    await asyncio.to_thread(bootstrap.initialize)
    await asyncio.Event().wait()
