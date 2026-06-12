// modules/utils.js
import { runRespiracion } from './motorRespiracion.js';
import { runGuiado } from './motorGuiado.js';
import { iniciarSonidoAmbiente, detenerSonidoAmbiente } from './ambientSound.js';

// ============================================
// CONSTANTES
// ============================================

export const TIEMPO_ENFRIAMIENTO = 80000; // ~1 min 20 seg


// ============================================
// AUTH HELPERS
// El backend ahora valida el token en cada endpoint:
// todas las llamadas a la API deben mandar Authorization.
// ============================================

export function getAuthUser() {
    try {
        return JSON.parse(localStorage.getItem('numa_user')) || null;
    } catch {
        return null;
    }
}

export function authHeaders(extra = {}) {
    const user = getAuthUser();
    const headers = { ...extra };
    if (user?.access_token) {
        headers['Authorization'] = `Bearer ${user.access_token}`;
    }
    return headers;
}


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
  // No mostrar si ya está corriendo como PWA instalada
  const yaInstalada =
    window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true;
  if (yaInstalada) return;

  // No mostrar más de una vez
  if (localStorage.getItem('numa_install_shown')) return;

  const modal = document.createElement("div");
  modal.id = "tester-modal";
  modal.style.cssText = `
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.45);
    display: flex; align-items: center; justify-content: center;
    z-index: 9999; padding: 20px;
    overflow-y: auto;
  `;
  modal.innerHTML = `
    <div style="
      background: white; padding: 24px; border-radius: 16px;
      max-width: 380px; width: 100%; text-align: center; font-family: inherit;
      color: #2f4f45; box-shadow: 0 12px 30px rgba(0,0,0,0.15);
      margin: auto;
    ">
      <p style="font-size:2rem; margin:0 0 6px;">📲</p>
      <h2 style="margin:0 0 8px; font-size:1.15rem;">Instalá Numa en tu celular</h2>
      <p style="font-size:.88rem; color:#6b8e7d; margin:0 0 18px; line-height:1.5;">
        Guardá el ícono en tu pantalla para volver cuando quieras, sin necesitar el link.
      </p>

      <!-- iPhone / Safari -->
      <div style="
        background:#eaf5f0; border:2px solid #7db89e;
        border-radius:12px; padding:14px 16px; margin-bottom:12px; text-align:left;
      ">
        <p style="font-weight:800; margin:0 0 8px; font-size:.95rem;">🍎 iPhone (Safari)</p>
        <ol style="padding-left:18px; margin:0; line-height:2.1; font-size:.9rem; color:#3a6b5a;">
          <li>Tocá el botón compartir <strong>⬆</strong> (abajo en la pantalla)</li>
          <li>Bajá y tocá <strong>"Añadir a pantalla de inicio"</strong></li>
          <li>Tocá <strong>"Añadir"</strong> arriba a la derecha</li>
        </ol>
      </div>

      <!-- Android / Chrome -->
      <div style="
        background:#eaf5f0; border:2px solid #7db89e;
        border-radius:12px; padding:14px 16px; margin-bottom:18px; text-align:left;
      ">
        <p style="font-weight:800; margin:0 0 8px; font-size:.95rem;">🤖 Android (Chrome)</p>
        <ol style="padding-left:18px; margin:0; line-height:2.1; font-size:.9rem; color:#3a6b5a;">
          <li>Tocá el menú <strong>⋮</strong> (tres puntos, arriba a la derecha)</li>
          <li>Tocá <strong>"Añadir a pantalla de inicio"</strong> o <strong>"Instalar app"</strong></li>
          <li>Confirmá tocando <strong>"Instalar"</strong></li>
        </ol>
      </div>

      <button id="tester-ok" style="
        width:100%; padding:13px; border:none; border-radius:12px;
        background:#7db89e; color:white; cursor:pointer;
        font-weight:700; font-size:1rem; font-family:inherit;
      ">¡Listo, ya lo instalo!</button>
      <button id="tester-skip" style="
        width:100%; padding:10px; border:none; background:none;
        color:#7db89e; cursor:pointer; font-size:.9rem;
        margin-top:6px; font-family:inherit; font-weight:600;
      ">Ahora no</button>
      <button id="tester-never" style="
        width:100%; padding:8px; border:none; background:none;
        color:#bbb; cursor:pointer; font-size:.8rem;
        margin-top:2px; font-family:inherit;
      ">No volver a mostrar</button>
    </div>
  `;
  document.body.appendChild(modal);

  const cerrarYMarcar = () => {
    localStorage.setItem('numa_install_shown', '1');
    modal.remove();
  };
  const cerrarSinMarcar = () => modal.remove();

  document.getElementById("tester-ok").onclick = cerrarYMarcar;
  document.getElementById("tester-skip").onclick = cerrarSinMarcar;
  document.getElementById("tester-never").onclick = cerrarYMarcar;

  // Escape = cerrar (accesibilidad)
  const onEsc = (e) => {
    if (e.key === 'Escape') {
      cerrarSinMarcar();
      document.removeEventListener('keydown', onEsc);
    }
  };
  document.addEventListener('keydown', onEsc);
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