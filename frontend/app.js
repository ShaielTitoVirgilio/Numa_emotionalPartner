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
import { showReading, nextReading, closeReading } from './modules/lectura.js';
import { showAuthScreen, hideAuthScreen, getCurrentUser } from './modules/auth.js';
import { showOnboarding, hideOnboarding } from './modules/onboarding.js';
import { mostrarAvisoTesterCada } from './modules/utils.js';
import { initFeedbackTab } from './modules/feedbackTab.js';
import { mostrarSelectorSonido } from './modules/ambientSound.js';

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
window.closeReading = closeReading;
window.agregarMensaje = agregarMensaje;
window.showOnboarding = showOnboarding;
window.mostrarProximamente = mostrarProximamente;
window.initFeedbackTab = initFeedbackTab;
window.mostrarSelectorSonido = mostrarSelectorSonido;

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
      agregarMensaje(`Bienvenido ${user.name} 🐼 Me alegra tenerte de vuelta`, "oso");
      mostrarAvisoTesterCada();
    }
  } catch (e) {
    agregarMensaje("Hola 🐼 ¿Cómo estás?", "oso");
  }
}
init();