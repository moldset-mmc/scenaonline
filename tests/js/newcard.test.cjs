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
const settle=()=>new Promise(resolve=>setTimeout(resolve,65));

async function setup(t,hash=''){
  const errors=[];
  const console=new VirtualConsole();
  console.on('jsdomError',error=>errors.push(error));
  const dom=new JSDOM(html,{url:'https://scena.test/newcard'+hash,runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:console});
  const w=dom.window,d=w.document,requests=[];
  w.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}});
  w.IntersectionObserver=class{observe(){}disconnect(){}};
  w.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};
  w.scrollTo=()=>{};
  w.HTMLElement.prototype.scrollIntoView=function(){};
  w.fetch=async(url,options={})=>{
    requests.push({url,method:options.method||'GET'});
    assert.equal(url,'/api/intake/status','No submission or upload is allowed in these tests');
    assert.equal(options.method,undefined);
    return {json:async()=>({ready:true})};
  };
  w.eval(script);
  await settle();
  t.after(()=>{dom.window.close();assert.deepEqual(errors,[],'No React/DOM errors');});
  const click=async element=>{assert.ok(element,'Expected control exists');element.focus();element.click();await settle();};
  const button=text=>[...d.querySelectorAll('button')].find(b=>b.textContent.trim()===text);
  const field=async(id,value)=>{
    const input=d.getElementById(id);
    Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value').set.call(input,value);
    input.dispatchEvent(new w.Event('input',{bubbles:true}));await settle();
  };
  return {w,d,click,button,field,requests};
}

test('initial cover load leaves focus alone; a direct example link focuses its heading',async t=>{
  const {d}=await setup(t);
  assert.equal(d.activeElement.tagName,'BODY','Opening the cover must not autofocus its large title');
  const direct=await setup(t,'#example');
  assert.equal(direct.d.activeElement.id,'example-title');
});

test('invalid first step focuses the required name, then the invalid choice group',async t=>{
  const {d,click,button,field}=await setup(t,'#anketa');
  await click(button('Продолжить'));
  assert.equal(d.activeElement.id,'name');
  assert.equal(d.getElementById('name').required,true);
  assert.equal(d.getElementById('name').getAttribute('aria-describedby'),'name-error');
  await field('name','Тест');
  await click(button('Продолжить'));
  const group=d.querySelector('[role="group"][aria-label="Специализация"]');
  assert.ok(d.activeElement===group,'Focus must move to the invalid choice group');
  assert.equal(group.getAttribute('aria-invalid'),'true');
  assert.equal(group.getAttribute('aria-describedby'),'specialty-error');
  assert.ok(d.getElementById('specialty-error'));
});

test('jumping ahead never marks unvalidated steps complete, validated step loses completion when invalidated',async t=>{
  const {d,click,button,field}=await setup(t,'#anketa');
  await click(d.querySelector('[aria-label^="Шаг 6:"]'));
  assert.equal(d.querySelectorAll('.step-number .lucide-check').length,0);
  await click(d.querySelector('[aria-label^="Шаг 1:"]'));
  await field('name','Тест');await click(button('Визажист'));await click(button('Продолжить'));
  assert.ok(d.querySelector('[aria-label^="Шаг 1:"] .lucide-check'));
  await click(d.querySelector('[aria-label^="Шаг 1:"]'));
  await field('name','');
  assert.equal(d.querySelector('[aria-label^="Шаг 1:"] .lucide-check'),null);
});

test('final validation returns to the first invalid field without making a submission',async t=>{
  const {d,click,button,requests}=await setup(t,'#anketa');
  await click(d.querySelector('[aria-label^="Шаг 6:"]'));
  assert.equal(d.getElementById('contact').required,true);
  assert.equal(d.getElementById('consent').getAttribute('aria-required'),'true');
  await click(button('Отправить анкету'));
  assert.equal(d.activeElement.id,'name');
  assert.match(d.querySelector('.step-heading h2').textContent,/Начнём с вас/);
  assert.deepEqual(requests,[{url:'/api/intake/status',method:'GET'}]);
});

test('return to card restores each opener; direct form entry returns focus to the cover title',async t=>{
  const {d,click}=await setup(t);
  for(const opener of [...d.querySelectorAll('a[href="#anketa"]')]){
    await click(opener);
    await click(d.querySelector('.form-cover-back'));
    assert.ok(d.activeElement===opener,'Focus must return to the link that opened the form');
    assert.ok(!opener.closest('[hidden]'),'Opener must be visible');
  }
  const direct=await setup(t,'#anketa');
  await direct.click(direct.d.querySelector('.form-cover-back'));
  assert.equal(direct.d.activeElement.id,'cover-title');
});

test('example navigation focuses its heading and modifier-click is not intercepted',async t=>{
  const {w,d,click}=await setup(t);
  const link=d.querySelector('.cover-actions a[href="#example"]');
  const modified=new w.MouseEvent('click',{bubbles:true,cancelable:true,ctrlKey:true});
  // Prevent jsdom's navigation only after the app's handler has been observed.
  let appPrevented;
  d.addEventListener('click',e=>{appPrevented=e.defaultPrevented;e.preventDefault();},{once:true});
  link.dispatchEvent(modified);
  assert.equal(appPrevented,false);
  await click(link);
  assert.equal(w.location.hash,'#example');
  assert.equal(d.activeElement.id,'example-title');
});

test('browser Back and Forward keep the visible view, focus and entered text consistent',async t=>{
  const {w,d,click,field}=await setup(t);
  const opener=d.querySelector('.cover-actions a[href="#anketa"]');
  await click(opener);await field('name','Тест');
  w.history.back();await settle();
  assert.equal(d.querySelector('.cover').hidden,false);
  assert.ok(d.activeElement===opener);
  w.history.forward();await settle();
  assert.equal(d.querySelector('.cover').hidden,true);
  assert.equal(d.activeElement.id,'anketa');
  assert.equal(d.getElementById('name').value,'Тест');
});

test('final consent error is focused and associated after the other required fields are valid',async t=>{
  const {d,click,button,field,requests}=await setup(t,'#anketa');
  await field('name','Тест');await click(button('Визажист'));await click(button('Продолжить'));
  await click(button('Портфолио'));await click(button('Продолжить'));
  await click(d.querySelector('[aria-label^="Шаг 6:"]'));
  await field('contact','test@example.com');await click(button('Отправить анкету'));
  assert.equal(d.activeElement.id,'consent');
  assert.equal(d.activeElement.getAttribute('aria-describedby'),'consent-error');
  assert.ok(d.getElementById('consent-error'));
  assert.deepEqual(requests,[{url:'/api/intake/status',method:'GET'}]);
});
