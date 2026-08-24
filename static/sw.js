/* PPS Hub service worker.
 *
 * Served by Flask from /sw.js — NOT from /static/sw.js. A service worker's
 * scope cannot rise above its own path, so one under /static/ could only ever
 * control /static/. It has to be at the root to cover the whole Hub, and going
 * through a route also gives us the kill switch below.
 *
 * ── The one rule that matters ───────────────────────────────────────────────
 *
 * **HTML is never cached.** Not the dashboard, not /login, not anything a
 * navigation returns. Every page in the Hub is session-authenticated behind a
 * 30-day cookie, so a cached page is a page that can be served to the wrong
 * person, or to the right person after they signed out. Worse, a cached /login
 * served to someone who already has a valid session is precisely the Safari
 * redirect loop that had to be fixed on 2026-07-27 (0e3f5d2) — a service worker
 * is a very effective way to bring that back, permanently, on every phone that
 * installed it.
 *
 * So: navigations go to the network, always. If the network genuinely fails,
 * they get the offline page. Nothing else.
 *
 * What IS cached is /static/ — the stylesheet, the logo, the icons. Those are
 * public, versionless in content, and the only reason the app looks broken on a
 * flaky connection.
 *
 * ── Why it can be turned off without a code change ──────────────────────────
 *
 * A service worker persists on a device until something replaces it. If this
 * one ever misbehaves, "clear your cache" does not fix it and neither does a
 * normal deploy of the pages. Setting SERVICE_WORKER_DISABLED=true on Render
 * makes /sw.js serve an unregistering stub instead of this file, which every
 * installed copy picks up on its next update check and removes itself. Keep
 * that route working.
 */

const VERSION = '__SW_VERSION__';           // injected by the /sw.js route
const STATIC_CACHE = `pps-static-${VERSION}`;
const OFFLINE_URL = '/offline';

// Small and stable. Anything that 404s here fails the whole install, so this
// list stays to things that certainly exist.
const PRECACHE = [
  OFFLINE_URL,
  '/static/pps-global.css',
  '/static/logo.png',
  '/static/icons/icon-192.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(STATIC_CACHE);
    // addAll is all-or-nothing; add individually so one missing asset cannot
    // stop the worker installing at all.
    await Promise.all(PRECACHE.map(async (url) => {
      try {
        await cache.add(new Request(url, { cache: 'reload' }));
      } catch (e) {
        // Non-fatal by design.
      }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    // Drop every cache from an older version. Because nothing here caches HTML,
    // there is no half-updated state to worry about and taking over
    // immediately is safe.
    const names = await caches.keys();
    await Promise.all(
      names.filter((n) => n.startsWith('pps-static-') && n !== STATIC_CACHE)
           .map((n) => caches.delete(n))
    );
    await self.clients.claim();
  })());
});

function isStaticAsset(url) {
  return url.origin === self.location.origin && url.pathname.startsWith('/static/');
}

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Anything that changes state, or that is not ours, is none of our business.
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // API responses are per-user and often per-second (pipeline polling,
  // presence). Caching one would serve one person's data to another.
  //
  // Strictly this is redundant today — the static-only rule further down
  // already excludes /api/ — and a mutation test confirmed removing it changes
  // no behaviour. It stays as an explicit statement of intent: if the caching
  // rule below is ever broadened, this is the line that stops user data going
  // into a shared cache, and it should be the last line anyone deletes.
  if (url.pathname.startsWith('/api/')) return;

  // Navigations: network, always. Offline page only if the network truly fails.
  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        return await fetch(req);
      } catch (e) {
        const cache = await caches.open(STATIC_CACHE);
        const offline = await cache.match(OFFLINE_URL);
        return offline || new Response(
          'You are offline.',
          { status: 503, headers: { 'Content-Type': 'text/plain' } }
        );
      }
    })());
    return;
  }

  if (!isStaticAsset(url)) return;

  // Static: cache first, refresh in the background. A stale stylesheet for one
  // load is a fair trade; a stale page is not, which is why only this branch
  // reads from the cache.
  event.respondWith((async () => {
    const cache = await caches.open(STATIC_CACHE);
    const hit = await cache.match(req);
    const network = fetch(req).then((res) => {
      // Only store real, complete, same-origin responses. An opaque or error
      // response cached here would persist a broken asset until the next
      // version bump.
      if (res && res.ok && res.type === 'basic') cache.put(req, res.clone());
      return res;
    }).catch(() => null);
    return hit || (await network) || new Response('', { status: 504 });
  })());
});

// Lets a page ask this worker to step aside without waiting for a reload.
self.addEventListener('message', (event) => {
  if (event.data === 'unregister') {
    self.registration.unregister().then(() => caches.keys().then(
      (names) => Promise.all(names.map((n) => caches.delete(n)))));
  }
});
