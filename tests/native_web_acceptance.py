"""Real HTTP acceptance of the native UI against isolated, shared fixtures.
Run separately so native presentation imports cannot affect desktop tests.
"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import re
import io
import tempfile
import time
from urllib.parse import urlencode
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.seo_http import Document

async def main():
    from tornado.httpclient import AsyncHTTPClient, HTTPRequest
    from tornado.httpserver import HTTPServer
    from tornado.testing import bind_unused_port
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as folder:
        fixture=Path(folder)
        shutil.copytree(root/'media',fixture/'media')
        os.environ.update(SCENA_NATIVE_WEB='1',SCENA_WEB_TESTING='1',SCENA_DB_PATH=str(fixture/'test.db'),SCENA_APP_DIR=str(fixture),SCENA_ADMIN_PASSWORD='isolated-fixture-password')
        os.environ.pop('SCENA_CLOUD',None)
        from scena_web.server import application, BROWSER_COOKIE
        from scena_web.bootstrap import initialize
        from scena_cloud_auth import COOKIE, make_session
        from scena_web.storage import load_form
        await asyncio.to_thread(initialize)
        servers=[];urls=[]
        for _ in range(2):
            sock,port=bind_unused_port()
            server=HTTPServer(application());server.add_socket(sock);servers.append(server)
            urls.append('http://127.0.0.1:'+str(port))
        client=AsyncHTTPClient()
        snapshots=Path(os.environ['SCENA_TEST_SNAPSHOTS']) if os.environ.get('SCENA_TEST_SNAPSHOTS') else None
        if snapshots:
            snapshots.mkdir(parents=True,exist_ok=True)
        def capture(name, response):
            if snapshots and response.code == 200:
                document=re.sub(r'(name="_token" value=")[^"]*',r'\1',response.body.decode())
                (snapshots/(name+'.html')).write_text(document)
        sid='fixture-browser-identity-'+'a'*20
        cookie=COOKIE+'='+make_session()+'; '+BROWSER_COOKIE+'='+sid
        async def request(path,*,owner=False,data=None,instance=0,headers=None):
            start=time.monotonic()
            h={'Cookie':cookie if owner else BROWSER_COOKIE+'='+sid,'Host':'scena-fixture.test',**(headers or {})}
            if data is not None:h.update({'Origin':'http://'+h['Host'],'Content-Type':'application/x-www-form-urlencoded'})
            response=await client.fetch(HTTPRequest(urls[instance]+path,method='POST' if data is not None else 'GET',headers=h,body=urlencode(data,doseq=True) if data is not None else None,follow_redirects=False,request_timeout=40),raise_error=False)
            return response,round((time.monotonic()-start)*1000)
        failures=[]
        try:
            for locale in ('ru','ro','en'):
                for page in ('scene','portfolio','professional','model','booking','course','join-model','invite-model','post','posts','shop'):
                    response,elapsed=await request('/?page='+page+'&lang='+locale)
                    print('PUBLIC',locale,page,response.code,elapsed,len(response.body),flush=True)
                    expected = 404 if page in ('course', 'post') else 200
                    if response.code!=expected:failures.append(locale+'/'+page)
                    elif expected == 404:
                        assert response.headers.get('X-Robots-Tag') == 'noindex, nofollow'
                    else:
                        assert b'data-scena-runtime="native-html"' in response.body
                        assert Document(response.body.decode()).language == locale
                        capture('public-'+page+'-'+locale,response)
            response,_=await request('/?page=admin',headers={'X-Scena-Session':make_session()})
            assert response.code==302,'Spoofed auth header accepted'
            import scena_app
            for locale in ('ru','ro','en'):
                for section,views in scena_app.ADMIN_VIEWS.items():
                    for view in views:
                        response,elapsed=await request('/?page=admin&lang='+locale+'&section='+section+'&view='+view,owner=True)
                        print('CABINET',locale,section,view,response.code,elapsed,len(response.body),flush=True)
                        if response.code!=200:failures.append(locale+'/'+section+'/'+view)
                        document=response.body.decode()
                        assert 'Vercel-CDN-Cache-Control' not in response.headers
                        assert document.count('<header class="scena-cabinet-header">') == 1
                        assert '<nav class="scena-admin-tabs">' not in document
                        assert ('<html lang="'+locale+'"') in document
                        capture('cabinet-'+section+'-'+view+'-'+locale,response)
            assert not failures,failures
            def form(response):
                token=re.search(r'name="_token" value="([^"]+)"',response.body.decode())[1]
                return token,load_form(token,sid)
            def payload(response,button_label,changes=None,changed=None):
                token,saved=form(response)
                widgets=saved['widgets']
                action=next((k for k,w in widgets.items() if w['kind']=='button' and w['label']==button_label),None) if button_label else None
                trigger=action or next(k for k,w in widgets.items() if w['label']==changed)
                group=widgets[trigger]['group']
                result={'_token':token,'_action':action} if action else {'_token':token,'_changed':trigger}
                for identity,w in widgets.items():
                    if w['group']!=group or w.get('disabled') or w['kind'] in ('button','file'):continue
                    value=(changes or {}).get(w['label'],w['value'])
                    if w['kind']=='bool':
                        if value:result[identity]='1'
                    elif w['kind']=='choice':result[identity]=str(w['options'].index(value)) if value in w['options'] else ''
                    elif w['kind']=='multiple':result[identity]=[str(w['options'].index(v)) for v in value]
                    else:result[identity]=value.isoformat() if hasattr(value,'isoformat') else str(value or '')
                return result
            # A validation error must not consume the form and strand the editor.
            schedule_path='/?page=admin&lang=ru&section=work&view=schedule'
            fresh,_=await request(schedule_path,owner=True)
            old_token,_=form(fresh)
            invalid,_=await request(schedule_path,owner=True,data=payload(fresh,'Сохранить',{'Интервал начала записи, минут':1}))
            assert invalid.code==409,invalid.body
            load_form(old_token,sid)
            corrected,_=await request(schedule_path,owner=True,data=payload(fresh,'Сохранить'))
            assert corrected.code==200,corrected.body
            assert 'data-cabinet-nav' in corrected.body.decode()
            scene_view,_=await request('/?page=admin&lang=ru&section=pages&view=scene',owner=True)
            model_view,_=await request('/?page=admin&lang=ru&section=pages&view=model',owner=True)
            assert scene_view.code==model_view.code==200
            assert 'data-cabinet-nav' in model_view.body.decode()
            print('PASS corrected save reuses unconsumed form; cabinet navigation is independent GET',flush=True)
            # Ready HTML is reused across replicas, then invalidated by edits.
            scene='/?page=scene&lang=ru'
            await request(scene)
            cached,_=await request(scene,instance=1)
            assert cached.headers.get('X-Scena-Page-Cache')=='HIT'
            assert b'name="_token" value=""' in cached.body
            assert 'Set-Cookie' not in cached.headers
            from scena_core import get_settings, save_settings, schedule_periods
            save_settings(os.environ['SCENA_DB_PATH'], {'master_name_ru':'Cache invalidation fixture'})
            refreshed,_=await request(scene,instance=1)
            assert 'Cache invalidation fixture' in refreshed.body.decode()
            assert refreshed.headers.get('X-Scena-Page-Cache')=='MISS'
            print('PASS saved public HTML reused across instances and invalidated by content edits',flush=True)
            # Save a single weekday, then a single date through real form validation.
            schedule='/?page=admin&lang=ru&section=work&view=schedule'
            response,_=await request(schedule,owner=True)
            response,_=await request(schedule,owner=True,data=payload(response,None,{'День недели':2},changed='День недели'))
            response,_=await request(schedule,owner=True,data=payload(response,'Сохранить только этот день',{'Выходной день':False,'Работа с':'10:00','Работа до':'12:00','Есть перерыв':False}),instance=1)
            assert response.code==200,response.body
            overrides=json.loads(get_settings(os.environ['SCENA_DB_PATH'])['schedule_day_hours'])
            assert overrides=={'2':[['10:00','12:00']]},overrides
            response,_=await request(schedule,owner=True,data=payload(response,None,{'Что настроить':'date'},changed='Что настроить'))
            from datetime import date, timedelta
            selected_date=date.today()+timedelta(days=2)
            untouched=selected_date+timedelta(days=1)
            periods_before=schedule_periods(os.environ['SCENA_DB_PATH'],untouched.isoformat())
            response,_=await request(schedule,owner=True,data=payload(response,None,{'Дата для изменения':selected_date},changed='Дата для изменения'),instance=1)
            response,_=await request(schedule,owner=True,data=payload(response,'Сохранить только этот день',{'Выходной день':False,'Работа с':'14:00','Работа до':'16:00','Есть перерыв':False}))
            assert response.code==200,response.body
            assert [(a.isoformat(),b.isoformat()) for a,b in schedule_periods(os.environ['SCENA_DB_PATH'],selected_date.isoformat())]==[('14:00:00','16:00:00')]
            assert periods_before==schedule_periods(os.environ['SCENA_DB_PATH'],untouched.isoformat())
            response,_=await request(schedule,owner=True,data=payload(response,'Вернуть общий график для этого дня'))
            assert response.code==200
            print('PASS individual weekday/date save and reset across instances, adjacent day preserved',flush=True)
            # The AJAX booking branch must not invoke the full page renderer.
            response,_=await request('/?page=booking&lang=ru')
            _,saved=form(response)
            service=next(w for w in saved['widgets'].values() if w.get('key')=='booking_service')
            from unittest.mock import patch
            data=payload(response,None,{service['label']:service['options'][0]},changed=service['label'])
            with patch('scena_app.run',side_effect=AssertionError('Full page rendered for booking interaction')):
                fragment,_=await request('/?page=booking&lang=ru',data=data,headers={'X-Scena-Fragment':'booking'},instance=1)
            assert fragment.code==200,fragment.body
            part=json.loads(fragment.body)
            assert part['fragment']=='.st-key-booking_flow' and 'booking_calendar' in part['html']
            assert '<html' not in part['html'] and 'scena-footer' not in part['html']
            load_form(part['token'],sid)
            full,_=await request('/?page=booking&lang=ru&service='+str(service['options'][0]))
            print('PASS booking fragment without whole-page render; bytes',len(full.body),'->',len(fragment.body),flush=True)
            # Simulate zero-request browser selection using registered hidden choices.
            local=json.loads(re.search(r'<script id="scena-booking-data" type="application/json">(.*?)</script>',full.body.decode(),re.S)[1])
            selected=next(day for day,slots in local['availability'].items() if slots)
            hour=local['availability'][selected][0]
            data=payload(full,'Продолжить',{'_booking_local_date':selected,'_booking_local_time':hour})
            selection,_=await request('/?page=booking&lang=ru',data=data,headers={'X-Scena-Fragment':'booking'})
            assert selection.code==200,selection.body
            assert 'Проверьте вашу запись' in json.loads(selection.body)['html']
            # Availability changing after the local snapshot must block Continue.
            full,_=await request('/?page=booking&lang=ru&service='+str(service['options'][0]))
            data=payload(full,'Продолжить',{'_booking_local_date':selected,'_booking_local_time':hour})
            from scena_core import save_date_hours
            save_date_hours(os.environ['SCENA_DB_PATH'],selected,closed=True)
            stale,_=await request('/?page=booking&lang=ru',data=data,headers={'X-Scena-Fragment':'booking'},instance=1)
            assert stale.code==200,stale.body
            assert 'Проверьте вашу запись' not in json.loads(stale.body)['html']
            assert 'Выбранное время уже недоступно' in json.loads(stale.body)['html']
            save_date_hours(os.environ['SCENA_DB_PATH'],selected,reset=True)
            print('PASS local day/time selection validated; stale slot blocked before contact step',flush=True)

            # The author's placement choice is a native control and survives replicas.
            path='/?page=admin&lang=ru&section=promotion&view=posts'
            response,_=await request(path,owner=True)
            response,_=await request(path,data=payload(response,'+ Новая публикация'),owner=True)
            _,saved=form(response)
            logo_choice=next(w for w in saved['widgets'].values() if w.get('key')=='post_logo_style_new')
            assert logo_choice['options']==['editorial','compact']
            response,_=await request(path,data=payload(response,None,{logo_choice['label']:'compact'},changed=logo_choice['label']),owner=True,instance=1)
            response,_=await request(path,data=payload(response,'Сохранить черновик',{'Заголовок RU':'Logo choice test','Текст RU':'Текст','Text RO':'Text'}),owner=True)
            from scena_publications import list_publications
            logo_draft=next(p for p in list_publications(os.environ['SCENA_DB_PATH']) if p['title_ru']=='Logo choice test')
            assert logo_draft['logo_style']=='compact'
            response,_=await request(path,owner=True,instance=1)
            response,_=await request(path,data=payload(response,f"№ {logo_draft['id']} · Logo choice test"),owner=True,instance=1)
            _,saved=form(response)
            assert next(w for w in saved['widgets'].values() if str(w.get('key','')).startswith('post_logo_style_'))['value']=='compact'
            print('PASS native publication placement selector persists Compact across replicas',flush=True)

            # Visibility and Trash operate on the live post without leaking draft text.
            from scena_publications import save_draft, publish_local, get_publication, get_draft
            pub=save_draft(os.environ['SCENA_DB_PATH'], title_ru='Visibility fixture', body_ru='Published text', body_ro='Text public', translations_approved=True)
            publish_local(os.environ['SCENA_DB_PATH'],pub['id'],pub['revision'])
            save_draft(os.environ['SCENA_DB_PATH'],pub['id'],body_ru='PRIVATE DRAFT')
            response,_=await request(path,owner=True)
            response,_=await request(path,owner=True,data=payload(response,f"№ {pub['id']} · Visibility fixture"))
            capture('owner-publication-editor',response)
            response,_=await request(path,owner=True,instance=1,data=payload(response,'Сохранить показ',{'Моя Сцена':False,'Услуги и курсы':False,'model SCENA':False}))
            assert response.code==200
            assert get_publication(os.environ['SCENA_DB_PATH'],pub['public_id']) is None
            assert get_draft(os.environ['SCENA_DB_PATH'],pub['id'])['body_ru']=='PRIVATE DRAFT'
            response,_=await request(path,owner=True,data=payload(response,'Сохранить показ',{'model SCENA':True}))
            assert get_publication(os.environ['SCENA_DB_PATH'],pub['public_id'])['body_ru']=='Published text'
            response,_=await request(path,owner=True,data=payload(response,None,{'Удалить эту публикацию в корзину':True},changed='Удалить эту публикацию в корзину'))
            response,_=await request(path,owner=True,instance=1,data=payload(response,'Удалить публикацию'))
            assert pub['id'] not in [p['id'] for p in list_publications(os.environ['SCENA_DB_PATH'])]
            response,_=await request(path,owner=True,data=payload(response,'Восстановить'))
            assert get_draft(os.environ['SCENA_DB_PATH'],pub['id'])['status']=='hidden'
            capture('owner-publication-list',response)
            print('PASS native visibility save, private draft retained, Trash and hidden restore across instances',flush=True)

            # The month calendar submits selected dates as one bounded edit.
            response,_=await request(schedule_path,owner=True)
            _,saved=form(response)
            targets=[w for w in saved['widgets'].values() if str(w.get('key','')).startswith('schedule_date_') and not w.get('disabled')][:2]
            changes={w['label']:True for w in targets}
            changes.update({'Выходной':False,'Начало работы':'10:00','Конец работы':'18:00','Добавить перерыв':True,'Перерыв с':'13:00','Перерыв до':'14:00'})
            response,_=await request(schedule_path,owner=True,instance=1,data=payload(response,'Применить к выбранным датам',changes))
            assert response.code==200
            for target in targets:
                assert len(schedule_periods(os.environ['SCENA_DB_PATH'],target['key'].removeprefix('schedule_date_')))==2
            capture('owner-calendar',response)
            print('PASS native calendar applies multiple dates and break together',flush=True)

            # A real signed fixture code goes through the same HTTP form as Production.
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives import serialization
            from scena_licensing import sign_code, owner_id
            issuer=Ed25519PrivateKey.generate()
            (fixture/'config').mkdir(exist_ok=True)
            (fixture/'config/pro-issuer-public.pem').write_bytes(issuer.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
            pro_path='/?page=admin&lang=ru&section=pro&view=subscription'
            response,_=await request(pro_path,owner=True)
            renewal=sign_code(issuer,owner_id(os.environ['SCENA_DB_PATH']),1)
            response,_=await request(pro_path,owner=True,instance=1,data=payload(response,'Активировать код',{'Код продления':renewal}))
            assert response.code==200 and 'Готово. PRO продлён до' in response.body.decode()
            response,_=await request(pro_path,owner=True,data=payload(response,'Активировать код',{'Код продления':renewal}))
            assert 'Код уже применён.' in response.body.decode()
            response,_=await request(pro_path,owner=True,data=payload(response,'Обсудить продление с SCENA'))
            assert 'Канал команды SCENA ещё не подключён.' in response.body.decode()
            assert 'view=subscription' in response.headers.get('X-Scena-URL','')
            capture('owner-pro-contact-unconfigured',response)
            print('PASS signed PRO code accepted once through HTTP; contact stays on PRO and reports missing platform channel',flush=True)

            path='/?page=admin&lang=ru&section=pages&view=scene'
            response,_=await request(path,owner=True)
            _,saved=form(response)
            print('SCENE BUTTONS',[w['label'] for w in saved['widgets'].values() if w['kind']=='button'],flush=True)
            save_label=next(w['label'] for w in saved['widgets'].values() if w['kind']=='button' and 'Сохранить' in w['label'] and 'фотограф' not in w['label'])
            scene_copy={'ru':'Макияж <для вас>\nВыберите удобное время.',
                        'ro':'Machiaj pentru tine.\nAlege ora potrivită.',
                        'en':'Makeup for you.\nChoose a convenient time.'}
            scene_titles={'ru':'Макияж и <обучение>', 'ro':'Machiaj și instruire', 'en':'Makeup and lessons'}
            data=payload(response,save_label,{'Имя и фамилия · RU':'Native acceptance owner',
                'Текст кнопки · RU':'Изучить мои услуги',
                **{'Заголовок блока услуг · '+lang.upper():value for lang,value in scene_titles.items()},
                **{'Описание услуг перед кнопкой · '+lang.upper():value for lang,value in scene_copy.items()}})
            saved_response,_=await request(path,owner=True,data=data,instance=1)
            assert saved_response.code==200,saved_response.body
            from scena_core import get_settings
            assert get_settings(os.environ['SCENA_DB_PATH'])['master_name_ru']=='Native acceptance owner','Profile save failed across instances'
            from html import escape
            for lang,text in scene_copy.items():
                assert get_settings(os.environ['SCENA_DB_PATH'])['scene_services_text_'+lang]==text
                assert get_settings(os.environ['SCENA_DB_PATH'])['scene_services_title_'+lang]==scene_titles[lang]
                public,_=await request('/?page=scene&lang='+lang,instance=1)
                assert '<div class="scene-service-intro"><p>'+escape(text)+'</p></div>' in public.body.decode()
                assert '<h2 id="scene-services-title" class="scene-section-title">'+escape(scene_titles[lang])+'</h2>' in public.body.decode()
            duplicate,_=await request(path,owner=True,data=data)
            assert duplicate.code==409,'Duplicate action was accepted'
            print('PASS profile save across instances; duplicate rejected',flush=True)
            reloaded,_=await request(path,owner=True)
            _,saved=form(reloaded)
            for lang,text in scene_copy.items():
                field=next(w for w in saved['widgets'].values() if w['label']=='Описание услуг перед кнопкой · '+lang.upper())
                assert field['value']==text
                title_field=next(w for w in saved['widgets'].values() if w['label']=='Заголовок блока услуг · '+lang.upper())
                assert title_field['value']==scene_titles[lang]
            invalid=payload(reloaded,save_label,{'Описание услуг перед кнопкой · RO':''})
            rejected,_=await request(path,owner=True,data=invalid,instance=1)
            assert rejected.code==200 and 'Для описания услуг заполните версии RU/RO.' in rejected.body.decode()
            assert get_settings(os.environ['SCENA_DB_PATH'])['scene_services_text_ro']==scene_copy['ro']
            incomplete_title=payload(rejected,save_label,{'Описание услуг перед кнопкой · RO':scene_copy['ro'], 'Заголовок блока услуг · RO':''})
            rejected,_=await request(path,owner=True,data=incomplete_title,instance=1)
            assert rejected.code==200 and 'Для заголовка услуг заполните версии RU/RO.' in rejected.body.decode()
            assert get_settings(os.environ['SCENA_DB_PATH'])['scene_services_title_ro']==scene_titles['ro']
            cleared,_=await request(path,owner=True,data=payload(rejected,save_label,
                {**{'Описание услуг перед кнопкой · '+lang.upper():'' for lang in scene_copy},
                 **{'Заголовок блока услуг · '+lang.upper():'' for lang in scene_titles}}),instance=1)
            assert cleared.code==200
            public,_=await request('/?page=scene&lang=ru')
            assert 'class="scene-service-intro"' not in public.body.decode()
            assert 'id="scene-services-title"' not in public.body.decode()
            assert '>Изучить мои услуги</a>' in public.body.decode()
            print('PASS owner service heading and intro saved/reloaded in RU/RO/EN; incomplete translations rejected; clear hides both and preserves custom CTA',flush=True)
            # A multipart-size image is uploaded in independent chunks, then a
            # different instance saves it through the existing image validator.
            from PIL import Image
            image=Image.frombytes('RGB',(1200,1000),os.urandom(3600000));buffer=io.BytesIO();image.save(buffer,format='PNG');image_data=buffer.getvalue()
            response,_=await request(path,owner=True)
            token,saved=form(response)
            upload_id=next(k for k,w in saved['widgets'].items() if w['kind']=='file')
            upload_widget=saved['widgets'][upload_id]
            save_upload=next(w['label'] for w in saved['widgets'].values() if w['kind']=='button' and w['group']==upload_widget['group'])
            refs=[]
            for index,offset in enumerate(range(0,len(image_data),3*1024*1024)):
                instance=index%2
                chunk=await client.fetch(HTTPRequest(urls[instance]+'/scena-upload',method='POST',headers={'Cookie':cookie,'Origin':urls[instance],'X-Scena-Form':token,'X-Scena-Field':upload_id,'Content-Type':'application/octet-stream'},body=image_data[offset:offset+3*1024*1024]),raise_error=False)
                assert chunk.code==200,chunk.body
                refs.append(json.loads(chunk.body)['id'])
            data=payload(response,save_upload)
            data['_upload_'+upload_id]=json.dumps([{'refs':refs,'name':'acceptance.png','mime':'image/png','size':len(image_data)}])
            uploaded,_=await request(path,owner=True,data=data,instance=1)
            assert uploaded.code==200,uploaded.body
            settings=get_settings(os.environ['SCENA_DB_PATH'])
            from scena_web.storage import read_binary
            assert b''.join(read_binary(ref,sid) for ref in refs)==image_data,'Upload chunks changed'
            with Image.open(fixture/settings['avatar_url']) as saved_image:
                assert saved_image.size==(1200,1000) and saved_image.format=='WEBP'
            print('PASS image >3MB uploaded across instances and saved by existing image pipeline',flush=True)
            # Save two extra photos through separate registered upload fields.
            from scena_shop import PRODUCT_FIELDS, save_product, get_product, list_orders
            tiny=io.BytesIO();Image.new('RGB',(600,700),'tan').save(tiny,format='PNG');photo=tiny.getvalue()
            product=save_product(os.environ['SCENA_DB_PATH'],fixture,
                {**{key:'Gallery fixture '+key for key in PRODUCT_FIELDS},'price':'100','status':'published'},upload=photo)
            market='/?page=admin&lang=ru&section=pages&view=shop'
            response,_=await request(market,owner=True)
            response,_=await request(market,owner=True,data=payload(response,None,{'Какой товар редактируем?':product['id']},changed='Какой товар редактируем?'))
            token,saved=form(response);data=payload(response,'Сохранить товар')
            for number in (2,3):
                identity=next(k for k,w in saved['widgets'].items() if w['kind']=='file' and w['label']==f'Фото {number} — дополнительно')
                chunk=await client.fetch(HTTPRequest(urls[0]+'/scena-upload',method='POST',headers={'Cookie':cookie,'Origin':urls[0],'X-Scena-Form':token,'X-Scena-Field':identity,'Content-Type':'application/octet-stream'},body=photo),raise_error=False)
                assert chunk.code==200,chunk.body
                data['_upload_'+identity]=json.dumps([{'refs':[json.loads(chunk.body)['id']],'name':f'extra{number}.png','mime':'image/png','size':len(photo)}])
            response,_=await request(market,owner=True,data=data,instance=1)
            assert response.code==200,response.body
            updated=get_product(os.environ['SCENA_DB_PATH'],product['id'])
            assert len({updated[key] for key in ('image','image_2','image_3')})==3
            for key in ('image','image_2','image_3'):assert (fixture/updated[key]).read_bytes()==photo
            shop,_=await request('/?page=shop&lang=ru')
            assert b'shop-gallery-compact' in shop.body and b'data-shop-gallery' in shop.body and b'1 / 3' in shop.body
            print('PASS native owner uploads 3 photos across instances; compact public gallery retains originals',flush=True)
            # Bind only the fixture owner's Telegram and intercept all bot calls.
            import scena_shop_telegram as tg
            bot_token='123456789:'+('a'*32)
            save_settings(os.environ['SCENA_DB_PATH'],{'telegram_url':'@fixtureowner'})
            with patch.dict(os.environ,{'SCENA_TELEGRAM_CREDENTIAL_KEY':'native-fixture-only-key'}):
                response,_=await request(market,owner=True)
                with patch.object(tg.TelegramBotAdapter,'_call',return_value={'is_bot':True,'username':'FixtureBot'}):
                    response,_=await request(market,owner=True,data=payload(response,'Получить код подключения',{'Токен бота из @BotFather':bot_token}))
                assert response.code==200 and bot_token.encode() not in response.body,response.body
                pending=tg.connection_status(os.environ['SCENA_DB_PATH'])['pending']
                update=[{'message':{'text':pending['code'],'date':time.time(),'chat':{'id':501,'type':'private','username':'fixtureowner'},'from':{'id':501,'is_bot':False}}}]
                with patch.object(tg.TelegramBotAdapter,'_call',return_value=update):
                    response,_=await request(market,owner=True,data=payload(response,'Код отправлен — подключить Telegram'))
                assert response.code==200 and tg.connection_status(os.environ['SCENA_DB_PATH'])['connected']
                # Activate through an owner POST, with every Telegram call intercepted.
                save_settings(os.environ['SCENA_DB_PATH'],{'public_base_url':'https://scena.example'})
                with patch.object(tg.TelegramBotAdapter,'_call',side_effect=[{'url':''},True,{'url':'https://scena.example/scena-telegram'}]):
                    response,_=await request(market,owner=True,data=payload(response,'Включить кнопки в Telegram'))
                assert response.code==200 and tg.connection_status(os.environ['SCENA_DB_PATH'])['actions_ready']
                shop,_=await request('/?page=shop&lang=ru',data=payload(shop,'В корзину'))
                shop,_=await request('/?page=shop&lang=ru',data=payload(shop,'Перейти к оформлению'))
                shop,_=await request('/?page=shop&lang=ru',data=payload(shop,'Проверить заказ',{'Ваше имя':'Fixture buyer','Телефон':'+37360000111','Согласна на обработку контактов для этого заказа':True}))
                data=payload(shop,'Подтвердить заказ')
                with patch.object(tg.TelegramBotAdapter,'_call',return_value={'message_id':123}) as sender:
                    receipt,_=await request('/?page=shop&lang=ru',data=data,instance=1)
                assert receipt.code==200,receipt.body
                sender.assert_called_once()
                assert sender.call_args.args[0]=='sendMessage' and sender.call_args.args[1]['chat_id']=='501'
                assert list_orders(os.environ['SCENA_DB_PATH'])[0]['telegram_status']=='sent'
                cabinet_orders,_=await request(market,owner=True)
                assert 'href="tel:+37360000111"' in cabinet_orders.body.decode()
                assert 'scena-order-products' in cabinet_orders.body.decode()
                assert 'Телефон: +37360000111' in sender.call_args.args[1]['text']
                order=list_orders(os.environ['SCENA_DB_PATH'])[0]
                assert order['items'][0]['name_ru'] in cabinet_orders.body.decode()
                capture('owner-order-list',cabinet_orders)
                buttons=sender.call_args.args[1]['reply_markup']['inline_keyboard']
                assert [row[0]['text'] for row in buttons]==['Открыть заказ','Сменить статус']
                direct=tg.order_path(order['id'])
                anonymous,_=await request(direct)
                from urllib.parse import parse_qs, urlsplit
                assert anonymous.code==302 and parse_qs(urlsplit(anonymous.headers['Location']).query)['next']==[direct]
                # Login page retains the exact order destination.
                login,_=await request(anonymous.headers['Location'])
                import html
                assert direct in html.unescape(login.body.decode())
                focused,_=await request(direct,owner=True,instance=1)
                assert focused.code==200 and order['reference'] in focused.body.decode()
                assert 'st-key-scena_request_card' in focused.body.decode()
                assert 'shop_product_editor_' not in focused.body.decode()
                assert 'Все заказы' in focused.body.decode()
                capture('owner-order-card',focused)
                with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as refresh:
                    refreshed,_=await request(direct,owner=True,data=payload(focused,'Обновить карточку в Telegram'),instance=1)
                assert refreshed.code==200 and 'Карточка в Telegram обновлена.' in refreshed.body.decode()
                refresh.assert_called_once()
                assert refresh.call_args.args[0]=='editMessageText'
                assert list_orders(os.environ['SCENA_DB_PATH'])[0]['revision']==1
                all_orders,_=await request(market+'&orders=1',owner=True)
                assert re.search(r'role="tab"[^>]*aria-selected="true"[^>]*>Заказы</button>',all_orders.body.decode())
                config=tg._load(os.environ['SCENA_DB_PATH'])
                update={'update_id':51,'callback_query':{'id':'fixture-action','from':{'id':501,'is_bot':False},
                    'message':{'message_id':123,'chat':{'id':501,'type':'private'}},'data':buttons[1][0]['callback_data']}}
                async def webhook(secret,body,instance=0):
                    return await client.fetch(HTTPRequest(urls[instance]+'/scena-telegram',method='POST',
                        headers={'Content-Type':'application/json','X-Telegram-Bot-Api-Secret-Token':secret},
                        body=body,request_timeout=40),raise_error=False)
                with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as calls:
                    forbidden=await webhook('wrong-secret',json.dumps(update))
                    assert forbidden.code==403
                    calls.assert_not_called()
                    malformed=await webhook(config['webhook_secret'],'[]')
                    assert malformed.code==400
                    assert (await webhook(config['webhook_secret'],json.dumps(update))).code==200
                    assert list_orders(os.environ['SCENA_DB_PATH'])[0]['revision']==1
                    menu=next(c.args[1] for c in calls.call_args_list if c.args[0]=='editMessageText')
                    update['callback_query']['data']=next(b['callback_data'] for line in menu['reply_markup']['inline_keyboard'] for b in line if b['text']=='Связались')
                    assert (await webhook(config['webhook_secret'],json.dumps(update))).code==200
                    assert (await webhook(config['webhook_secret'],json.dumps(update),instance=1)).code==200
                updated=list_orders(os.environ['SCENA_DB_PATH'])[0]
                assert updated['status']=='contacted' and updated['revision']==2
                focused,_=await request(direct,owner=True)
                assert 'Связались' in focused.body.decode() and 'tel:+37360000111' in focused.body.decode()
                saved_order,_=await request(direct,owner=True,data=payload(focused,'Сохранить статус'),instance=1)
                assert saved_order.code==200 and 'st-key-scena_request_card' in saved_order.body.decode()
                assert list_orders(os.environ['SCENA_DB_PATH'])[0]['status']=='contacted'
                for locale in ('ru','ro','en'):
                    screen,_=await request(tg.order_path(order['id'],locale),owner=True)
                    capture('order-'+locale,screen)
                missing,_=await request(tg.order_path('00000000-0000-0000-0000-000000000000'),owner=True)
                assert missing.code==200 and order['reference'] not in missing.body.decode()
                duplicate,_=await request('/?page=shop&lang=ru',data=data)
                assert duplicate.code==409
            print('PASS native Telegram binding and checkout: one committed order, one lead to verified owner',flush=True)
            print('PASS Telegram owner callback across replicas, duplicate idempotency, direct order/login destination and selected Orders tab',flush=True)
            # Create a public inquiry; do not call any configured external sender.
            inquiry='/?page=join-model&lang=ru'
            response,_=await request(inquiry)
            _,saved=form(response)
            print('INQUIRY FIELDS',[(w['kind'],w['label']) for w in saved['widgets'].values()],flush=True)
            changes={w['label']:True for w in saved['widgets'].values() if w['kind']=='bool'}
            for w in saved['widgets'].values():
                if w['kind']=='text' and ('имя' in w['label'].lower() or 'name' in w['label'].lower()):changes[w['label']]='Acceptance client'
                if w['kind']=='text' and 'телефон' in w['label'].lower():changes[w['label']]='+37360000111'
            button=next(w['label'] for w in saved['widgets'].values() if w['kind']=='button')
            accepted,_=await request(inquiry,data=payload(response,button,changes),instance=1)
            assert accepted.code==200,accepted.body
            from scena_database import connect
            with connect(os.environ['SCENA_DB_PATH']) as db:
                assert db.execute("SELECT COUNT(*) FROM requests WHERE name='Acceptance client'").fetchone()[0]==1,'Public request missing'
            print('PASS public request saved once and visible to cabinet database',flush=True)
            path='/?page=booking&lang=ru'
            booking,_=await request(path)
            _,saved=form(booking)
            choices=[w for w in saved['widgets'].values() if w['kind']=='choice']
            service=next(w for w in choices if w['key']=='booking_service')
            booking,_=await request(path,data=payload(booking,None,{service['label']:service['options'][0]},changed=service['label']),instance=1)
            assert booking.code==200
            for move in range(5):
                _,saved=form(booking)
                slots=[w for w in saved['widgets'].values() if w['kind']=='button' and str(w.get('key','')).startswith('booking_slot_') and not w.get('disabled')]
                if slots:break
                days=[w for w in saved['widgets'].values() if w['kind']=='button' and str(w.get('key','')).startswith('booking_day_') and not w.get('disabled')]
                assert days,'No available booking date'
                booking,_=await request(path,data=payload(booking,days[min(move,len(days)-1)]['label']),instance=move%2)
            assert slots,'No available slot'
            booking,_=await request(path,data=payload(booking,slots[0]['label']),instance=1)
            booking,_=await request(path,data=payload(booking,'Продолжить'))
            _,saved=form(booking)
            changes={w['label']:True for w in saved['widgets'].values() if w['kind']=='bool'}
            for w in saved['widgets'].values():
                if w['kind']=='text' and 'имя' in w['label'].lower():changes[w['label']]='Acceptance booking'
                if w['kind']=='text' and 'телефон' in w['label'].lower():changes[w['label']]='+37360000222'
            submit=next(w['label'] for w in saved['widgets'].values() if w['kind']=='button' and w['group'])
            channel=next(w for w in saved['widgets'].values() if w.get('key')=='booking_contact_channel')
            telegram_field=next(w for w in saved['widgets'].values() if w.get('key')=='booking_contact_telegram')
            assert channel['options']==['phone','telegram','sms','email']
            changes[channel['label']]='telegram'
            import scena_service_telegram as service_tg
            with patch.dict(os.environ,{'SCENA_TELEGRAM_CREDENTIAL_KEY':'native-fixture-only-key'}):
                with patch.object(tg.TelegramBotAdapter,'_call',return_value={'message_id':301}) as sender:
                    invalid,_=await request(path,data=payload(booking,submit,changes))
                    assert invalid.code==200 and 'укажите ваш @username' in invalid.body.decode()
                    sender.assert_not_called()
                    changes[telegram_field['label']]='@bookingclient'
                    submitted_data=payload(invalid,submit,changes)
                    booked,_=await request(path,data=submitted_data,instance=1)
                sender.assert_called_once()
                assert sender.call_args.args[0]=='sendMessage'
                lead=sender.call_args.args[1]
                assert lead['chat_id']=='501' and 'Ответить в Telegram: @bookingclient' in lead['text']
                with connect(os.environ['SCENA_DB_PATH']) as db:
                    identity=db.execute("SELECT id FROM requests WHERE name='Acceptance booking'").fetchone()[0]
                    assert db.execute('SELECT contact_telegram FROM requests WHERE id=?',(identity,)).fetchone()[0]=='@bookingclient'
                    assert db.execute('SELECT COUNT(*) FROM sms_outbox WHERE request_id=?',(identity,)).fetchone()[0]==0
                direct=service_tg.request_path(identity)
                anonymous,_=await request(direct)
                assert anonymous.code==302 and parse_qs(urlsplit(anonymous.headers['Location']).query)['next']==[direct]
                focused,_=await request(direct,owner=True,instance=1)
                assert focused.code==200 and 'https://t.me/bookingclient' in focused.body.decode()
                assert 'tel:+37360000222' in focused.body.decode() and 'Все заявки' in focused.body.decode()
                assert len(re.findall(r'data-form-key="request_status_',focused.body.decode()))==1
                assert 'request-contact' in focused.body.decode()
                assert 'st-key-scena_request_card' in focused.body.decode()
                assert '<nav class="scena-admin-tabs">' not in focused.body.decode()
                assert 'Полная таблица заявок' not in focused.body.decode()
                assert 'Acceptance client' not in focused.body.decode()
                missing,_=await request(service_tg.request_path(999999999),owner=True)
                assert 'Заявка не найдена.' in missing.body.decode()
                assert 'Acceptance booking' not in missing.body.decode()
                for locale in ('ro','en'):
                    translated,_=await request(service_tg.request_path(identity,locale),owner=True)
                    assert translated.code==200 and 'st-key-scena_request_card' in translated.body.decode()
                    capture('request-'+locale,translated)
                capture('request-ru',focused)
                saved_status,_=await request(direct,owner=True,data=payload(focused,'Сохранить статус'),instance=0)
                assert saved_status.code==200 and 'Статус заявки обновлён.' in saved_status.body.decode()
                assert 'st-key-scena_request_card' in saved_status.body.decode()
                focused,_=await request(direct,owner=True)
                print('PASS compact request: isolated record, missing ID, RU/RO/EN and save stays on card',flush=True)
                with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as refresh:
                    refreshed,_=await request(direct,owner=True,data=payload(focused,'Обновить карточку в Telegram'),instance=1)
                assert refreshed.code==200 and 'Карточка в Telegram обновлена.' in refreshed.body.decode()
                refresh.assert_called_once()
                assert refresh.call_args.args[0]=='editMessageText'
                contact=next(b['callback_data'] for line in lead['reply_markup']['inline_keyboard'] for b in line if b['text']=='Сменить статус')
                update={'update_id':52,'callback_query':{'id':'service-contact','from':{'id':501,'is_bot':False},
                    'message':{'message_id':301,'chat':{'id':501,'type':'private'}},'data':contact}}
                config=tg._load(os.environ['SCENA_DB_PATH'])
                with patch.object(tg.TelegramBotAdapter,'_call',return_value=True) as api:
                    assert (await webhook(config['webhook_secret'],json.dumps(update))).code==200
                    async def press(label):
                        edited=[c.args[1] for c in api.call_args_list if c.args[0]=='editMessageText'][-1]
                        update['callback_query']['data']=next(b['callback_data'] for line in edited['reply_markup']['inline_keyboard'] for b in line if b['text']==label)
                        assert (await webhook(config['webhook_secret'],json.dumps(update),instance=1)).code==200
                    await press('Связались')
                    await press('Сменить статус')
                    await press('Подтверждена')
                    assert (await webhook(config['webhook_secret'],json.dumps(update))).code==200
                with connect(os.environ['SCENA_DB_PATH']) as db:
                    assert tuple(db.execute('SELECT status,revision FROM requests WHERE id=?',(identity,)).fetchone())==('Подтверждена',3)
                for method,extra,expected in [('sms','', 'sms:+37360000222'),('email','client@example.com','mailto:client@example.com')]:
                    with connect(os.environ['SCENA_DB_PATH']) as db:
                        db.execute('UPDATE requests SET contact_channel=?,email=? WHERE id=?',(method,extra,identity))
                    view,_=await request(direct,owner=True)
                    assert expected in view.body.decode()
                duplicate,_=await request(path,data=submitted_data)
                assert duplicate.code==409
            assert booked.code==200
            with connect(os.environ['SCENA_DB_PATH']) as db:
                assert db.execute("SELECT COUNT(*) FROM requests WHERE name='Acceptance booking'").fetchone()[0]==1,'Booking missing'
            assert 'Спасибо!' in booked.body.decode(),'Booking receipt missing'
            for locale in ('ru','ro','en'):
                for name,path in [('overview','/?page=admin&section=work&view=overview'),('requests','/?page=admin&section=work&view=requests'),('orders','/?page=admin&section=pages&view=shop&orders=1')]:
                    screen,_=await request(path+'&lang='+locale,owner=True)
                    assert screen.code==200
                    capture(name+'-'+locale,screen)
            print('PASS service/date/time/contact/confirmation booking across instances',flush=True)
            print('PASS service lead to shared bot, selected channel validation, Telegram/SMS/email/phone reply links, direct owner access and two idempotent status actions',flush=True)
            path='/?page=admin&lang=ru&section=settings&view=backup'
            response,_=await request(path,owner=True)
            backup,_=await request(path,owner=True,data=payload(response,'Создать резервную копию'),instance=1)
            assert backup.code==200,backup.body
            print('BACKUP NOTICES',re.findall(r'<div class="scena-notice[^>]*>(.*?)</div>',backup.body.decode()),flush=True)
            download=re.search(r'href="(/scena-download/[^" ]+)"',backup.body.decode())[1].replace('&amp;','&')
            downloaded,_=await request(download,owner=True)
            assert downloaded.code==200
            from scena_transfer import inspect_backup
            assert inspect_backup(downloaded.body)['kind']=='private_backup'
            denied,_=await request(download)
            assert denied.code==401,'Private download exposed'
            print('PASS portable private backup/download across instances; anonymous access denied',flush=True)
        finally:
            for server in servers:server.stop()
            for server in servers:await server.close_all_connections()
    print('NATIVE HTTP ACCEPTANCE PASSED')

if __name__=='__main__':asyncio.run(main())
