(() => {
  let busy = false;
  const status = (message, failed = false) => {
    const node = document.getElementById('scena-operation');
    node.hidden = !message; node.textContent = message; node.dataset.failed = String(failed);
  };
  // Retain unchanged DOM nodes (especially images/iframes) and patch only changes.
  function patch(current, next) {
    if (current.isEqualNode(next)) return;
    if (current.nodeType !== next.nodeType || current.nodeName !== next.nodeName) {
      current.replaceWith(next.cloneNode(true)); return;
    }
    if (current.nodeType !== Node.ELEMENT_NODE) { current.textContent = next.textContent; return; }
    const open = current.tagName === 'DETAILS' && current.open;
    for (const attr of [...current.attributes]) if (!next.hasAttribute(attr.name)) current.removeAttribute(attr.name);
    for (const attr of next.attributes) if (current.getAttribute(attr.name) !== attr.value) current.setAttribute(attr.name, attr.value);
    if (open) current.open = true;
    let index = 0;
    while (index < next.childNodes.length || index < current.childNodes.length) {
      const old = current.childNodes[index], fresh = next.childNodes[index];
      if (!fresh) { old.remove(); continue; }
      if (!old) current.append(fresh.cloneNode(true)); else patch(old, fresh);
      index++;
    }
    if (current.tagName === 'INPUT' && current.type !== 'file') {
      current.value = next.value; current.checked = next.checked;
    }
    if (current.tagName === 'TEXTAREA') current.value = next.value;
    if (current.tagName === 'SELECT') [...current.options].forEach((option, i) => { option.selected = next.options[i]?.selected || false; });
  }
  async function submit(form, button, changed) {
    if (busy) return;
    busy = true;
    const started = performance.now();
    status('Сохраняю…');
    const focus = document.activeElement?.id;
    const scroll = window.scrollY;
    const data = new FormData(form);
    if (button?.name) data.set(button.name, button.value);
    if (changed) data.set('_changed', changed);
    try {
      for (const input of form.querySelectorAll('input[type=file]')) {
        data.delete(input.name);
        if (!input.files.length) continue;
        const descriptors = [];
        for (const file of input.files) {
          if (file.size > Number(input.dataset.maxSize)) throw new Error('Файл слишком большой: ' + file.name);
          const refs = [];
          for (let offset = 0; offset < file.size; offset += 3 * 1024 * 1024) {
            status('Загружаю ' + file.name + ' · ' + Math.round(offset / file.size * 100) + '%');
            const response = await fetch('/scena-upload', {method:'POST', credentials:'same-origin',
              headers:{'Content-Type':'application/octet-stream','X-Scena-Form':data.get('_token'),'X-Scena-Field':input.name},
              body:file.slice(offset, offset + 3 * 1024 * 1024)});
            if (!response.ok) throw new Error('Не удалось загрузить файл. Повторите попытку.');
            refs.push((await response.json()).id);
          }
          descriptors.push({refs,name:file.name,mime:file.type,size:file.size});
        }
        data.set('_upload_' + input.name, JSON.stringify(descriptors));
      }
      status('Сохраняю…');
      const headers = form.querySelector('.st-key-booking_flow') ? {'X-Scena-Fragment':'booking'} : {};
      const response = await fetch(form.action, {method:'POST',body:data,credentials:'same-origin',headers});
      const text = await response.text();
      if (!response.ok) {
        const error = new DOMParser().parseFromString(text,'text/html');
        throw new Error(error.querySelector('main p')?.textContent || 'Не удалось сохранить. Обновите страницу и повторите действие.');
      }
      if (response.headers.get('Content-Type')?.includes('application/json')) {
        const payload = JSON.parse(text);
        const target = form.querySelector(payload.fragment);
        if (!target) throw new Error('Обновите страницу и повторите действие.');
        const template = document.createElement('template'); template.innerHTML = payload.html;
        patch(target, template.content.firstElementChild);
        form.elements._token.value = payload.token;
      } else {
        const next = new DOMParser().parseFromString(text,'text/html');
        document.title = next.title;
        const oldStyles = [...document.head.querySelectorAll('style')];
        const newStyles = [...next.head.querySelectorAll('style')];
        newStyles.forEach((style, index) => oldStyles[index] ? patch(oldStyles[index], style) : document.head.append(style.cloneNode(true)));
        oldStyles.slice(newStyles.length).forEach(style => style.remove());
        patch(document.body, next.body);
      }
      const destination = response.headers.get('X-Scena-URL') || form.action;
      history.replaceState(null,'',destination);
      window.scrollTo(0,scroll);
      if (focus) document.getElementById(focus)?.focus({preventScroll:true});
      for (const input of document.querySelectorAll('input[type=file]')) input.value = '';
      status('');
      let meter = document.getElementById('scena-performance');
      if (!meter) { meter = document.createElement('div'); meter.id = 'scena-performance'; meter.hidden = true; document.body.append(meter); }
      meter.dataset.lastInteraction = JSON.stringify({ms:Math.round(performance.now()-started),
        mode:headers['X-Scena-Fragment'] || 'dom-patch', bytes:new TextEncoder().encode(text).length,
        serverTiming:response.headers.get('Server-Timing')});
    } catch (error) {
      status(error.message,true);
    } finally { busy = false; }
  }
  const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const monthOffset = (month, delta) => { const d = new Date(month + '-01T12:00:00Z'); d.setUTCMonth(d.getUTCMonth()+delta); return d.toISOString().slice(0,7); };
  const row = cells => '<div class="scena-columns" data-testid="stHorizontalBlock" data-count="7" style="--scena-cols:1fr 1fr 1fr 1fr 1fr 1fr 1fr">' + cells.map(cell => '<div class="scena-column" data-testid="stColumn">'+cell+'</div>').join('')+'</div>';
  function localCalendar(data) {
    const first = new Date(data.month + '-01T12:00:00Z');
    const back = monthOffset(data.month,-1), next = monthOffset(data.month,1);
    const controls = '<div class="st-key-booking_month_header" style="display:flex;align-items:center;justify-content:space-between;gap:12px"><strong>'+escapeHTML(data.months[first.getUTCMonth()+1])+' '+first.getUTCFullYear()+'</strong><div style="display:flex;gap:8px">'+
      '<button type="button" data-booking-month="'+back+'" aria-label="‹" '+(back<data.days[0].slice(0,7)?'disabled':'')+'>‹</button>'+
      '<button type="button" data-booking-month="'+next+'" aria-label="›" '+(next>data.days.at(-1).slice(0,7)?'disabled':'')+'>›</button></div></div>';
    const cells = Array((first.getUTCDay()+6)%7).fill('<div class="scena-calendar-blank"></div>');
    const count = new Date(Date.UTC(first.getUTCFullYear(),first.getUTCMonth()+1,0)).getUTCDate();
    for (let d=1;d<=count;d++) {
      const day=data.month+'-'+String(d).padStart(2,'0'), valid=Object.hasOwn(data.availability,day), selected=day===data.selected;
      cells.push('<button type="button" style="width:100%" data-booking-day="'+day+'" data-kind="'+(selected?'primary':'secondary')+'" '+(!valid?'disabled':'')+' title="'+escapeHTML(data.dates[day] || day)+'">'+d+(!selected && data.availability[day]?.length?' ·':'')+'</button>');
    }
    while (cells.length%7) cells.push('<div class="scena-calendar-blank"></div>');
    return controls+row(data.weekdays.map(day=>'<div class="scena-calendar-weekday">'+escapeHTML(day)+'</div>'))+Array.from({length:cells.length/7},(_,i)=>row(cells.slice(i*7,i*7+7))).join('');
  }
  function localTimes(data) {
    const available=data.availability[data.selected] || [];
    let output='<h3 class="scena-booking-date">'+escapeHTML(data.dates[data.selected])+'</h3>';
    if (!available.length) {
      const nearest=data.days.find(day=>day>data.selected && data.availability[day].length);
      return output+'<div class="scena-notice info" role="status">'+escapeHTML(data.empty)+'</div>'+(nearest?'<button type="button" style="width:100%" data-booking-day="'+nearest+'">'+escapeHTML(data.nearest)+' · '+escapeHTML(data.dates[nearest])+'</button>':'');
    }
    for (const [kind,title,morning] of [['morning',data.morning,true],['afternoon',data.afternoon,false]]) {
      const slots=available.filter(slot=>(Number(slot.slice(0,2))<12)===morning);
      output+='<div class="scena-container scena-bordered st-key-booking_'+kind+'"><h4>'+escapeHTML(title)+'</h4><div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px">'+
        (slots.length?slots.map(slot=>'<button type="button" data-booking-time="'+slot+'" data-kind="'+(slot===data.chosen?'primary':'secondary')+'">'+slot+'</button>').join(''):'<p>'+escapeHTML(data.empty)+'</p>')+'</div></div>';
    }
    return output;
  }
  document.addEventListener('click', event => {
    const button=event.target.closest('[data-booking-day],[data-booking-time],[data-booking-month]');
    const state=document.getElementById('scena-booking-data');
    if (!button || !state || button.disabled) return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (busy) return;
    const started=performance.now(), data=JSON.parse(state.textContent), form=state.closest('form');
    if (button.dataset.bookingMonth) {
      data.month=button.dataset.bookingMonth;
    } else if (button.dataset.bookingDay) {
      if (!Object.hasOwn(data.availability,button.dataset.bookingDay)) return;
      data.selected=button.dataset.bookingDay; data.chosen=null; data.month=data.selected.slice(0,7);
    } else {
      if (!data.availability[data.selected]?.includes(button.dataset.bookingTime)) return;
      data.chosen=button.dataset.bookingTime;
    }
    form.elements[data.fields.date].value=data.days.indexOf(data.selected);
    form.elements[data.fields.time].value=data.chosen?data.times.indexOf(data.chosen):'';
    if (!button.dataset.bookingTime) {
      form.querySelector('.st-key-booking_calendar').innerHTML=localCalendar(data);
      form.querySelector('.st-key-booking_times').innerHTML=localTimes(data);
    } else {
      for (const item of form.querySelectorAll('[data-booking-time]')) item.dataset.kind=item.dataset.bookingTime===data.chosen?'primary':'secondary';
    }
    form.querySelector('.st-key-booking_continue_wrap').hidden=!data.chosen;
    form.querySelector('.st-key-booking_summary').textContent=data.chosen?data.service+' · '+data.dates[data.selected]+' · '+data.chosen:'';
    state.textContent=JSON.stringify(data);
    const meter=document.getElementById('scena-performance');
    if (meter) meter.dataset.lastInteraction=JSON.stringify({ms:Math.round(performance.now()-started),mode:'booking-local',networkRequests:0});
  }, true);
  document.addEventListener('submit', event => {
    if (event.target.id !== 'scena-page') return;
    event.preventDefault(); submit(event.target,event.submitter);
  });
  document.addEventListener('change', event => {
    if (event.target.dataset.auto === '1') submit(event.target.form,null,event.target.name);
  });
  const selectTab = tab => {
    const list = tab.closest('[role=tablist]');
    for (const item of list.querySelectorAll('[role=tab]')) {
      const selected = item === tab;
      item.setAttribute('aria-selected',String(selected)); item.tabIndex = selected ? 0 : -1;
      document.getElementById(item.getAttribute('aria-controls')).hidden = !selected;
    }
  };
  document.addEventListener('click', event => {const tab=event.target.closest('[role=tab]');if(tab)selectTab(tab);});
  document.addEventListener('keydown', event => {
    const tab=event.target.closest('[role=tab]'); if(!tab || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();const tabs=[...tab.parentElement.querySelectorAll('[role=tab]')];let index=tabs.indexOf(tab);
    index=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
    selectTab(tabs[index]);tabs[index].focus();
  });
})();
