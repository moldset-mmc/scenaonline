"""Acceptance of the migrated public site using isolated data and two HTTP servers."""
import asyncio, json, os, re, shutil, sys, tempfile
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from xml.etree import ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from seo_http import Document

async def main():
    from tornado.httpclient import AsyncHTTPClient, HTTPRequest
    from tornado.httpserver import HTTPServer
    from tornado.testing import bind_unused_port
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as folder:
        shutil.copytree(root/'media',Path(folder)/'media')
        db=Path(folder)/'test.db'
        os.environ.update(SCENA_NATIVE_WEB='1',SCENA_WEB_TESTING='1',SCENA_DB_PATH=str(db),SCENA_APP_DIR=folder,SCENA_ADMIN_PASSWORD='mbstudio-isolated-fixture')
        os.environ.pop('SCENA_CLOUD',None)
        from scena_web.server import application, BROWSER_COOKIE
        from scena_web.bootstrap import initialize
        from scena_web.domain_redirect import with_legacy_redirects
        from scena_web.mbstudio_migration import migrate,ORIGIN
        from scena_web.storage import load_form
        from scena_core import get_settings,save_settings
        from scena_seo import public_catalog
        from scena_urls import public_path,query_from_path
        await asyncio.to_thread(initialize)
        save_settings(db,{'public_base_url':'https://scena.life','model_portfolio_customized':'1',**{f'{p}_image_{i}':'' for p in ('beauty','model') for i in range(1,13)}})
        assert migrate(db,{'VERCEL':'1','VERCEL_ENV':'production'})=='migrated'
        servers=[];ports=[]
        for _ in range(2):
            socket,port=bind_unused_port();server=HTTPServer(with_legacy_redirects(application()));server.add_socket(socket)
            servers.append(server);ports.append(port)
        client=AsyncHTTPClient();sid='mbstudio-fixture-'+'a'*32;count=0
        async def request(path,host='mbstudio.scena.life',data=None,method='GET',instance=0):
            nonlocal count
            headers={'Host':host,'Cookie':BROWSER_COOKIE+'='+sid}
            if data is not None:headers.update(Origin='http://'+host,**{'Content-Type':'application/x-www-form-urlencoded'});method='POST'
            result=await client.fetch(HTTPRequest('http://127.0.0.1:'+str(ports[instance])+path,method=method,headers=headers,body=urlencode(data) if data is not None else None,follow_redirects=False,request_timeout=45),raise_error=False)
            count+=1;return result
        try:
            settings=get_settings(db);catalog=public_catalog(settings,db_path=db)
            for lang in ('ru','ro','en'):
                localized=[r for r in catalog if r['locale']==lang]
                assert len({r['title'] for r in localized})==len(localized),localized
                assert len({r['description'] for r in localized})==len(localized),localized
            for i,item in enumerate(catalog):
                path=urlsplit(item['canonical']).path
                response=await request(path,instance=i%2);assert response.code==200,(path,response.code,response.body[:200])
                text=response.body.decode();doc=Document(text)
                assert len(re.findall(r'<h1(?:\s|>)',text))==1,path
                assert doc.canonical()==[item['canonical']],path
                assert doc.alternates()==item['alternates'],path
                assert doc.language==item['locale']
                assert 'data-scena-analytics="112712591"' in text,path
                for a in doc.anchors:
                    if a['text'].strip() in ('RU','RO','EN'):
                        assert query_from_path(urlsplit(a['href']).path)['page']==item['page'],(path,a)
                old='/?'+urlencode({'page':item['page'],'lang':item['locale'],**item['params']})
                for host in ('mbstudio.scena.life','scena.life','scenaonline.vercel.app'):
                    redirect=await request(old,host=host)
                    assert redirect.code==308,(host,old,redirect.code)
                    assert redirect.headers['Location']==(ORIGIN if host!='mbstudio.scena.life' else '')+path,(host,path,redirect.headers)
            for lang in ('ru','ro','en'):
                for page,key,values in [('posts','destination',('scene','professional','model')),('portfolio','view',('professional','model'))]:
                    for value in values:
                        path=public_path({'page':page,'lang':lang,key:value})
                        response=await request(path);text=response.body.decode()
                        assert response.code==200,(path,response.code)
                        assert len(re.findall(r'<h1(?:\s|>)',text))==1,path
                        assert 'noindex' in response.headers.get('X-Robots-Tag',''),path
                        assert 'data-scena-analytics' not in text,path
            sitemap=await request('/sitemap.xml');locs=[e.text for e in ET.fromstring(sitemap.body).iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
            assert set(locs)=={r['canonical'] for r in catalog}
            robots=await request('/robots.txt');assert (ORIGIN+'/sitemap.xml') in robots.body.decode()
            home=await request('/');assert Document(home.body.decode()).named('yandex-verification')==['5b068d63b7164de0']
            private=await request('/?page=admin&lang=ru');assert private.code==302 and private.headers['Location'].startswith('/auth/login')
            unknown=await request('/ru/missing/');assert unknown.code==404 and 'noindex' in unknown.headers['X-Robots-Tag']
            preview=await request('/ru/',host='preview.example.invalid');assert 'noindex' in preview.headers['X-Robots-Tag'] or os.environ['SCENA_WEB_TESTING']=='1'
            # Submit invalid course input through the new path: validation must keep the form usable.
            course=next(r for r in catalog if r['page']=='course' and r['locale']=='ru');path=urlsplit(course['canonical']).path
            response=await request(path);text=response.body.decode();token=re.search(r'name="_token" value="([^"]+)"',text)[1]
            widgets=load_form(token,sid)['widgets'];action,button=next((k,w) for k,w in widgets.items() if w['kind']=='button' and w['label']=='Предварительно записаться')
            payload={'_token':token,'_action':action}
            for key,w in widgets.items():
                if w['group']!=button['group'] or w['kind'] in ('button','file') or w.get('disabled'):continue
                if w['kind']=='bool':
                    if w['value']:payload[key]='1'
                elif w['kind']=='choice':payload[key]=str(w['options'].index(w['value'])) if w['value'] in w['options'] else ''
                else:payload[key]=str(w['value'] or '')
            posted=await request(path,data=payload,instance=1);assert posted.code==200,(path,posted.code,posted.body[:250])
            assert 'noindex' in posted.headers['X-Robots-Tag'] and 'data-scena-analytics' not in posted.body.decode()
            head=await request('/ro/machiaj/',method='HEAD');assert head.code==200 and head.body==b''
            print(json.dumps({'result':'PASS','http_requests':count,'indexable_urls':len(catalog),'empty_urls_checked':15,'sitemap_urls':len(locs),'checks':'H1, descriptions, languages, canonical, redirects, discovery, analytics privacy, cross-server form POST'},ensure_ascii=False))
        finally:
            for server in servers:server.stop();await server.close_all_connections()

if __name__=='__main__':asyncio.run(main())
