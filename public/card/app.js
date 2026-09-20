'use strict';
(() => {
  const CARD_URL = 'https://mbstudio.scena.life/card/';
  const published = location.protocol === 'https:' && location.origin === 'https://mbstudio.scena.life' && /^\/card\/(?:index\.html)?$/.test(location.pathname);
  const byId = id => document.getElementById(id);
  const toast = byId('toast');
  let toastTimer;
  let installPrompt;
  function say(message) { clearTimeout(toastTimer); toast.textContent = message; toast.hidden = false; toastTimer = setTimeout(() => { toast.hidden = true; }, 5000); }
  function show(id) { const dialog = byId(id); if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', ''); }
  function close(dialog) { if (typeof dialog.close === 'function') dialog.close(); else dialog.removeAttribute('open'); }
  for (const button of document.querySelectorAll('[data-close]')) button.addEventListener('click', () => close(button.closest('dialog')));
  for (const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('click', event => { if (event.target !== dialog) return; const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) close(dialog); });
  if (!published) {
    byId('preview-note').hidden = false;
    byId('share-preview').hidden = false;
    byId('nfc-preview').hidden = false;
    byId('copy-button').disabled = true;
    byId('share-help').textContent = 'Предпросмотр QR-кода для будущей публикации.';
    byId('install-note').textContent = 'Установка станет доступна после публикации по HTTPS. Ниже показаны шаги для опубликованной визитки.';
  }
  byId('qr-button').addEventListener('click', () => show('share-dialog'));
  byId('share-button').addEventListener('click', async () => {
    if (!published) { show('share-dialog'); return; }
    if (typeof navigator.share === 'function') {
      try { await navigator.share({title:'MBStudio · Маша Бараночникова', text:'Моя визитка · Model & Makeup Artist', url:CARD_URL}); }
      catch (error) { if (error.name !== 'AbortError') show('share-dialog'); }
    } else show('share-dialog');
  });
  byId('copy-button').addEventListener('click', async () => {
    if (!published) return;
    try { await navigator.clipboard.writeText(CARD_URL); say('Ссылка скопирована'); }
    catch { byId('card-url').focus(); byId('card-url').select(); say('Скопируйте выделенную ссылку'); }
  });
  byId('nfc-button').addEventListener('click', () => show('nfc-dialog'));
  byId('install-button').addEventListener('click', () => {
    const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
    if (standalone) { say('Визитка уже открыта с главного экрана'); return; }
    const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    byId(ios ? 'apple-guide' : 'android-guide').open = true;
    show('install-dialog');
  });
  addEventListener('beforeinstallprompt', event => {
    if (!published) return;
    event.preventDefault(); installPrompt = event; byId('native-install').hidden = false;
  });
  byId('native-install').addEventListener('click', async () => {
    if (!installPrompt) return;
    try { await installPrompt.prompt(); const choice = await installPrompt.userChoice; if (choice.outcome === 'accepted') say('Установка запрошена — проверьте главный экран'); }
    catch { say('Используйте добавление через меню браузера'); }
    finally { installPrompt = null; byId('native-install').hidden = true; }
  });
  addEventListener('appinstalled', () => { installPrompt = null; byId('native-install').hidden = true; say('Визитка добавлена'); });
  if (published && 'serviceWorker' in navigator) addEventListener('load', () => { navigator.serviceWorker.register('./sw.js', {scope:'./'}).catch(() => {}); });
})();
