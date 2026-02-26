// modules/chat.js
import { CATALOGO_EJERCICIOS } from '../ejerciciosData.js';
import { iniciarEjercicio } from './utils.js';

// ============================================
// ESTADO Y CONFIGURACIÓN
// ============================================

const chat = document.getElementById("chat");
const input = document.getElementById("input");

// 🧠 Historial de conversación
let historialConversacion = [];

// ⏱️ Control de "Enfriamiento" (Throttling)
let ultimoEjercicioSugeridoTime = 0;
const TIEMPO_ENFRIAMIENTO = 10000; // 10 segundos (para desarrollo)
// const TIEMPO_ENFRIAMIENTO = 300000; // 5 minutos 


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

// 💬 Frases de introducción para la sugerencia de ejercicio
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
// FUNCIONES PÚBLICAS
// ============================================

/**
 * Agrega un mensaje al chat visualmente
 */
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

/**
 * Envía mensaje al backend y procesa la respuesta inteligente
 */
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

function _prepararEnvio() {
  if (window.setBearState) window.setBearState('listening');
  mostrarTyping();
}

async function _llamarBackend(texto) {
  const conversationToSend = [
      ...historialConversacion,
      { role: "user", content: texto }
  ];

  const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation: conversationToSend })
  });

  if (!res.ok) {
      const errorText = await res.text();
      console.error("❌ ERROR DEL SERVIDOR:", errorText);
      throw new Error("Error en respuesta HTTP");
  }

  return await res.json();
}

function _procesarRespuesta(data, textoUsuario) {
  const mood = data.mood || 'neutral';
  const textoLimpio = _limpiarMensaje(data.message);

  ocultarTyping();
  agregarMensaje(textoLimpio, "oso", mood);

  if (window.setBearState) window.setBearState(MOOD_TO_BEAR_STATE[mood] || 'calm');
  actualizarMoodIndicator(mood);

  _actualizarHistorial(textoUsuario, textoLimpio);
  _manejarSugerencia(data, mood);
}

function _limpiarMensaje(mensaje) {
  return mensaje.replace(/\[EJERCICIO:\s*(\w+)\]/, "").trim();
}

function _actualizarHistorial(textoUsuario, textoOso) {
  historialConversacion.push({ role: "user", content: textoUsuario });
  historialConversacion.push({ role: "assistant", content: textoOso });
}

function _manejarSugerencia(data, mood) {
  const regexEjercicio = /\[EJERCICIO:\s*(\w+)\]/;
  const ejercicioId = (data.suggested_action && data.suggested_action !== 'none')
      ? data.suggested_action
      : data.message.match(regexEjercicio)?.[1] ?? null;

  if (!ejercicioId) return;

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
// FUNCIONES PRIVADAS
// ============================================

/**
 * Actualiza el indicador de mood debajo del oso
 */
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

/**
 * Muestra un botón de sugerencia de ejercicio en el chat
 */
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
    bubble.className = "bubble oso";
    bubble.classList.add(`mood-${mood}`); 
    
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
        background: #a6c7b8; 
        border: none; 
        padding: 12px; 
        width: 100%; 
        border-radius: 12px; 
        cursor: pointer; 
        color: #2f4f45; 
        font-weight: bold;
        transition: transform 0.2s;
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

export function getHistorial() {
    return historialConversacion;
}

export function resetHistorial() {
    historialConversacion = [];
}