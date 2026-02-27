// app.js - Archivo principal (orquestador)

import { CATALOGO_EJERCICIOS } from './ejerciciosData.js';
import { enviarMensaje, agregarMensaje, recibirFeedbackEjercicio } from './modules/chat.js';
import { 
  irAEjercicios, 
  cerrarMenuEjercicios,
  abrirSubmenu,
  volverAMenuPrincipal,
  volverAlChat 
} from './modules/menuEjercicios.js';
import { detenerRespiracion, setFeedbackCallback as setRespiracionFeedback } from './modules/motorRespiracion.js';
import { detenerGuiado, setFeedbackCallback as setGuiadoFeedback } from './modules/motorGuiado.js';
import { 
  showReading, 
  nextReading, 
  closeReading 
} from './modules/lectura.js';

// ============================================
// CONECTAR FEEDBACK DE EJERCICIOS → CHAT
// ============================================

// Callback compartido: cuando el usuario responde el feedback,
// chat.js recibe la respuesta del usuario + la respuesta de Numa
const handleFeedback = (textoOpcion, respuestaNuma, valor) => {
  recibirFeedbackEjercicio(textoOpcion, respuestaNuma, valor);
};

setRespiracionFeedback(handleFeedback);
setGuiadoFeedback(handleFeedback);

// ============================================
// EXPONER FUNCIONES AL WINDOW (para HTML inline)
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

console.log("✅ Numa cargado correctamente");
console.log(`📚 Catálogo: ${Object.keys(CATALOGO_EJERCICIOS).length} categorías`);

agregarMensaje("Hola, soy Numa 🐼 Estoy acá si querés hablar, desahogarte, o simplemente no estar solo. ¿Cómo estás hoy?", "oso");