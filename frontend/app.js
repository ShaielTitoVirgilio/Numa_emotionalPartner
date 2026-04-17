// app.js
import { CATALOGO_EJERCICIOS } from './ejerciciosData.js';
import { enviarMensaje, agregarMensaje, inicializarChat, mostrarProximamente} from './modules/chat.js';
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
import { showAuthScreen, hideAuthScreen, getCurrentUser } from './modules/auth.js';
import { showOnboarding, hideOnboarding } from './modules/onboarding.js';
import { mostrarAvisoTesterCada } from './modules/utils.js';
import { initFeedbackTab } from './modules/feedbackTab.js';
import { initDashboard } from './modules/dashboard.js';
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
window.mostrarProximamente = mostrarProximamente;
window.initFeedbackTab = initFeedbackTab;
window.initDashboard = initDashboard;
window.mostrarSelectorSonido = mostrarSelectorSonido;
window.toggleMic = toggleMic;




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

    const user = JSON.parse(localStorage.getItem('numa_user'));

    await fetch('/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        subscription_data: suscripcion
      })
    });
    console.log("Suscripción a notificaciones exitosa.");
  } catch (e) {
    console.error('Error suscribiendo a notificaciones:', e);
  }
}

// ============================================
// INICIALIZACIÓN
// ============================================

async function init() {
  const savedUser = localStorage.getItem('numa_user');
  if (!savedUser) {
    showAuthScreen();
    return;
  }

  const user = JSON.parse(savedUser);
  
  try {
    const res = await fetch(`/profile/${user.user_id}`);
    const profile = await res.json();

    if (!profile.onboarding_completo) {
      showOnboarding(user.user_id);
    } else {
      await inicializarChat();
      agregarMensaje(`Bienvenido ${user.name || 'de vuelta'} 🐼 Me alegra que estés aquí.`, "oso");
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
  banner.innerHTML = `
    <div style="font-size:2rem; margin-bottom:8px;">🐼</div>
    <p style="margin:0 0 16px; font-size:1rem; line-height:1.5; text-align:center;">
      ¿Querés que Numa te mande un mensajito de vez en cuando?
    </p>
    <button id="btn-si-notif" style="
      width: 100%;
      padding: 14px;
      background: #7db89e;
      color: white;
      border: none;
      border-radius: 14px;
      font-size: 1.1rem;
      font-weight: 700;
      cursor: pointer;
      margin-bottom: 10px;
    ">Sí, activar notificaciones</button>
    <button id="btn-no-notif" style="
      width: 100%;
      padding: 12px;
      background: transparent;
      color: #aaa;
      border: none;
      font-size: 0.95rem;
      cursor: pointer;
    ">Ahora no</button>
  `;
  Object.assign(banner.style, {
    position: 'fixed',
    bottom: '0',
    left: '0',
    right: '0',
    background: '#2f4f45',
    color: 'white',
    padding: '24px 24px 36px', // 36px abajo por el home indicator del iPhone
    borderRadius: '24px 24px 0 0',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    zIndex: '9999',
    boxShadow: '0 -4px 30px rgba(0,0,0,0.3)',
  });
  document.body.appendChild(banner);

  document.getElementById('btn-si-notif').addEventListener('click', () => {
    banner.remove();
    suscribirANotificaciones(userId);
  });
  document.getElementById('btn-no-notif').addEventListener('click', () => {
    banner.remove();
  });
}