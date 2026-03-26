// ============================================
// SERVICE WORKER — Numa v6
// Estrategia:
//   JS / CSS  → siempre de la red (nunca cacheados)
//   Assets    → cacheados (audio, video, imágenes)
//   API       → siempre de la red, sin interceptar
// ============================================

const CACHE_NAME = 'numa-v5.12';

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

  if (url.includes('/chat') ||
      url.includes('/login') ||
      url.includes('/register') ||
      url.includes('/profile') ||
      url.includes('/onboarding') ||
      url.includes('/subscribe')) { // Añadido /subscribe
    return;
  }

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

// ── Push Notifications ──────────────────────
self.addEventListener('push', function(event) {
  const data = event.data ? event.data.json() : {
    title: "Numa 🐼",
    body: "Hola, ¿querés contarme cómo te está yendo estos días?"
  };

  const opciones = {
    body: data.body,
    icon: '/static/icons/icon-192.png', // Usa el ícono que ya tienes
    badge: '/static/icons/icon-192.png',
    vibrate: [200, 100, 200],
    data: { url: '/' } // A dónde ir al hacer click
  };

  event.waitUntil(
    self.registration.showNotification(data.title, opciones)
  );
});

// ── Click en la Notificación ────────────────
self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(windowClients => {
      // Si ya hay una pestaña abierta de Numa, la pone en foco
      for (var i = 0; i < windowClients.length; i++) {
        var client = windowClients[i];
        if (client.url === '/' && 'focus' in client) {
          return client.focus();
        }
      }
      // Si no, abre una nueva
      if (clients.openWindow) {
        return clients.openWindow('/');
      }
    })
  );
});