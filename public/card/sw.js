'use strict';
const CACHE = 'mbstudio-card-v2';
const ROOT = new URL('./', self.location.href);
const FILES = ['./', './index.html', './style.css', './app.js', './assets/scena-live.svg', './assets/manrope-regular.woff2', './assets/portrait.webp', './assets/qr.svg', './assets/icon-192.png', './assets/icon-512.png', './manifest.webmanifest', './mbstudio.vcf'].map(path => new URL(path, ROOT).href);
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES)).then(() => self.skipWaiting())); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('mbstudio-card-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== ROOT.origin || !url.pathname.startsWith(ROOT.pathname) || url.pathname.endsWith('/sw.js') || url.search) return;
  if (!FILES.includes(url.href)) return;
  event.respondWith(fetch(event.request).then(response => { if (response.ok && response.type === 'basic') { const copy = response.clone(); event.waitUntil(caches.open(CACHE).then(cache => cache.put(event.request, copy))); } return response; }).catch(() => caches.match(event.request).then(cached => cached || (event.request.mode === 'navigate' ? caches.match(ROOT.href) : Response.error()))));
});
