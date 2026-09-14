(() => {
  let busy = false;
  const status = (message, failed = false) => {
    const node = document.getElementById('scena-operation');
    node.hidden = !message; node.textContent = message; node.dataset.failed = String(failed);
  };
  async function submit(form, button, changed) {
    if (busy) return;
    busy = true;
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
      const response = await fetch(form.action, {method:'POST',body:data,credentials:'same-origin'});
      const text = await response.text();
      if (!response.ok) {
        const error = new DOMParser().parseFromString(text,'text/html');
        throw new Error(error.querySelector('main p')?.textContent || 'Не удалось сохранить. Обновите страницу и повторите действие.');
      }
      const next = new DOMParser().parseFromString(text,'text/html');
      document.title = next.title;
      // Styles may change when the cabinet changes the page theme.
      const oldStyles = document.head.querySelectorAll('style');
      oldStyles.forEach(node => node.remove());
      next.head.querySelectorAll('style').forEach(node => document.head.append(node));
      document.body.replaceWith(next.body);
      const destination = response.headers.get('X-Scena-URL') || form.action;
      history.replaceState(null,'',destination);
      window.scrollTo(0,scroll);
      if (focus) document.getElementById(focus)?.focus({preventScroll:true});
      status('');
    } catch (error) {
      status(error.message,true);
    } finally { busy = false; }
  }
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
