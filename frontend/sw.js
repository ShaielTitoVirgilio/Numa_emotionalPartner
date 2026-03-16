// ============================================
// SERVICE WORKER — Numa v6
// Estrategia:
//   JS / CSS  → siempre de la red (nunca cacheados)
//   Assets    → cacheados (audio, video, imágenes)
//   API       → siempre de la red, sin interceptar
// ============================================

const CACHE_NAME = 'numa-v77';

// Solo cacheamos assets pesados que no cambian seguido
const ASSETS_CACHEABLES = [
  '/static/assets/rain_loop.mp3',
  '/static/assets/wave_loop.mp3',
  '/static/assets/fire_loop.mp3',
  '/static/assets/forest_loop.mp3',
  '/static/assets/inhale.mp3',
  '/static/assets/exhale.mp3',
  // Videos yoga
  '/static/assets/numa_cuello_der.mp4',
  '/static/assets/numa_cuello_izq.mp4',
  '/static/assets/haciaAtras.mp4',
  '/static/assets/pecho.mp4',
  '/static/assets/pos_nino.mp4',
  '/static/assets/gatomalo_bueno.mp4',
  '/static/assets/haciaAdelante.mp4',
];

// ── Instalación ──────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(ASSETS_CACHEABLES))
      .catch(() => {})
  );
  self.skipWaiting();
});

// ── Activación ───────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== CACHE_NAME)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch ────────────────────────────────────
self.addEventListener('fetch', event => {
  const url = event.request.url;

  // 1. Rutas de API → dejar pasar sin tocar
  if (url.includes('/chat') ||
      url.includes('/login') ||
      url.includes('/register') ||
      url.includes('/profile') ||
      url.includes('/onboarding')) {
    return;
  }

  // 2. JS, CSS, HTML y raíz → SIEMPRE de la red, nunca desde caché
  //    Así los testers siempre bajan el código más nuevo automáticamente
  if (url.endsWith('.js') ||
      url.endsWith('.css') ||
      url.endsWith('.html') ||
      url === self.registration.scope) {
    event.respondWith(
      fetch(event.request, { cache: 'no-store' })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // 3. Assets de audio/video/imagen → caché primero, red como fallback
  //    Archivos pesados que no cambian; conviene cachearlos para carga rápida
  if (url.includes('/static/assets/')) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        });
      })
    );
    return;
  }

  // 4. Todo lo demás → red primero, caché como fallback offline
  event.respondWith(
    fetch(event.request)
      .then(response => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});