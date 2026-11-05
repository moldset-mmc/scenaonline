// Exercises the actual standalone deliverable, including script/HTML packaging.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM,VirtualConsole}=require('jsdom');
const file=process.env.SCENA_PREVIEW_HTML;
test('standalone preview runs all steps and blocks intake without any network',async t=>{
 assert.ok(file,'Set SCENA_PREVIEW_HTML to the generated review file');
 const html=fs.readFileSync(file,'utf8'),errors=[],console=new VirtualConsole();
 console.on('jsdomError',error=>{if(error.type!=='css parsing')errors.push(error.message);});
 const dom=new JSDOM(html,{url:'https://offline.test/newcard#anketa',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:console,beforeParse(w){
  w.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}});w.IntersectionObserver=class{observe(){}disconnect(){}};w.scrollTo=()=>{};w.HTMLElement.prototype.scrollIntoView=()=>{};
 }});t.after(()=>dom.window.close());
 const w=dom.window,d=w.document;
 const settle=()=>new Promise(r=>setTimeout(r,100));
 async function until(fn){for(let i=0;i<60;i++){if(fn())return;await settle();}assert.ok(fn());}
 const button=text=>[...d.querySelectorAll('button')].find(b=>b.textContent.trim()===text);
 assert.equal(d.querySelectorAll('script').length,1);
 await until(()=>d.getElementById('name'));
 Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value').set.call(d.getElementById('name'),'Лилия');d.getElementById('name').dispatchEvent(new w.Event('input',{bubbles:true}));await settle();
 d.querySelector('input[name=specialty][value="Модель"]').click();await settle();button('Выбрать фотографию').click();await settle();button('Продолжить без фото').click();await settle();button('Увидеть свою визитку').click();await settle();
 assert.equal(d.querySelector('.card-journey .personal-card-copy h3').textContent,'Лилия');assert.equal(d.querySelectorAll('.journey-progress .lucide-check').length,3);
 button('Обсудить запуск').click();await settle();assert.equal(button('Отправить заявку').disabled,true);assert.match(d.querySelector('.card-request').textContent,/В этой копии заявки не отправляются/);
 assert.equal(d.querySelectorAll('script[src],link[rel=stylesheet]').length,0);
 assert.ok([...d.querySelectorAll('img')].every(img=>img.src.startsWith('data:')));
 assert.deepEqual(errors,[]);
});
