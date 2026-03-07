const CACHE_NAME = 'numa-v1';
const ASSETS = [
  '/',
  '/static/styles.css',
  '/static/app.js',
  '/static/bear3d.js',
  '/static/ejerciciosData.js',
  '/static/modules/chat.js',
  '/static/modules/auth.js',
  '/static/modules/onboarding.js',
  '/static/modules/menuEjercicios.js',
  '/static/modules/motorRespiracion.js',
  '/static/modules/motorGuiado.js',
  '/static/modules/feedbackPost.js',
  '/static/modules/lectura.js',
  '/static/modules/utils.js',
];

// Instalación — cachear assets estáticos
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
  );
  self.skipWaiting();
});

// Activación — limpiar caches viejos
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch — red primero, cache como fallback
self.addEventListener('fetch', event => {
  // Las llamadas a la API siempre van a la red
  if (event.request.url.includes('/chat') ||
      event.request.url.includes('/login') ||
      event.request.url.includes('/register') ||
      event.request.url.includes('/profile') ||
      event.request.url.includes('/onboarding')) {
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