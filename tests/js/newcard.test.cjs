// Tests the actual compiled React bundle in a DOM; not a browser/device test.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');
const root=path.join(__dirname,'../../public/newcard');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const scriptPath=html.match(/<script src="\/newcard\/([^"?]+)"/)[1];
const script=fs.readFileSync(path.join(root,scriptPath),'utf8');
const settle=()=>new Promise(resolve=>setTimeout(resolve,100));
async function until(predicate){for(let i=0;i<60;i++){if(predicate())return;await settle();}assert.ok(predicate(),'Expected state did not arrive');}

async function setup(t,hash='',draft=null,localResponder=null){
  const errors=[];
  const console=new VirtualConsole();
  console.on('jsdomError',error=>errors.push(error));
  const dom=new JSDOM(html,{url:'https://scena.test/newcard'+hash,runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:console});
  const w=dom.window,d=w.document,requests=[],downloads=[],blobs=[];
  if(draft)w.localStorage.setItem('scena-personal-card-v1',JSON.stringify(draft));
  w.URL.createObjectURL=blob=>{blobs.push(blob);return 'blob:test-'+blobs.length;};w.URL.revokeObjectURL=()=>{};
  d.addEventListener('click',e=>{const a=e.target.closest('a[download]');if(a){e.preventDefault();downloads.push(a.download);}});
  w.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}});
  w.IntersectionObserver=class{observe(){}disconnect(){}};
  w.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};
  w.scrollTo=()=>{};
  w.HTMLElement.prototype.scrollIntoView=function(){};
  w.fetch=async(url,options={})=>{
    requests.push({url,method:options.method||'GET'});
    if(options.method==='POST'&&localResponder)return localResponder(url,options);
    if(String(url).endsWith('.woff2'))return {ok:true,blob:async()=>new w.Blob([fs.readFileSync(path.join(__dirname,'../../public/card/assets/manrope-regular.woff2'))])};
    assert.equal(url,'/api/intake/status','No external submission or upload is allowed in these tests');
    assert.equal(options.method,undefined);
    return {json:async()=>({ready:true})};
  };
  w.eval(script);
  await until(()=>d.querySelector('.cover'));
  if(hash==='#anketa')await until(()=>d.getElementById('name'));else await settle();
  t.after(()=>{dom.window.close();assert.deepEqual(errors,[],'No React/DOM errors');});
  const click=async element=>{assert.ok(element,'Expected control exists');element.focus();element.click();await settle();};
  const button=text=>[...d.querySelectorAll('button')].find(b=>b.textContent.trim()===text);
  const field=async(id,value)=>{
    const input=d.getElementById(id);
    Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value').set.call(input,value);
    input.dispatchEvent(new w.Event('input',{bubbles:true}));await settle();
  };
  const choose=async(name,value)=>{const radio=[...d.querySelectorAll('input[type=radio]')].find(i=>i.name===name&&i.value===value);await click(radio);};
  const readBlob=blob=>new Promise(resolve=>{const r=new w.FileReader();r.onload=()=>resolve(r.result);r.readAsText(blob);});
  return {w,d,click,button,field,choose,requests,downloads,blobs,readBlob};
}


async function identity(ui,name='Алина',role='Визажист'){await ui.field('name',name);await ui.choose('specialty',role);}
async function final(ui){await identity(ui);await ui.click(ui.button('Выбрать фотографию'));await ui.click(ui.button('Продолжить без фото'));await ui.click(ui.button('Увидеть свою визитку'));}

test('cover does not steal focus; direct example and form entry focus the destination',async t=>{
 const ui=await setup(t);assert.equal(ui.d.activeElement.tagName,'BODY');
 const example=await setup(t,'#example');await until(()=>example.d.activeElement.id==='example-title');
 const form=await setup(t,'#anketa');assert.equal(form.d.activeElement.id,'anketa');
});
test('required name and role block progress and focus a readable error',async t=>{
 const ui=await setup(t,'#anketa');await ui.click(ui.button('Выбрать фотографию'));
 assert.equal(ui.d.activeElement.id,'name');assert.equal(ui.d.getElementById('name').getAttribute('aria-describedby'),'name-error');
 await ui.field('name','Алина');await ui.click(ui.button('Выбрать фотографию'));
 assert.equal(ui.d.activeElement.id,'specialty');assert.equal(ui.d.getElementById('specialty').getAttribute('aria-invalid'),'true');assert.equal(ui.d.querySelectorAll('[aria-current=step]').length,1);
});
test('all four steps work without a photo, contact or submission; booking and setup are absent',async t=>{
 const ui=await setup(t,'#anketa');await final(ui);
 assert.match(ui.d.getElementById('journey-title').textContent,/Это вы/);
 assert.ok(ui.button('Сохранить визитку · PNG'));assert.ok(ui.button('Скачать живую визитку · HTML'));
 assert.equal(ui.d.querySelector('.card-journey .personal-card-copy h3').textContent,'Алина');
 assert.equal(ui.d.querySelectorAll('.journey-progress .lucide-check').length,3);
 assert.doesNotMatch(ui.d.querySelector('.card-journey').textContent,/Запись на услуги|GitHub|Vercel|Магазин/);
 assert.deepEqual(ui.requests,[]);
});
test('model and custom direction appear verbatim; switching to another role removes the custom field',async t=>{
 const ui=await setup(t,'#anketa');await identity(ui,'Лилия','Модель');
 assert.equal(ui.d.querySelector('.card-journey .personal-card-profession').textContent,'Модель');
 await ui.choose('specialty','Своё направление');await ui.click(ui.button('Выбрать фотографию'));assert.equal(ui.d.activeElement.id,'customSpecialty');
 await ui.field('customSpecialty','Фотограф');assert.equal(ui.d.querySelector('.card-journey .personal-card-profession').textContent,'Фотограф');
 await ui.choose('specialty','Стилист');assert.equal(ui.d.getElementById('customSpecialty'),null);assert.equal(ui.d.querySelector('.card-journey .personal-card-profession').textContent,'Стилист');
});
test('invalid contact expands and stays open while typing; corrected contact flips with keyboard recovery',async t=>{
 const ui=await setup(t,'#anketa');await identity(ui);await ui.click(ui.d.querySelector('[aria-label^="Шаг 3:"]'));
 const detail=ui.d.querySelector('.journey-details');detail.open=true;
 await ui.field('contact','javascript:alert(1)');await ui.click(ui.button('Увидеть свою визитку'));
 assert.equal(detail.open,true);assert.equal(ui.d.activeElement.id,'contact');assert.ok(ui.d.getElementById('contact-error'));
 await ui.field('contact','@alina.makeup');assert.equal(detail.open,true,'Disclosure must stay open while correcting input');
 await ui.click(ui.button('Увидеть свою визитку'));await ui.click(ui.d.querySelector('[data-card-action=contact]'));
 assert.equal(ui.d.querySelector('.card-journey .personal-card-back').hidden,false);assert.equal(ui.d.activeElement.dataset.cardAction,'front');
 assert.equal(ui.d.querySelector('.card-journey .personal-card-back a').href,'https://www.instagram.com/alina.makeup/');
 ui.d.activeElement.dispatchEvent(new ui.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await settle();
 assert.equal(ui.d.querySelector('.card-journey .personal-card-back').hidden,true);assert.equal(ui.d.activeElement.dataset.cardAction,'contact');
});
test('mood changes the actual card; persisted progress and photo survive restore',async t=>{
 const ui=await setup(t,'#anketa');await identity(ui);await ui.click(ui.button('Выбрать фотографию'));await ui.click(ui.button('Продолжить без фото'));
 await ui.choose('theme','wine');assert.equal(ui.d.querySelector('.card-journey .personal-card').dataset.theme,'wine');
 await ui.click(ui.button('Увидеть свою визитку'));await new Promise(r=>setTimeout(r,350));
 const saved=JSON.parse(ui.w.localStorage.getItem('scena-personal-card-v1'));assert.deepEqual(saved.completed,[0,1,2]);
 saved.draft.photo='data:image/jpeg;base64,/9j/2Q==';
 const again=await setup(t,'',saved);await again.click(again.d.querySelector('.cover-actions a[href="#anketa"]'));await until(()=>again.d.querySelector('.journey-progress'));
 assert.equal(again.d.querySelectorAll('.journey-progress .lucide-check').length,3);assert.equal(again.d.querySelector('.card-journey .personal-card img').src,saved.draft.photo);
 assert.equal(again.d.querySelector('.card-journey .personal-card').dataset.theme,'wine');
});
test('invalidated name loses its completion and cannot jump to the final step',async t=>{
 const ui=await setup(t,'#anketa');await final(ui);await ui.click(ui.d.querySelector('[aria-label^="Шаг 1:"]'));await ui.field('name','');
 assert.equal(ui.d.querySelector('[aria-label^="Шаг 1:"] .lucide-check'),null);
 await ui.click(ui.d.querySelector('[aria-label^="Шаг 4:"]'));assert.equal(ui.d.activeElement.id,'name');
});
test('Back and Forward retain answers and return focus to the actual opener',async t=>{
 const ui=await setup(t);const opener=ui.d.querySelector('.cover-actions a[href="#anketa"]');await ui.click(opener);await ui.field('name','Лилия');
 ui.w.history.back();await until(()=>!ui.d.querySelector('.cover').hidden);assert.equal(ui.d.activeElement,opener);
 ui.w.history.forward();await until(()=>ui.d.querySelector('.cover').hidden);assert.equal(ui.d.getElementById('name').value,'Лилия');assert.equal(ui.d.activeElement.id,'anketa');
});
test('downloaded HTML contains the personal card, safe text and functioning contact; no booking or external assets',async t=>{
 const ui=await setup(t,'#anketa');await identity(ui,'<Алина>');await ui.click(ui.d.querySelector('[aria-label^="Шаг 3:"]'));ui.d.querySelector('.journey-details').open=true;await ui.field('contact','@alina.makeup');await ui.click(ui.button('Увидеть свою визитку'));
 await ui.click(ui.button('Скачать живую визитку · HTML'));await until(()=>ui.downloads.length>0);
 assert.deepEqual(ui.downloads,['My-SCENA.html']);const content=await ui.readBlob(ui.blobs[0]);
 const exported=new JSDOM(content,{runScripts:'dangerously'});t.after(()=>exported.window.close());
 const doc=exported.window.document;assert.equal(doc.querySelector('.personal-card-copy h3').textContent,'<Алина>');assert.equal(doc.querySelectorAll('script').length,1);assert.equal(doc.querySelectorAll('script[src],link[rel=stylesheet],img[src^="http"]').length,0);
 doc.querySelector('[data-card-action=contact]').click();assert.equal(doc.querySelector('.personal-card-back').hidden,false);assert.equal(doc.querySelector('.personal-card-back a').href,'https://www.instagram.com/alina.makeup/');
 assert.doesNotMatch(content,/Запись на услуги|api\/intake/);assert.equal(doc.getElementsByTagName("алина").length,0);
});
test('private launch contact is separate, optional, and consent is required before any post',async t=>{
 const ui=await setup(t,'#anketa');await final(ui);await ui.click(ui.button('Обсудить запуск'));await until(()=>ui.button('Отправить заявку').disabled===false);
 assert.equal(ui.d.getElementById('request-contact').value,'');await ui.field('request-contact','test@example.com');await ui.click(ui.button('Отправить заявку'));
 assert.equal(ui.d.activeElement.id,'request-consent');assert.deepEqual(ui.requests,[{url:'/api/intake/status',method:'GET'}]);
 assert.equal(ui.d.querySelector('.card-journey .personal-card-contact'),null);
});
test('reset requires confirmation and removes only this card draft',async t=>{
 const ui=await setup(t,'#anketa');await identity(ui);ui.w.localStorage.setItem('unrelated','keep');await ui.click(ui.button('Начать заново'));
 assert.equal(ui.d.getElementById('name').value,'Алина');await ui.click(ui.button('Отмена'));assert.equal(ui.d.getElementById('name').value,'Алина');
 await ui.click(ui.button('Начать заново'));await ui.click(ui.button('Да, начать заново'));assert.equal(ui.d.getElementById('name').value,'');assert.equal(ui.w.localStorage.getItem('scena-personal-card-v1'),null);assert.equal(ui.w.localStorage.getItem('unrelated'),'keep');
});

test('optional launch request uses the existing contract and distinguishes stored from delivered',async t=>{
 const payloads=[];const ui=await setup(t,'#anketa',null,async(url,options)=>{if(url==='/api/intake/start'){payloads.push(JSON.parse(options.body));return {ok:true,json:async()=>({uploadToken:'local-test-only'})};}assert.match(url,/\/api\/intake\/[a-f0-9-]+\/send$/);return {ok:true,json:async()=>({stored:true,delivered:false})};});
 await identity(ui,'Лилия','Модель');await ui.click(ui.d.querySelector('[aria-label^="Шаг 4:"]'));await ui.click(ui.button('Обсудить запуск'));await until(()=>ui.button('Отправить заявку').disabled===false);
 await ui.field('request-contact','test@example.com');await ui.click(ui.d.getElementById('request-consent'));await ui.click(ui.button('Отправить заявку'));await until(()=>ui.d.querySelector('.request-receipt'));
 assert.equal(payloads.length,1);assert.deepEqual(payloads[0].answers.features,['Визитка и QR']);assert.equal(payloads[0].answers.specialty,'Другое');assert.match(payloads[0].answers.notes,/Направление: Модель/);assert.equal(payloads[0].answers.consent,true);assert.deepEqual(payloads[0].photos,[]);
 assert.match(ui.d.querySelector('.request-receipt').textContent,/Заявка сохранена/);assert.doesNotMatch(ui.d.querySelector('.request-receipt').textContent,/доставлена/);assert.equal(ui.d.querySelector('.card-journey .personal-card-copy h3').textContent,'Лилия');
});
