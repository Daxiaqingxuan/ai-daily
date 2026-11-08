/* AI 晨报离线缓存：读过的期数断网也能看；网络优先，永远优先拿最新内容 */
const CACHE = 'ai-daily-reader-v3';
const SHELL = [
  './', './index.html', './config.js', './issues.js',
  './manifest.webmanifest', './icon-192.png', './icon-512.png',
  './apple-touch-icon.png', './favicon.ico'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  // 导航请求（打开页面本身）绕过 HTTP 缓存：线上重新发布后，手机端下次打开
  // 一定拿到新的 index.html，而不是启发式缓存里几小时前的旧副本。
  const opts = req.mode === 'navigate' ? { cache: 'no-store' } : undefined;
  e.respondWith(
    fetch(req, opts).then(res => {
      if (res && res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match(req).then(hit => {
      if (hit) return hit;
      if (req.mode === 'navigate') return caches.match('./index.html');
      return new Response('', { status: 504, statusText: '离线且未缓存' });
    }))
  );
});
