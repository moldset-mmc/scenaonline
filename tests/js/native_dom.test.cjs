const {JSDOM}=require('jsdom');
const fs=require('fs');
const assert=require('node:assert/strict');
const source=fs.readFileSync(require('path').join(__dirname,'../../scena_web/static/web.js'),'utf8');
const html=token=>`<!doctype html><html><head><title>SCENA</title></head><body><form id="scena-page" action="/?page=admin&view=model"><input type="hidden" name="_token" value="${token}"><a data-cabinet-nav href="/?page=admin&section=pages&view=scene">Моя Сцена</a><div class="scena-tabs"><div role="tablist"><button type="button" id="products-tab" role="tab" aria-controls="products-panel" aria-selected="true">Товары</button><button type="button" id="settings-tab" role="tab" aria-controls="settings-panel" aria-selected="false">Витрина</button></div><div role="tabpanel" id="products-panel">Каталог</div><div role="tabpanel" id="settings-panel" hidden><fieldset data-form-key="active"><input name="name" value="Saved"><input name="price" value="900"><button name="_action" value="save">Сохранить</button></fieldset></div></div><fieldset data-form-key="unrelated">${Array.from({length:150},(_,i)=>`<input name="other_${i}" value="Unrelated">`).join('')}<input type="file" id="unused-photo" name="photo"></fieldset></form><div id="scena-operation" hidden></div></body></html>`;
async function main(){
  const dom=new JSDOM(html('before'),{url:'https://fixture.scena.test/',runScripts:'outside-only'});
  const w=dom.window;w.scrollTo=()=>{};w.TextEncoder=TextEncoder;
  const calls=[];let done;
  const completed=new Promise(resolve=>{done=resolve});
  w.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,headers:new Map([['Content-Type','text/html']]),text:async()=>html('after')}};
  const observer=new w.MutationObserver(()=>{if(w.document.getElementById('scena-performance')?.dataset.lastInteraction)done()});
  observer.observe(w.document.body,{subtree:true,attributes:true,childList:true});
  w.eval(source);
  w.document.getElementById("settings-tab").click();
  // >100 fields exist, but only the submitted group belongs in the request.
  w.document.querySelector('button[value=save]').click();
  await Promise.race([completed,new Promise((_,reject)=>setTimeout(()=>reject(Error('Save did not finish')),1500))]);
  assert.equal(calls.length,1);
  assert.equal(w.document.getElementById('settings-panel').hidden,false,'Save must keep the Telegram settings tab visible');
  assert.equal(w.document.getElementById('settings-tab').getAttribute('aria-selected'),'true');
  const body=calls[0].options.body;
  assert.equal(body.constructor.name,'URLSearchParams');
  assert.deepEqual([...body.keys()].sort(),['_action','_token','name','price']);
  assert.equal(w.document.querySelector('[name=_token]').value,'after');
  assert.equal(w.document.querySelector('[data-cabinet-nav]').getAttribute('href'),'/?page=admin&section=pages&view=scene');
  assert.equal(w.document.getElementById('scena-operation').textContent,'');
  // Save a second time without refreshing: the fresh token must be submitted.
  w.document.querySelector('button[value=save]').click();
  await new Promise(resolve=>setTimeout(resolve,20));
  assert.equal(calls.length,2);assert.equal(calls[1].options.body.get('_token'),'after');
  // Real gallery code: main image, next/previous and thumbnails need no HTTP.
  const opener=w.document.createElement('button');opener.type='button';
  opener.dataset.shopGallery=JSON.stringify({images:['/one.webp','/two.webp','/three.webp'],title:'<img src=x onerror=alert(1)>',price:'90 MDL',description:'Description',recommendation:'Recommendation',close:'Close',previous:'Previous',next:'Next'});
  w.document.body.append(opener);
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
  const beforeGallery=calls.length;
  opener.click();let dialog=w.document.querySelector('dialog');
  assert.equal(dialog.open,true);assert.equal(dialog.querySelector('h2').children.length,0);
  assert.equal(dialog.querySelector('.shop-dialog-image').getAttribute('src'),'/one.webp');
  dialog.querySelector('[data-gallery-next]').click();
  assert.equal(dialog.querySelector('.shop-dialog-image').getAttribute('src'),'/two.webp');
  dialog.querySelectorAll('.shop-photo-thumbs button')[2].click();
  assert.equal(dialog.querySelector('.shop-dialog-image').getAttribute('src'),'/three.webp');
  dialog.dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}));
  assert.equal(dialog.querySelector('.shop-dialog-image').getAttribute('src'),'/two.webp');
  dialog.querySelector('.shop-dialog-close').click();
  assert.equal(w.document.querySelector('dialog'),null);assert.equal(w.document.activeElement,opener);
  const single=JSON.parse(opener.dataset.shopGallery);single.images=['/one.webp'];opener.dataset.shopGallery=JSON.stringify(single);
  opener.click();dialog=w.document.querySelector('dialog');
  assert.equal(dialog.querySelector('.shop-dialog-arrows').hidden,true);
  assert.equal(dialog.querySelector('.shop-photo-thumbs').hidden,true);
  assert.equal(calls.length,beforeGallery);
  console.log('PASS: 1–3 photo modal, thumbnail and keyboard changes, focus restoration, safe product text, zero requests');
  observer.disconnect();dom.window.close();
  console.log('PASS: scoped urlencoded save on a >100-field page; repeat save uses fresh token; cabinet navigation is a GET link');
}
main().catch(error=>{console.error(error);process.exitCode=1});
