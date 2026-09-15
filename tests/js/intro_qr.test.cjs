// DOM/geometry regression, using HTML from tests/intro_qr_http.py; not a device test.
const {JSDOM}=require('jsdom');
const fs=require('node:fs'), path=require('node:path'), assert=require('node:assert/strict');
const snapshots=process.argv[2];
if(!snapshots)throw Error('Pass the SCENA_QR_SNAPSHOTS directory produced by intro_qr_http.py');
const script=fs.readFileSync(path.join(__dirname,'../../scena_web/static/intro-qr.js'),'utf8');
async function main(){
  const dom=new JSDOM(fs.readFileSync(path.join(snapshots,'editor-ru.html'),'utf8'),{url:'https://scena.test/',runScripts:'outside-only'});
  const w=dom.window, d=w.document;
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
  let requests=0;w.fetch=()=>{requests++;throw Error('No network expected');};
  let resize;w.ResizeObserver=class{constructor(callback){resize=callback;}observe(){}};
  const editor=d.querySelector('.st-key-intro_qr_editor'), container=editor.querySelector('[data-qr-photo]');
  const photo=container.querySelector(':scope>img'), code=container.querySelector('.cube-qr');
  Object.defineProperties(photo,{naturalWidth:{value:1000,configurable:true},naturalHeight:{value:1500,configurable:true}});
  container.getBoundingClientRect=()=>({left:20,top:10,width:402,height:302});
  Object.defineProperties(container,{clientLeft:{value:1},clientTop:{value:1}});
  let box={left:21,top:11,width:400,height:300};
  photo.getBoundingClientRect=()=>box;
  photo.style.objectFit='contain';photo.style.objectPosition='20% 75%';
  for(const [key,value] of [['x','50'],['y','50'],['size','20']])editor.querySelector('.st-key-intro_qr_'+key+' input').value=value;
  w.eval(script);
  const near=(actual,expected)=>assert.ok(Math.abs(parseFloat(actual)-expected)<0.001,`${actual} != ${expected}`);
  // The 1000×1500 portrait occupies 200×300 inside 400×300. Its left gap is 40.
  near(code.style.left,118);near(code.style.top,128);near(code.style.getPropertyValue('--qr-size'),40);
  near(code.style.width,44);assert.equal(code.style.visibility,'visible');
  // Cover scales to 400×600, with a -225 vertical crop offset.
  photo.style.objectFit='cover';resize();near(code.style.left,160);near(code.style.top,35);near(code.style.getPropertyValue('--qr-size'),80);
  photo.style.objectFit='contain';
  for(const width of [320,360,390,412,430,768]){
    box={left:21,top:11,width,height:width*1.5};resize();
    near(code.style.left,width*.4);near(code.style.top,width*.65);
    near(code.style.getPropertyValue('--qr-size'),width*.2);
  }
  code.click();let dialog=d.getElementById(code.dataset.qrOpen);
  assert.equal(dialog.open,true);dialog.querySelector('[data-qr-close]').click();
  assert.equal(dialog.open,false);assert.equal(d.activeElement,code);
  // Changing the destination switches QR pixels, link, download and visible title.
  const select=editor.querySelector('.st-key-intro_qr_destination select');
  const options=JSON.parse(container.dataset.qrOptions);
  const original=code.querySelector('img').src;
  for(let index=0;index<options.length;index++){
    select.value=String(index);select.dispatchEvent(new w.Event('change',{bubbles:true}));
    assert.equal(code.querySelector('img').src,options[index].code);
    assert.equal(dialog.querySelector('[data-qr-link]').href,options[index].url);
    assert.equal(dialog.querySelector('[data-qr-download]').href,options[index].code);
    assert.equal(dialog.querySelector('[data-qr-title]').textContent,options[index].label);
  }
  assert.notEqual(code.querySelector('img').src,original);
  // Direct positioning writes real registered form controls, without submitting.
  const adjust=editor.querySelector('.st-key-intro_qr_x').closest('details');adjust.open=true;
  photo.dispatchEvent(new w.MouseEvent('click',{clientX:21+box.width*.6,clientY:11+box.height*.4,bubbles:true}));
  near(editor.querySelector('.st-key-intro_qr_x input').value,60);
  near(editor.querySelector('.st-key-intro_qr_y input').value,40);
  near(code.dataset.qrX,60);near(code.dataset.qrY,40);
  const current=code.style.left;
  editor.querySelector('.st-key-intro_qr_x input').value='101';
  editor.querySelector('.st-key-intro_qr_x input').dispatchEvent(new w.Event('input',{bubbles:true}));
  assert.equal(code.style.left,current,'Invalid entry must not move QR outside its image');
  assert.equal(requests,0);
  // Native patches may replace the entire preview; the new image gets its own observer.
  const next=container.cloneNode(true);container.replaceWith(next);
  await new Promise(resolve=>setTimeout(resolve,0));
  next.querySelector('.cube-qr').click();assert.equal(dialog.open,true);
  assert.equal(requests,0);dom.window.close();
  console.log('PASS: contain/cover coordinates, 320–768 widths, 44px target, dialog and focus, 8 destinations, tap-to-place, replacement after save, zero requests');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
