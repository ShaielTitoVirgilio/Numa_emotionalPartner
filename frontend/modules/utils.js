// modules/utils.js
import { runRespiracion } from './motorRespiracion.js';
import { runGuiado } from './motorGuiado.js';
import { iniciarSonidoAmbiente, detenerSonidoAmbiente } from './ambientSound.js';

// ============================================
// CONSTANTES
// ============================================

export const TIEMPO_ENFRIAMIENTO = 80000; // ~1 min 20 seg


// ============================================
// FUNCIONES PÚBLICAS
// ============================================

/**
 * Función dispatcher que inicia el ejercicio correcto.
 * Arranca el sonido de fondo automáticamente.
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
 
        // 🎵 Sonido de fondo solo en meditacion, yoga y lectura
        const conSonido = ["meditacion", "yoga", "lectura"];
        if (conSonido.includes(tipo)) {
            iniciarSonidoAmbiente();
        }
 
        if (tipo === "respiracion") {
            runRespiracion(data);
        } 
        else if (tipo === "meditacion" || tipo === "yoga") {
            runGuiado(tipo, data);
        }
        else if (tipo === "lectura") {
            if (window.showReading) window.showReading(data);
        }
    }, 3000);
}

/**
 * Detiene el sonido de fondo (llamado cuando el ejercicio termina o se cierra)
 * Los motores (motorRespiracion, motorGuiado) llaman esto al finalizar/detener.
 */
export function pararSonidoAmbiente() {
    detenerSonidoAmbiente();
}

// ============================================
// AVISO TESTER
// ============================================

export function mostrarAvisoTesterCada() {
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

      <div style="
        background: #eaf5f0; border: 2px solid #7db89e;
        border-radius: 12px; padding: 14px 16px; margin-bottom: 18px;
      ">
        <p style="font-size: 1rem; font-weight: 800; color: #2f4f45; margin: 0 0 6px;">
          🎙️ ¡NUEVA FEATURE!
        </p>
        <p style="font-size: .95rem; color: #3a6b5a; margin: 0; line-height: 1.4;">
          Ahora podés <strong>hablarle por micrófono a Numa</strong>.<br>
          ¡Probalo y contanos qué te parece! 💬
        </p>
      </div>

      <button id="tester-ok" style="
        padding: 12px 20px; border:none; border-radius:12px;
        background:#7db89e; color:white; cursor:pointer; font-weight:700;
      ">Entendido</button>
    </div>
  `;
  document.body.appendChild(modal);
  document.getElementById("tester-ok").onclick = () => {
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