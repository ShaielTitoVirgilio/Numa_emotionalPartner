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

// ── Sesión: refresco resiliente + proactivo ────────────────────────────
//
// Mismo problema y misma solución que numa-mobile (ver
// numa-mobile/src/services/tokenRefresh.ts y api.ts, y el backend
// app/auth_service.py): antes SOLO se refrescaba una vez, al cargar la
// página (init() en app.js), y CUALQUIER fallo — un hipo de red, un cold
// start de Railway — cerraba la sesión directo, sin distinguir un 401
// genuino de un error transitorio. Como el access_token dura 1 hora,
// dejar la pestaña abierta ese tiempo bastaba para que la siguiente
// llamada reventara con 401 sin haber intentado refrescar antes.
//
// authHeaders() ahora es async y llama a ensureFreshToken() antes de
// armar el header — así CUALQUIER llamada autenticada (no solo el
// arranque de la página) dispara el refresco si hace falta.
//
// _enVuelo dedupea llamadas concurrentes: varias secciones piden datos
// a la vez al abrir la página (perfil, checkin, memorias...), y cada una
// refrescando por su cuenta mandaría dos /refresh con el MISMO
// refresh_token — de un solo uso, reenviarlo revoca toda la familia de
// tokens (Supabase: "Invalid Refresh Token: Already Used").

let _enVuelo = null;
let _onSessionInvalid = null;

/** Se llama cuando el refresh token resultó genuinamente inválido, para
 *  que sea app.js (dueño del estado de sesión/pantallas) quien haga el
 *  logout completo — limpiar el chat, mostrar la pantalla de login —
 *  en vez de que este módulo lo haga a medias. */
export function setSessionInvalidHandler(cb) {
    _onSessionInvalid = cb;
}

/** ¿El JWT ya venció? */
export function tokenExpired(token) {
    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        return payload.exp < Date.now() / 1000;
    } catch {
        return true;
    }
}

/**
 * Un solo intento de /refresh. NUNCA reintenta con el mismo refresh_token:
 * un fetch que tira no garantiza que el pedido no haya llegado al server
 * (pudo procesarlo y rotar el token igual, y perderse la respuesta en el
 * camino) — reintentar a ciegas ahí es lo que mandaba el mismo token dos
 * veces y disparaba el "Already Used" (ver el fix idéntico en
 * numa-mobile/src/services/api.ts, refreshResilient).
 *
 * Devuelve el user actualizado, 'keep' (fallo transitorio, no desloguear)
 * o 'clear' (401: el refresh token está muerto).
 */
async function refreshResilient(refreshToken) {
    try {
        const r = await fetch('/refresh', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (r.ok) return await r.json();
        return r.status === 401 ? 'clear' : 'keep';
    } catch {
        // Sin respuesta HTTP: no hay forma de saber si el pedido llegó al
        // server. Se conserva la sesión y se reintenta en la próxima
        // llamada, nunca reenviando el mismo refresh_token acá mismo.
        return 'keep';
    }
}

/** Devuelve un access_token en condiciones de usarse, refrescándolo antes
 *  si ya venció. `force=true` lo refresca aunque el JWT diga que sigue
 *  vigente (backstop para cuando el server lo rechaza por otro motivo).
 *  Llamadas concurrentes mientras hay un refresh en curso esperan la
 *  MISMA promesa — nunca disparan un segundo /refresh por su cuenta. */
export async function ensureFreshToken(force = false) {
    const user = getAuthUser();
    if (!user?.access_token) return null;
    if (!force && !tokenExpired(user.access_token)) return user.access_token;
    if (_enVuelo) return _enVuelo;
    if (!user.refresh_token) return user.access_token; // nada con qué renovar

    _enVuelo = (async () => {
        try {
            const resultado = await refreshResilient(user.refresh_token);
            if (resultado === 'clear') {
                localStorage.removeItem('numa_user');
                _onSessionInvalid?.();
                return null;
            }
            if (resultado === 'keep') return user.access_token;
            const actualizado = { ...user, ...resultado };
            localStorage.setItem('numa_user', JSON.stringify(actualizado));
            return actualizado.access_token;
        } finally {
            _enVuelo = null;
        }
    })();
    return _enVuelo;
}

export async function authHeaders(extra = {}) {
    const headers = { ...extra };
    const token = await ensureFreshToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
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

// ============================================
// AVISO DESCARGAR APP (iOS / Android)
// ============================================

const APP_STORE_URL = 'https://apps.apple.com/us/app/numa-app/id6788907827';
const PLAY_STORE_URL = 'https://play.google.com/store/apps/details?id=app.numa.mobile&hl=es_419';

/**
 * Alert que avisa que Numa ya se puede descargar como app (iOS/Android) y
 * que la web va a dejar de funcionar. Se muestra cada vez que el usuario
 * entra a su cuenta (no se guarda flag de "no volver a mostrar": es a
 * propósito, hasta que se bajen la app).
 */
export function mostrarAvisoDescargarApp() {
  const modal = document.createElement('div');
  modal.id = 'download-app-modal';
  modal.style.cssText = `
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.45);
    display: flex; align-items: center; justify-content: center;
    z-index: 10000; padding: 20px;
    overflow-y: auto;
  `;

  const cardStyle = `
    background: white; padding: 24px; border-radius: 16px;
    max-width: 400px; width: 100%; text-align: center; font-family: inherit;
    color: #2f4f45; box-shadow: 0 12px 30px rgba(0,0,0,0.15);
    margin: auto;
  `;

  const vistaPrincipal = `
    <div id="download-app-main" style="${cardStyle}">
      <p style="font-size:2rem; margin:0 0 6px;">📲🐼</p>
      <h2 style="margin:0 0 8px; font-size:1.2rem;">¡Numa ya se puede descargar!</h2>
      <p style="font-size:.9rem; color:#6b8e7d; margin:0 0 16px; line-height:1.55;">
        Ya está la versión de prueba de la app para <strong>iOS</strong> y <strong>Android</strong>.
        Anda mucho más fluida que la web y tiene más funciones — y muy pronto
        <strong>la web va a dejar de funcionar</strong>, así que para seguir usando Numa
        vas a necesitar bajarte la app. ¡Ayudanos descargándola ya!
      </p>

      <p style="font-weight:800; margin:0 0 10px; font-size:.92rem;">Descargá la app en:</p>

      <div style="display:flex; gap:10px; margin-bottom:12px;">
        <a id="btn-download-ios" href="${APP_STORE_URL}" target="_blank" rel="noopener" style="
          flex:1; padding:13px; border:none; border-radius:12px;
          background:#7db89e; color:white; cursor:pointer; text-decoration:none;
          font-weight:700; font-size:.95rem; font-family:inherit;
        ">iOS</a>
        <a id="btn-download-android" href="${PLAY_STORE_URL}" target="_blank" rel="noopener" style="
          flex:1; padding:13px; border:none; border-radius:12px;
          background:#7db89e; color:white; cursor:pointer; text-decoration:none;
          font-weight:700; font-size:.95rem; font-family:inherit;
        ">Android</a>
      </div>

      <button id="download-app-cerrar" style="
        width:100%; padding:10px; border:none; background:none;
        color:#7db89e; cursor:pointer; font-size:.9rem;
        margin-top:2px; font-family:inherit; font-weight:600;
      ">Ahora no</button>
    </div>
  `;

  modal.innerHTML = vistaPrincipal;
  document.body.appendChild(modal);

  document.getElementById('download-app-cerrar').onclick = () => modal.remove();

  const onEsc = (e) => {
    if (e.key === 'Escape') {
      modal.remove();
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