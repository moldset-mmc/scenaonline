/* One image coordinate system for both the public card and the owner preview. */
(() => {
  const initialized = new WeakSet();
  function geometry(photo) {
    if (!photo.naturalWidth || !photo.naturalHeight) return null;
    const box = photo.getBoundingClientRect(), style = getComputedStyle(photo);
    const fit = style.objectFit === 'cover' ? Math.max : Math.min;
    const scale = fit(box.width / photo.naturalWidth, box.height / photo.naturalHeight);
    const width = photo.naturalWidth * scale, height = photo.naturalHeight * scale;
    const positions = style.objectPosition.split(' ');
    const offset = (token, free) => token.endsWith('%') ? free * parseFloat(token) / 100 : parseFloat(token) || 0;
    return {left: box.left + offset(positions[0] || '50%', box.width - width),
      top: box.top + offset(positions[1] || '50%', box.height - height), width, height};
  }
  function position(container) {
    const photo = container.querySelector(':scope>img'), code = container.querySelector('.cube-qr');
    const rect = photo && geometry(photo);
    if (!rect || !code) return;
    const parent = container.getBoundingClientRect();
    const size = Math.min(rect.width, rect.height) * Number(code.dataset.qrSize) / 100;
    const hit = Math.max(44, size);
    // Keep the complete QR inside the image even when a centre is set at an edge.
    const cx = Math.min(rect.width - size / 2, Math.max(size / 2, rect.width * Number(code.dataset.qrX) / 100));
    const cy = Math.min(rect.height - size / 2, Math.max(size / 2, rect.height * Number(code.dataset.qrY) / 100));
    code.style.left = (rect.left - parent.left - container.clientLeft + cx - hit / 2) + 'px';
    code.style.top = (rect.top - parent.top - container.clientTop + cy - hit / 2) + 'px';
    code.style.width = hit + 'px'; code.style.height = hit + 'px';
    code.style.setProperty('--qr-size', size + 'px'); code.style.visibility = 'visible';
  }
  function syncEditor(editor) {
    const container = editor.querySelector('[data-qr-photo]');
    if (!container) return;
    const code = container.querySelector('.cube-qr');
    for (const field of ['x', 'y', 'size']) {
      const input = editor.querySelector('.st-key-intro_qr_' + field + ' input');
      if (input && input.value !== '' && input.validity.valid) code.dataset['qr' + field[0].toUpperCase() + field.slice(1)] = input.value;
    }
    const select = editor.querySelector('.st-key-intro_qr_destination select');
    const item = JSON.parse(container.dataset.qrOptions || '[]')[Number(select?.value)];
    const dialog = document.getElementById(code.dataset.qrOpen);
    if (item && dialog) {
      code.querySelector('img').src = item.code;
      code.querySelector('img').alt = 'QR — ' + item.label;
      code.setAttribute('aria-label', code.dataset.qrShow + ': ' + item.label);
      dialog.querySelector('img').src = item.code;
      dialog.querySelector('img').alt = 'QR — ' + item.label;
      dialog.querySelector('[data-qr-title]').textContent = item.label;
      dialog.querySelector('[data-qr-link]').href = item.url;
      dialog.querySelector('[data-qr-download]').href = item.code;
      dialog.setAttribute('aria-label', 'QR — ' + item.label);
    }
    position(container);
  }
  function init() {
    document.querySelectorAll('[data-qr-photo]').forEach(container => {
      const photo = container.querySelector(':scope>img');
      if (photo && !initialized.has(photo)) {
        initialized.add(photo);
        photo.addEventListener('load', () => position(container));
        if (typeof ResizeObserver !== 'undefined') new ResizeObserver(() => position(container)).observe(photo);
      }
      position(container);
    });
    document.querySelectorAll('.st-key-intro_qr_editor').forEach(syncEditor);
  }
  document.addEventListener('input', event => {
    const editor = event.target.closest('.st-key-intro_qr_editor');
    if (editor) syncEditor(editor);
  });
  document.addEventListener('change', event => {
    const editor = event.target.closest('.st-key-intro_qr_editor');
    if (editor) syncEditor(editor);
  });
  document.addEventListener('click', event => {
    const opener = event.target.closest('[data-qr-open]');
    if (opener) {
      const dialog = document.getElementById(opener.dataset.qrOpen);
      if (!dialog) return;
      dialog.addEventListener('close', () => opener.focus({preventScroll:true}), {once:true});
      dialog.showModal(); return;
    }
    const close = event.target.closest('[data-qr-close]');
    if (close) { close.closest('dialog').close(); return; }
    if (event.target.matches('dialog.qr-dialog')) {
      const box = event.target.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) event.target.close();
      return;
    }
    const container = event.target.closest('.qr-editor-preview');
    const editor = container?.closest('.st-key-intro_qr_editor');
    const adjust = editor?.querySelector('.st-key-intro_qr_x')?.closest('details');
    if (!editor || !adjust?.open) return;
    const rect = geometry(container.querySelector(':scope>img'));
    if (!rect) return;
    for (const [field, value] of [['x', (event.clientX - rect.left) / rect.width * 100], ['y', (event.clientY - rect.top) / rect.height * 100]]) {
      const input = editor.querySelector('.st-key-intro_qr_' + field + ' input');
      input.value = Math.min(100, Math.max(0, value)).toFixed(2);
      input.dispatchEvent(new Event('input', {bubbles:true}));
    }
  });
  addEventListener('resize', init);
  // Native form saves replace only changed nodes; initialize their new previews.
  let queued = false;
  new MutationObserver(records => {
    if (queued || !records.some(record => [...record.addedNodes].some(node => node.nodeType === 1))) return;
    queued = true; queueMicrotask(() => { queued = false; init(); });
  }).observe(document.body, {childList:true, subtree:true});
  init();
})();
