// modules/utils.js
import { runRespiracion } from './motorRespiracion.js';
import { runGuiado } from './motorGuiado.js';

// ============================================
// CONSTANTES
// ============================================

export const TIEMPO_ENFRIAMIENTO = 200000; //  5 minutos


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
// utils.js
export function mostrarAvisoTesterCada(periodoHoras = 12) {
    const key = 'numa_tester_banner_last_ts';
    const last = Number(localStorage.getItem(key) || 0);
    const ahora = Date.now();
    const msPeriodo = periodoHoras * 3600 * 1000;
  
    if (ahora - last < msPeriodo) return; // dentro del periodo -> no mostrar
  
    const modal = document.createElement("div");
    modal.id = "tester-modal";
    modal.style.cssText = `
      position: fixed; inset: 0;
      background: rgba(0,0,0,0.45);
      display: flex; align-items: center; justify-content: center;
      z-index: 9999; padding: 20px;
    `;
    modal.innerHTML = `
      <div style="
        background: white; padding: 24px; border-radius: 16px;
        max-width: 380px; text-align: center; font-family: inherit;
        color: #2f4f45; box-shadow: 0 12px 30px rgba(0,0,0,0.15);
      ">
        <h2 style="margin-bottom: 10px;">🐼 ¡Gracias por estar acá!</h2>
        <p style="margin-bottom: 14px; line-height: 1.5;">
          Estás usando una versión en <strong>fase de prueba</strong>.
          Sos parte del grupo privado de testers que ayudan a mejorar Numa con feedback, ideas y reportes.
        </p>
        <p style="font-size: .9rem; color:#6b8e7d; margin-bottom: 18px;">
          En el lanzamiento oficial, vas a tener
          <strong>acceso gratis</strong> como agradecimiento 💚
        </p>
        <button id="tester-ok" style="
          padding: 12px 20px; border:none; border-radius:12px;
          background:#7db89e; color:white; cursor:pointer; font-weight:700;
        ">Entendido</button>
      </div>
    `;
    document.body.appendChild(modal);
    document.getElementById("tester-ok").onclick = () => {
      localStorage.setItem(key, String(ahora));
      modal.remove();
    };
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