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
        sid='fixture-browser-identity-'+'a'*20
        cookie=COOKIE+'='+make_session()+'; '+BROWSER_COOKIE+'='+sid
        async def request(path,*,owner=False,data=None,instance=0,headers=None):
            start=time.monotonic()
            h={'Cookie':cookie if owner else BROWSER_COOKIE+'='+sid,**(headers or {})}
            if data is not None:h.update({'Origin':urls[instance],'Content-Type':'application/x-www-form-urlencoded'})
            response=await client.fetch(HTTPRequest(urls[instance]+path,method='POST' if data is not None else 'GET',headers=h,body=urlencode(data,doseq=True) if data is not None else None,follow_redirects=False,request_timeout=40),raise_error=False)
            return response,round((time.monotonic()-start)*1000)
        failures=[]
        try:
            for page in ('scene','portfolio','professional','model','booking','course','join-model','invite-model','post','posts','shop'):
                response,elapsed=await request('/?page='+page+'&lang=ru')
                print('PUBLIC',page,response.code,elapsed,len(response.body),flush=True)
                if response.code!=200:failures.append(page)
                else:assert b'data-scena-runtime="native-html"' in response.body
            response,_=await request('/?page=admin',headers={'X-Scena-Session':make_session()})
            assert response.code==302,'Spoofed auth header accepted'
            import scena_app
            for section,views in scena_app.ADMIN_VIEWS.items():
                for view in views:
                    response,elapsed=await request('/?page=admin&lang=ru&section='+section+'&view='+view,owner=True)
                    print('CABINET',section,view,response.code,elapsed,len(response.body),flush=True)
                    if response.code!=200:failures.append(section+'/'+view)
                    assert 'Vercel-CDN-Cache-Control' not in response.headers
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

            path='/?page=admin&lang=ru&section=pages&view=scene'
            response,_=await request(path,owner=True)
            _,saved=form(response)
            print('SCENE BUTTONS',[w['label'] for w in saved['widgets'].values() if w['kind']=='button'],flush=True)
            save_label=next(w['label'] for w in saved['widgets'].values() if w['kind']=='button' and 'Сохранить' in w['label'] and 'фотограф' not in w['label'])
            data=payload(response,save_label,{'Имя и фамилия · RU':'Native acceptance owner'})
            saved_response,_=await request(path,owner=True,data=data,instance=1)
            assert saved_response.code==200,saved_response.body
            from scena_core import get_settings
            assert get_settings(os.environ['SCENA_DB_PATH'])['master_name_ru']=='Native acceptance owner','Profile save failed across instances'
            duplicate,_=await request(path,owner=True,data=data)
            assert duplicate.code==409,'Duplicate action was accepted'
            print('PASS profile save across instances; duplicate rejected',flush=True)
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
            booked,_=await request(path,data=payload(booking,submit,changes),instance=1)
            assert booked.code==200
            with connect(os.environ['SCENA_DB_PATH']) as db:
                assert db.execute("SELECT COUNT(*) FROM requests WHERE name='Acceptance booking'").fetchone()[0]==1,'Booking missing'
            assert 'Спасибо!' in booked.body.decode(),'Booking receipt missing'
            print('PASS service/date/time/contact/confirmation booking across instances',flush=True)
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
