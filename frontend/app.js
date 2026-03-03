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

// ============================================
// INICIALIZACIÓN
// ============================================

function init() {
    // Verificar si ya hay sesión guardada
    const savedUser = localStorage.getItem('numa_user');

    if (savedUser) {
        // Ya tiene sesión → ir directo al chat
        agregarMensaje("Bienvenido de nuevo 🐼 ¿Cómo estás hoy?", "oso");
    } else {
        // No tiene sesión → mostrar login
        showAuthScreen();
    }
}

init();