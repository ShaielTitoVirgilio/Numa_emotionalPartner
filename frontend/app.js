// app.js
import { CATALOGO_EJERCICIOS } from './ejerciciosData.js';
import { enviarMensaje, agregarMensaje, inicializarChat } from './modules/chat.js';
import { 
    irAEjercicios, 
    cerrarMenuEjercicios,
    abrirSubmenu,
    volverAMenuPrincipal,
    volverAlChat 
} from './modules/menuEjercicios.js';
import { detenerRespiracion } from './modules/motorRespiracion.js';
import { detenerGuiado } from './modules/motorGuiado.js';
import { showReading, nextReading, prevReading, closeReading } from './modules/lectura.js';
import { showAuthScreen, hideAuthScreen, getCurrentUser, manejarCallbackOAuth } from './modules/auth.js';
import { showOnboarding, hideOnboarding } from './modules/onboarding.js';
import { mostrarAvisoTesterCada, authHeaders } from './modules/utils.js';
import { initDashboard } from './modules/dashboard.js';
import { initProfile, aplicarTamanoFuenteGuardado, aplicarTemaGuardado, alternarTemaChat } from './modules/profile.js';
import { mostrarSelectorSonido } from './modules/ambientSound.js';
import { toggleMic } from "./modules/chat.js";

// ============================================
// EXPONER FUNCIONES AL WINDOW
// ============================================

window.enviarMensaje = enviarMensaje;
window.irAEjercicios = irAEjercicios;
window.cerrarMenuEjercicios = cerrarMenuEjercicios;
window.volverAMenuPrincipal = volverAMenuPrincipal;
window.volverAlChat = volverAlChat;
window.detenerRespiracion = detenerRespiracion;
window.detenerGuiado = detenerGuiado;
window.showReading = showReading;
window.nextReading = nextReading;
window.prevReading = prevReading;
window.closeReading = closeReading;
window.agregarMensaje = agregarMensaje;
window.showOnboarding = showOnboarding;
window.initDashboard = initDashboard;
window.initProfile = initProfile;
window.mostrarSelectorSonido = mostrarSelectorSonido;
window.toggleMic = toggleMic;
window.alternarTemaChat = alternarTemaChat;
window.inicializarChat = inicializarChat;




// ============================================
// NOTIFICACIONES PUSH
// ============================================

function urlB64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

async function suscribirANotificaciones(userId) {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;

  try {
    const permiso = await Notification.requestPermission();
    if (permiso !== 'granted') return;

    const registro = await navigator.serviceWorker.ready;

    // TODO: REEMPLAZA ESTO CON TU VAPID PUBLIC KEY
    const vapidPublicKey = "BNAHZjDGp79UzaP_sfHU2cA7kLwKdKPmlj1Q-20HvO6wWsfg3PqXXASqlWTirck3-Eol47e1PCPp734Y65XoxVg=";

    const applicationServerKey = urlB64ToUint8Array(vapidPublicKey);

    const suscripcion = await registro.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: applicationServerKey
    });

    await fetch('/subscribe', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        subscription_data: suscripcion
      })
    });
  } catch (e) {
    console.error('Error suscribiendo a notificaciones:', e);
  }
}

// ============================================
// INICIALIZACIÓN
// ============================================

function _tokenExpired(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.exp < Date.now() / 1000;
  } catch {
    return true;
  }
}

async function init() {
  aplicarTemaGuardado();
  aplicarTamanoFuenteGuardado();
  const fueOAuth = await manejarCallbackOAuth();
  if (fueOAuth) return;

  const savedUser = localStorage.getItem('numa_user');
  if (!savedUser) {
    showAuthScreen();
    return;
  }

  const user = JSON.parse(savedUser);

  if (_tokenExpired(user.access_token)) {
    if (user.refresh_token) {
      try {
        const r = await fetch('/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: user.refresh_token })
        });
        if (r.ok) {
          const fresh = await r.json();
          Object.assign(user, fresh);
          localStorage.setItem('numa_user', JSON.stringify(user));
        } else {
          localStorage.removeItem('numa_user');
          showAuthScreen();
          return;
        }
      } catch {
        localStorage.removeItem('numa_user');
        showAuthScreen();
        return;
      }
    } else {
      localStorage.removeItem('numa_user');
      showAuthScreen();
      return;
    }
  }

  try {
    const res = await fetch(`/profile/${user.user_id}`, { headers: authHeaders() });

    if (res.status === 401) {
      localStorage.removeItem('numa_user');
      showAuthScreen();
      return;
    }

    if (!res.ok) {
      // Server error — don't force onboarding, just open chat
      await inicializarChat();
      agregarMensaje("Hola 🐼 ¿Cómo estás?", "oso");
      return;
    }

    const profile = await res.json();

    if (!profile.onboarding_completo) {
      showOnboarding(user.user_id);
    } else {
      const huboHistorial = await inicializarChat();
      // Si se rehidrató la charla anterior, el saludo largo sobra
      if (huboHistorial) {
        agregarMensaje(`Bienvenido de vuelta 🐼`, "oso");
      } else {
        agregarMensaje(`Bienvenido ${user.name || 'de vuelta'} 🐼 Me alegra que estés aquí.`, "oso");
      }
      mostrarAvisoTesterCada();
      mostrarBannerNotificaciones(user.user_id);
    }
  } catch (e) {
    agregarMensaje("Hola 🐼 ¿Cómo estás?", "oso");
  }
}
init();
function mostrarBannerNotificaciones(userId) {
  if (Notification.permission !== 'default') return;

  const banner = document.createElement('div');
  banner.id = 'banner-notif';
  banner.className = 'banner-notif';
  banner.setAttribute('role', 'dialog');
  banner.setAttribute('aria-label', 'Activar notificaciones');
  banner.innerHTML = `
    <div class="banner-notif-emoji">🐼</div>
    <p class="banner-notif-texto">
      ¿Querés que Numa te mande un mensajito de vez en cuando?
    </p>
    <button id="btn-si-notif" class="banner-notif-si">Sí, activar notificaciones</button>
    <button id="btn-no-notif" class="banner-notif-no">Ahora no</button>
  `;
  document.body.appendChild(banner);

  document.getElementById('btn-si-notif').addEventListener('click', () => {
    banner.remove();
    suscribirANotificaciones(userId);
  });
  document.getElementById('btn-no-notif').addEventListener('click', () => {
    banner.remove();
  });
}