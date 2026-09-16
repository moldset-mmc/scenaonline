"""Public analytics without private cabinet pages, form values or session replay."""
import json
import re


def render_analytics(settings, metadata, *, private=False, submitted=False, preview=False):
    counter = str(settings.get('seo_yandex_counter', ''))
    if private or submitted or preview or not metadata.get('indexable') or not re.fullmatch(r'[1-9][0-9]{4,12}', counter):
        return ''
    url = json.dumps(metadata['canonical']).replace('<', '\\u003c')
    page = json.dumps(metadata['page'])
    return rf'''<script data-scena-analytics="{counter}">
(function(w,d){{
  const id={counter}, page={page}, canonical={url};
  w.ym=w.ym||function(){{(w.ym.a=w.ym.a||[]).push(arguments)}};
  w.ym.l=Date.now();
  const script=d.createElement('script');script.async=true;script.src='https://mc.yandex.ru/metrika/tag.js';d.head.appendChild(script);
  w.ym(id,'init',{{defer:true,clickmap:false,webvisor:false,trackLinks:false,ecommerce:false,childIframe:false,disableYtm:true,accurateTrackBounce:true,triggerEvent:true}});
  let referer='';try{{const r=new URL(d.referrer);referer=r.origin+r.pathname}}catch(e){{}}
  w.ym(id,'hit',canonical,{{referer:referer,title:d.title}});
  if(page==='booking')w.ym(id,'reachGoal','booking_open');
  const sent=new Set();
  function conversions(){{d.querySelectorAll('[data-scena-conversion]').forEach(el=>{{
    const goal=el.dataset.scenaConversion,key=goal+':'+el.dataset.scenaConversionKey;
    if(!['booking_request','shop_order','course_request'].includes(goal)||sent.has(key))return;
    sent.add(key);w.ym(id,'reachGoal',goal);
  }})}}
  d.addEventListener('click',e=>{{const a=e.target.closest('a[href]');if(!a)return;
    if(/^(tel:|sms:|mailto:|https:\/\/t\.me\/)/i.test(a.getAttribute('href')))w.ym(id,'reachGoal','contact_click');
  }});
  d.addEventListener('DOMContentLoaded',()=>{{conversions();new MutationObserver(conversions).observe(d.body,{{childList:true,subtree:true}})}});
}})(window,document);
</script>'''
