// modules/chat.js
import { CATALOGO_EJERCICIOS } from '../ejerciciosData.js';
import { iniciarEjercicio } from './utils.js';
import { TIEMPO_ENFRIAMIENTO } from './utils.js';
// ============================================
// ESTADO Y CONFIGURACIÓN
// ============================================

const chat = document.getElementById("chat");
const input = document.getElementById("input");

// 🧠 Historial de conversación — limitado a últimos 20 mensajes
let historialConversacion = [];
const MAX_HISTORIAL = 20;

// 👤 Perfil cacheado — se carga una vez al inicio, se actualiza si hay memoria nueva
let perfilCacheado = null;

// ⏱️ Control de Enfriamiento
let ultimoEjercicioSugeridoTime = 0;


// 🐻 Estados del oso según mood
const MOOD_TO_BEAR_STATE = {
  stressed:    'stressed',
  overwhelmed: 'stressed',
  sad:         'sad',
  anxious:     'thinking',
  happy:       'happy',
  excited:     'happy',
  calm:        'calm',
  neutral:     'calm',
};

// 💬 Frases de introducción para sugerencia de ejercicio
const FRASES_POR_MOOD = {
  stressed:    "Che, probá esto. Ayuda más de lo que parece:",
  overwhelmed: "Para un segundo. Esto puede acomodarte:",
  sad:         "No tenés que hacer nada grande. Esto es suave:",
  anxious:     "Para bajar un cambio:",
  default:     "Esto podría ayudarte ahora:",
};

// 🏷️ Etiquetas de mood para el indicador
const MOOD_LABELS = {
  stressed:    '😤 un poco estresado/a',
  overwhelmed: '😮‍💨 bastante al límite',
  sad:         '🌧️ bajón',
  happy:       '☀️ bien',
  excited:     '✨ con energía',
  anxious:     '😬 ansioso/a',
  calm:        '🌿 tranquilo/a',
  neutral:     '',
};

// ============================================
// INICIALIZACIÓN — cargar perfil al arrancar
// ============================================

export async function inicializarChat() {
  const numaUser = localStorage.getItem('numa_user');
  if (!numaUser) return;

  const user = JSON.parse(numaUser);

  try {
    const res = await fetch(`/profile/${user.user_id}`);
    if (res.ok) {
      perfilCacheado = await res.json();
    }
  } catch (e) {
    console.warn('No se pudo cargar el perfil:', e);
  }
}

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

export function agregarMensaje(texto, tipo, mood = null) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${tipo}`;

  if (typeof texto === "string") {
    bubble.innerText = texto;
  } else if (texto && typeof texto === "object" && texto.oso) {
    bubble.innerText = texto.oso;
  } else {
    bubble.innerText = "…";
  }

  if (tipo === "oso" && mood) {
    bubble.classList.add(`mood-${mood}`);
  }

  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
}

export async function enviarMensaje() {
  const texto = input.value.trim();
  if (!texto) return;

  agregarMensaje(texto, "user");
  input.value = "";
  _prepararEnvio();

  try {
    const data = await _llamarBackend(texto);
    _procesarRespuesta(data, texto);
  } catch (error) {
    _manejarError(error);
  }
}

export function recibirFeedbackEjercicio(textoOpcion, respuestaNuma, valor) {
  agregarMensaje(textoOpcion, "user");

  setTimeout(() => {
    const moodParaFeedback = _valorAMood(valor);
    agregarMensaje(respuestaNuma, "oso", moodParaFeedback);

    if (window.setBearState) {
      window.setBearState(MOOD_TO_BEAR_STATE[moodParaFeedback] || 'calm');
    }

    historialConversacion.push({ role: "user", content: `[Post-ejercicio] ${textoOpcion}` });
    historialConversacion.push({ role: "assistant", content: respuestaNuma });
    _trimHistorial();

    chat.scrollTop = chat.scrollHeight;
  }, 400);
}

// ============================================
// FUNCIONES PRIVADAS — ENVÍO
// ============================================

function _prepararEnvio() {
  if (window.setBearState) window.setBearState('listening');
  mostrarTyping();
}

async function _llamarBackend(texto) {
  // Limitar historial antes de enviar
  const historialLimitado = historialConversacion.slice(-MAX_HISTORIAL);

  const conversationToSend = [
    ...historialLimitado,
    { role: "user", content: texto }
  ];

  const numaUser = localStorage.getItem('numa_user');
  const userId = numaUser ? JSON.parse(numaUser).user_id : null;

  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation: conversationToSend,
      user_id: userId,
      perfil: perfilCacheado,   // ← mandamos el perfil cacheado, backend no lo busca en DB
    })
  });

  if (!res.ok) {
    const errorText = await res.text();
    console.error("❌ ERROR DEL SERVIDOR:", errorText);
    throw new Error("Error en respuesta HTTP");
  }

  return await res.json();
}

function _procesarRespuesta(data, textoUsuario) {
  console.log("📨 Respuesta completa del backend:", JSON.stringify(data, null, 2));
  const mood = data.mood || 'neutral';
  const textoLimpio = _limpiarMensaje(data.message);

  ocultarTyping();
  agregarMensaje(textoLimpio, "oso", mood);

  if (window.setBearState) window.setBearState(MOOD_TO_BEAR_STATE[mood] || 'calm');
  actualizarMoodIndicator(mood);

  _actualizarHistorial(textoUsuario, textoLimpio);
  _manejarSugerencia(data, mood);

  // Si el backend detectó una memoria nueva, actualizarla en el perfil cacheado
  // para que los próximos mensajes ya la tengan en cuenta
  if (data.nueva_memoria && perfilCacheado) {
    if (!perfilCacheado._memorias_sesion) {
      perfilCacheado._memorias_sesion = [];
    }
    perfilCacheado._memorias_sesion.push(data.nueva_memoria);
  }
}

function _limpiarMensaje(mensaje) {
  return mensaje.replace(/\[EJERCICIO:\s*(\w+)\]/, "").trim();
}

function _actualizarHistorial(textoUsuario, textoOso) {
  historialConversacion.push({ role: "user", content: textoUsuario });
  historialConversacion.push({ role: "assistant", content: textoOso });
  _trimHistorial();
}

// Mantener el historial dentro del límite
function _trimHistorial() {
  if (historialConversacion.length > MAX_HISTORIAL) {
    historialConversacion = historialConversacion.slice(-MAX_HISTORIAL);
  }
}

function _manejarSugerencia(data, mood) {
  console.log("🔍 _manejarSugerencia llamada con:", { data, mood });
  const regexEjercicio = /\[EJERCICIO:\s*(\w+)\]/;
  const ejercicioId = (data.suggested_action && data.suggested_action !== 'none')
      ? data.suggested_action
      : data.message.match(regexEjercicio)?.[1] ?? null;
    console.log("🎯 ejercicioId detectado:", ejercicioId);
    console.log("📦 suggested_action del backend:", data.suggested_action);
    console.log("📝 mensaje crudo del backend:", data.message);
  if (!ejercicioId){
    console.log("⛔ Sin ejercicio — se corta acá");
    return;
  }

  // Si el ejercicio requiere espacio físico y el usuario parece estar ocupado/en trabajo
  const ejerciciosFisicos = ['yoga_cuello', 'yoga_ansiedad', 'meditacion_bodyscan', 'meditacion_mindfulness'];
  const ultimoMensajeUsuario = historialConversacion.filter(m => m.role === 'user').slice(-1)[0]?.content?.toLowerCase() || '';
  const contextoCupado = /trabajo|ocupado|cansad|sin tiempo|jefe|reunión|oficina/i.test(ultimoMensajeUsuario);

  if (contextoCupado && ejerciciosFisicos.includes(ejercicioId)) {
      console.log("Ejercicio físico suprimido por contexto de trabajo/ocupación.");
      return;
  }

  const ahora = Date.now();
  if (ahora - ultimoEjercicioSugeridoTime > TIEMPO_ENFRIAMIENTO) {
      mostrarBotonSugerencia(ejercicioId, mood);
      ultimoEjercicioSugeridoTime = ahora;
  } else {
      console.log("Sugerencia suprimida por enfriamiento (anti-spam).");
  }
}

function _manejarError(error) {
  ocultarTyping();
  console.error("❌ Error:", error);
  agregarMensaje("Estoy acá contigo. (Error de conexión)", "oso");
  if (window.setBearState) window.setBearState('calm');
}

// ============================================
// FUNCIONES PRIVADAS — UI
// ============================================

function _valorAMood(valor) {
  const map = {
    positive_high: 'happy',
    positive_low:  'calm',
    neutral:       'neutral',
    negative:      'sad',
  };
  return map[valor] || 'neutral';
}

function actualizarMoodIndicator(mood) {
  const indicator = document.getElementById('mood-indicator');
  if (!indicator) return;
  const label = MOOD_LABELS[mood] || '';
  indicator.textContent = label;
  indicator.style.opacity = label ? '1' : '0';
}

function mostrarTyping() {
  const bubble = document.createElement("div");
  bubble.className = "bubble oso typing";
  bubble.id = "typing-indicator";
  bubble.innerHTML = `<span></span><span></span><span></span>`;
  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
}

function ocultarTyping() {
  const indicator = document.getElementById("typing-indicator");
  if (indicator) indicator.remove();
}

function mostrarBotonSugerencia(id, mood = 'neutral') {
  let ejercicioEncontrado = null;
  let tipoEncontrado = "";

  for (const [tipo, lista] of Object.entries(CATALOGO_EJERCICIOS)) {
    const found = lista.find(e => e.id === id);
    if (found) {
      ejercicioEncontrado = found;
      tipoEncontrado = tipo;
      break;
    }
  }

  if (!ejercicioEncontrado) return;

  const frase = FRASES_POR_MOOD[mood] || FRASES_POR_MOOD.default;

  const bubble = document.createElement("div");
  bubble.className = `bubble oso mood-${mood}`;

  const div = document.createElement("div");
  div.innerHTML = `
    <p style="font-size: 0.9em; margin-bottom: 8px;">${frase}</p>
    <button class="exercise-suggestion-btn">
        ✨ ${ejercicioEncontrado.nombre}
    </button>
    <p style="font-size: 0.75em; opacity: 0.8; margin-top: 6px; font-style: italic;">
       "${ejercicioEncontrado.cientifico || 'Técnica recomendada'}"
    </p>
  `;

  const btn = div.querySelector('button');
  btn.style.cssText = `
    background: #a6c7b8; border: none; padding: 12px; width: 100%;
    border-radius: 12px; cursor: pointer; color: #2f4f45;
    font-weight: bold; transition: transform 0.2s;
  `;
  btn.onmouseover = () => btn.style.transform = "scale(1.02)";
  btn.onmouseout = () => btn.style.transform = "scale(1)";
  btn.onclick = () => iniciarEjercicio(tipoEncontrado, ejercicioEncontrado);

  bubble.appendChild(div);
  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
}

// ============================================
// EXPORTS
// ============================================

export function getHistorial() { return historialConversacion; }
export function resetHistorial() { historialConversacion = []; }
export function mostrarProximamente() {
  const tarjeta = document.createElement("div");
  tarjeta.style.cssText = `
    text-align: center;
    padding: 16px;
    margin: 12px auto;
    background: rgba(166, 199, 184, 0.15);
    border: 1px solid rgba(166, 199, 184, 0.4);
    border-radius: 16px;
    font-size: 0.85rem;
    color: #6b8e7d;
    max-width: 80%;
  `;
  tarjeta.innerHTML = `
    <span style="font-size: 1.2rem;">🎙️</span><br>
    <strong>Modo voz</strong><br>
    <span style="opacity: 0.8;">Muy pronto vas a poder hablar con Numa.</span>
  `;
  chat.appendChild(tarjeta);
  chat.scrollTop = chat.scrollHeight;
}