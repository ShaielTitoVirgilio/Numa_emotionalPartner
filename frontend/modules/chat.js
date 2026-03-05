// modules/chat.js
import { CATALOGO_EJERCICIOS } from '../ejerciciosData.js';
import { iniciarEjercicio } from './utils.js';
import { TIEMPO_ENFRIAMIENTO } from './utils.js';

// ============================================
// ESTADO Y CONFIGURACIÓN
// ============================================

const chat = document.getElementById("chat");
const input = document.getElementById("input");

let historialConversacion = [];
const MAX_HISTORIAL = 20;

let perfilCacheado = null;
let ultimoEjercicioSugeridoTime = 0;

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

const FRASES_POR_MOOD = {
  stressed:    "Che, probá esto. Ayuda más de lo que parece:",
  overwhelmed: "Para un segundo. Esto puede acomodarte:",
  sad:         "No tenés que hacer nada grande. Esto es suave:",
  anxious:     "Para bajar un cambio:",
  default:     "Esto podría ayudarte ahora:",
};

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
// INICIALIZACIÓN
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
// ENVIAR MENSAJE — ahora usa streaming
// ============================================

export async function enviarMensaje() {
  const texto = input.value.trim();
  if (!texto) return;

  agregarMensaje(texto, "user");
  input.value = "";

  // Activar estado "escuchando" del oso + mostrar typing
  if (window.setBearState) window.setBearState('listening');
  mostrarTyping();

  try {
    const numaUser = localStorage.getItem('numa_user');
    const userId = numaUser ? JSON.parse(numaUser).user_id : null;
    const historialLimitado = historialConversacion.slice(-MAX_HISTORIAL);

    const res = await fetch("/chat", {           // ← mismo endpoint de siempre
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation: [...historialLimitado, { role: "user", content: texto }],
        user_id: userId,
        perfil: perfilCacheado,
      })
    });

    if (!res.ok) throw new Error("Error HTTP");

    await _procesarStream(res, texto);

  } catch (error) {
    ocultarTyping();
    console.error("❌ Error:", error);
    agregarMensaje("Estoy acá contigo. (Error de conexión)", "oso");
    if (window.setBearState) window.setBearState('calm');
  }
}

// ============================================
// PROCESAR STREAM — lee el SSE y va mostrando
// ============================================

async function _procesarStream(res, textoUsuario) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();

  // Crear bubble vacía que iremos llenando en tiempo real
  ocultarTyping();
  const bubble = document.createElement("div");
  bubble.className = "bubble oso mood-neutral";
  chat.appendChild(bubble);

  let sseBuffer = "";
  let displayText = "";
  let lastEventWasMeta = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    sseBuffer += decoder.decode(value, { stream: true });

    // Procesar líneas completas del SSE
    const lines = sseBuffer.split("\n");
    sseBuffer = lines.pop(); // la última línea puede estar incompleta, la guardamos

    for (const line of lines) {

      // Detectar que el próximo "data:" es el evento de metadatos
      if (line.trim() === "event: meta") {
        lastEventWasMeta = true;
        continue;
      }

      if (!line.startsWith("data: ")) continue;

      const payload = line.slice(6); // quitar "data: "
      if (!payload.trim()) continue;

      // ── Evento meta: mood, ejercicio, memoria ──
      if (lastEventWasMeta) {
        lastEventWasMeta = false;
        try {
          const meta = JSON.parse(payload);
          const mood = meta.mood || "neutral";

          // Aplicar color de mood a la bubble
          bubble.className = `bubble oso mood-${mood}`;

          // Texto final limpio del backend (por si el stream quedó cortado)
          if (meta.full_message) {
            bubble.innerText = meta.full_message;
            displayText = meta.full_message;
          }

          // Actualizar oso y mood indicator
          if (window.setBearState) window.setBearState(MOOD_TO_BEAR_STATE[mood] || 'calm');
          actualizarMoodIndicator(mood);

          // Guardar en historial
          _actualizarHistorial(textoUsuario, displayText);

          // Mostrar botón de ejercicio si aplica
          _manejarSugerencia(meta, mood);

          // Actualizar memorias de sesión
          if (meta.nueva_memoria && perfilCacheado) {
            if (!perfilCacheado._memorias_sesion) perfilCacheado._memorias_sesion = [];
            perfilCacheado._memorias_sesion.push(meta.nueva_memoria);
          }

        } catch (e) {
          console.warn("Error parseando meta:", e);
        }
        continue;
      }

      // ── Texto parcial: ir mostrando mientras el modelo genera ──
      lastEventWasMeta = false;
      displayText = payload;
      bubble.innerText = displayText;
      chat.scrollTop = chat.scrollHeight;
    }
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
// FUNCIONES PRIVADAS — HISTORIAL Y SUGERENCIAS
// ============================================

function _actualizarHistorial(textoUsuario, textoOso) {
  historialConversacion.push({ role: "user", content: textoUsuario });
  historialConversacion.push({ role: "assistant", content: textoOso });
  _trimHistorial();
}

function _trimHistorial() {
  if (historialConversacion.length > MAX_HISTORIAL) {
    historialConversacion = historialConversacion.slice(-MAX_HISTORIAL);
  }
}

function _manejarSugerencia(data, mood) {
  // Con el nuevo formato, suggested_action viene directo en el meta
  const ejercicioId = (data.suggested_action && data.suggested_action !== 'none')
    ? data.suggested_action
    : null;

  if (!ejercicioId) return;

  // Suprimir ejercicios físicos si el usuario está ocupado/en trabajo
  const ejerciciosFisicos = ['yoga_cuello', 'yoga_ansiedad', 'meditacion_bodyscan', 'meditacion_mindfulness'];
  const ultimoMensajeUsuario = historialConversacion
    .filter(m => m.role === 'user')
    .slice(-1)[0]?.content?.toLowerCase() || '';
  const contextoCupado = /trabajo|ocupado|cansad|sin tiempo|jefe|reunión|oficina/i.test(ultimoMensajeUsuario);

  if (contextoCupado && ejerciciosFisicos.includes(ejercicioId)) return;

  // Anti-spam: respetar tiempo de enfriamiento
  const ahora = Date.now();
  if (ahora - ultimoEjercicioSugeridoTime > TIEMPO_ENFRIAMIENTO) {
    mostrarBotonSugerencia(ejercicioId, mood);
    ultimoEjercicioSugeridoTime = ahora;
  }
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
  btn.onmouseout  = () => btn.style.transform = "scale(1)";
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