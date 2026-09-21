'use strict';
const CACHE = 'mbstudio-card-v3';
const ROOT = new URL('./', self.location.href);
const FILES = ['./', './index.html', './style.css', './app.js', './assets/scena-live.svg', './assets/manrope-regular.woff2', './assets/portrait.webp', './portrait.webp', './assets/qr.svg', './assets/icon-192.png', './assets/icon-512.png', './manifest.webmanifest', './mbstudio.vcf'].map(path => new URL(path, ROOT).href);
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES)).then(() => self.skipWaiting())); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('mbstudio-card-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // Never cache cabinet requests. Query strings only vary these known public files.
  const key = url.origin + url.pathname;
  if (event.request.method !== 'GET' || !FILES.includes(key)) return;
  event.respondWith(fetch(event.request, {cache:'no-store'}).then(response => {
    if (response.ok && ['basic', 'cors'].includes(response.type)) {
      const copy = response.clone();
      event.waitUntil(caches.open(CACHE).then(cache => cache.put(key, copy)));
    }
    return response;
  }).catch(() => caches.match(key).then(cached => cached || (event.request.mode === 'navigate' ? caches.match(ROOT.href) : Response.error()))));
});
