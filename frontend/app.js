// app.js
import { CATALOGO_EJERCICIOS } from './ejerciciosData.js';
import { enviarMensaje, agregarMensaje } from './modules/chat.js';
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

    // Verificar si completó el onboarding
    try {
        const res = await fetch(`/profile/${user.user_id}`);
        const profile = await res.json();

        if (!profile.onboarding_completo) {
            // Primera vez → mostrar onboarding
            showOnboarding(user.user_id);
        } else {
            // Ya completó → ir al chat
            agregarMensaje(`Bienvenido de nuevo 🐼 ¿Cómo estás hoy?`, "oso");
        }
    } catch (e) {
        agregarMensaje("Hola 🐼 ¿Cómo estás hoy?", "oso");
    }
}

init();