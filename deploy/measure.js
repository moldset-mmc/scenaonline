/* Local-only browser measurements. No analytics transmission or identifiers. */
(()=>{
  const result={fcpMs:null,lcpMs:null,contentReadyMs:null,loadMs:null,ttfbMs:null,resourceCount:0,transferBytes:0};
  let observer,finished=false;
  function expose(){
    if(!document.body)return;
    let output=document.getElementById('scena-performance');
    if(!output){output=document.createElement('output');output.id='scena-performance';output.hidden=true;output.setAttribute('aria-hidden','true');document.body.append(output);}
    const nav=performance.getEntriesByType('navigation')[0];
    if(nav){result.ttfbMs=Math.round(nav.responseStart);result.loadMs=nav.loadEventEnd?Math.round(nav.loadEventEnd):null;}
    const resources=performance.getEntriesByType('resource');
    result.resourceCount=resources.length;result.transferBytes=resources.reduce((sum,r)=>sum+r.transferSize,0);
    output.dataset.metrics=JSON.stringify(result);
  }
  function check(){
    if(finished)return;
    const footer=document.querySelector('.scena-footer');
    const hero=document.querySelector('.scena-editorial-scene img');
    if(!footer||!hero||!hero.complete||!hero.naturalWidth)return;
    finished=true;
    Promise.all([hero.decode().catch(()=>{}),document.fonts.ready]).then(()=>requestAnimationFrame(()=>requestAnimationFrame(()=>{
      result.contentReadyMs=Math.round(performance.now());expose();if(observer)observer.disconnect();
    })));
  }
  try{new PerformanceObserver(list=>{for(const e of list.getEntries())if(e.name==='first-contentful-paint')result.fcpMs=Math.round(e.startTime);expose();}).observe({type:'paint',buffered:true});}catch(e){}
  try{new PerformanceObserver(list=>{const e=list.getEntries().at(-1);if(e)result.lcpMs=Math.round(e.startTime);expose();}).observe({type:'largest-contentful-paint',buffered:true});}catch(e){}
  function start(){observer=new MutationObserver(check);observer.observe(document.body,{childList:true,subtree:true});document.addEventListener('load',check,true);check();expose();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  window.addEventListener('load',()=>{setTimeout(expose,0);check();},{once:true});
})();
