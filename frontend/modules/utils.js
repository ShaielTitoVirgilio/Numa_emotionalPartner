// modules/utils.js
import { runRespiracion } from './motorRespiracion.js';
import { runGuiado } from './motorGuiado.js';

// ============================================
// CONSTANTES
// ============================================

export const TIEMPO_ENFRIAMIENTO = 300000; // 5 minutos

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

/**
 * Función dispatcher que inicia el ejercicio correcto
 * Muestra pantalla de preparación antes de comenzar
 */
export function iniciarEjercicio(tipo, data) {
    const prep = document.getElementById("prep-screen");
    const prepText = document.getElementById("prep-text");
    
    // Cerrar menús
    document.getElementById("ejercicios-menu").classList.add("hidden");
    document.getElementById("submenu-detalle").classList.add("hidden");

    // Mostrar pantalla de preparación
    prep.classList.remove("hidden");
    prepText.innerText = `Preparando ${data.nombre}...`;

    // Esperar 3 segundos antes de empezar
    setTimeout(() => {
        prep.classList.add("hidden");
        
        // Dispatcher: decidir qué motor usar
        if (tipo === "respiracion") {
            runRespiracion(data);
        } 
        else if (tipo === "meditacion" || tipo === "yoga") {
            runGuiado(tipo, data);
        }
    }, 3000);
}

/**
 * Obtiene un ejercicio del catálogo por ID
 */
export function getEjercicioPorId(id, catalogo) {
    for (const [tipo, lista] of Object.entries(catalogo)) {
        const found = lista.find(e => e.id === id);
        if (found) {
            return { ejercicio: found, tipo };
        }
    }
    return null;
}