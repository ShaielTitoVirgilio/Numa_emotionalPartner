// modules/chat.js
import { CATALOGO_EJERCICIOS } from '../ejerciciosData.js';
import { iniciarEjercicio, authHeaders } from './utils.js';
import { TIEMPO_ENFRIAMIENTO } from './utils.js';
import { verificarCheckinDiario, consumirFlagCheckin } from './checkin.js';
import { getRespuestaNuma, VALOR_A_RATING } from './feedbackPost.js';
import { showAuthScreen } from './auth.js';
import { setFeedbackCallback as setFeedbackRespiracion } from './motorRespiracion.js';
import { setFeedbackCallback as setFeedbackGuiado } from './motorGuiado.js';
// ============================================
// ESTADO Y CONFIGURACIÓN
// ============================================

const chat = document.getElementById("chat");
const input = document.getElementById("input");

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;


let messageCount = 0;



// 🧠 Historial de conversación — limitado a últimos 20 mensajes
let historialConversacion = [];
const MAX_HISTORIAL = 20;

// 👤 Perfil cacheado — se carga una vez al inicio, se actualiza si hay memoria nueva
let perfilCacheado = null;

// 🎭 Mood de la última respuesta de Numa — el backend lo usa para el routing de módulos
let ultimoMood = null;

// ⏱️ Control de Enfriamiento
let ultimoEjercicioSugeridoTime = 0;

//Microfono

let recordingTimeout = null;
const MAX_RECORDING_MS = 25_000; // 25 segundos

let sttErrorCount = 0;
const MAX_STT_ERRORS = 3;
let micDisabled = false;


let audioContext = null;
let analyserNode = null;
let silenceStartTime = null;

const SILENCE_THRESHOLD = 0.015; // volumen RMS
const MAX_SILENCE_MS = 3000;     // 3 segundos
let silenceCheckInterval = null;


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
  stressed:    "Podes probar esto. Ayuda más de lo que parece:",
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
  if (!numaUser) return false;

  const user = JSON.parse(numaUser);

  try {
    const res = await fetch(`/profile/${user.user_id}`, { headers: authHeaders() });
    if (res.ok) {
      perfilCacheado = await res.json();
    }
  } catch (e) {
    console.warn('No se pudo cargar el perfil:', e);
  }

  // Rehidratar el chat: antes el historial vivía solo en memoria de la página
  // y al reabrir la PWA aparecía vacío ("Numa se olvidó de todo").
  return await _rehidratarHistorial();
}

async function _rehidratarHistorial() {
  try {
    const res = await fetch('/chat/history?limit=12', { headers: authHeaders() });
    if (!res.ok) return false;

    const data = await res.json();
    const mensajes = data.messages || [];
    if (!mensajes.length) return false;

    for (const m of mensajes) {
      if (m.role === 'user') {
        agregarMensaje(m.content, 'user');
        historialConversacion.push({ role: 'user', content: m.content });
      } else {
        agregarMensaje(m.content, 'oso', m.mood || null);
        historialConversacion.push({ role: 'assistant', content: m.content });
        if (m.mood) ultimoMood = m.mood;
      }
    }
    _trimHistorial();

    // Separador visual entre la charla anterior y la sesión nueva
    const sep = document.createElement('div');
    sep.className = 'chat-separador';
    sep.innerHTML = `<span>charla anterior</span>`;
    chat.appendChild(sep);
    chat.scrollTop = chat.scrollHeight;

    return true;
  } catch (e) {
    return false; // el historial no es crítico
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

if (tipo === 'user' || tipo === 'oso') {
  messageCount++;
}

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

export async function recibirFeedbackEjercicio(textoOpcion, valor, ejercicio) {
  agregarMensaje(textoOpcion, "user");

  const numaUser = localStorage.getItem('numa_user');
  const userId = numaUser ? JSON.parse(numaUser).user_id : null;

  // 1) Persistir el rating 1-5 del ejercicio (fire-and-forget, no bloquea la respuesta)
  if (userId && ejercicio?.id && VALOR_A_RATING[valor]) {
    fetch("/exercise-rating", {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        user_id: userId,
        exercise_id: ejercicio.id,
        rating: VALOR_A_RATING[valor],
        valor_texto: valor,
      }),
    }).catch(e => console.warn("No se pudo guardar el rating:", e));
  }

  // 2) Respuesta real de Numa vía LLM — el prefijo [Post-ejercicio | ...] activa
  //    el módulo de feedback contextual en el backend
  const mensajePost = `[Post-ejercicio | ${ejercicio?.nombre || "ejercicio"}] ${textoOpcion}`;
  _prepararEnvio();
  try {
    const data = await _llamarBackend(mensajePost);
    _procesarRespuesta(data, mensajePost);
  } catch (error) {
    // Fallback offline: frase local si falla la red
    console.warn("Feedback vía LLM falló, uso respuesta local:", error);
    ocultarTyping();
    const moodParaFeedback = _valorAMood(valor);
    const respuestaFallback = getRespuestaNuma(valor);
    agregarMensaje(respuestaFallback, "oso", moodParaFeedback);
    if (window.setBearState) {
      window.setBearState(MOOD_TO_BEAR_STATE[moodParaFeedback] || 'calm');
    }
    historialConversacion.push({ role: "user", content: mensajePost });
    historialConversacion.push({ role: "assistant", content: respuestaFallback });
    _trimHistorial();
    chat.scrollTop = chat.scrollHeight;
  }
}

// Cablear el callback de feedback de los motores hacia el chat
// (antes setFeedbackCallback no se llamaba nunca y el feedback se perdía)
setFeedbackRespiracion(recibirFeedbackEjercicio);
setFeedbackGuiado(recibirFeedbackEjercicio);

// ============================================
// FUNCIONES PRIVADAS — ENVÍO
// ============================================

function _prepararEnvio() {
  if (window.setBearState) window.setBearState('listening');
  mostrarTyping();
}





// Timeout del chat: una request colgada dejaba el typing infinito
const CHAT_TIMEOUT_MS = 25000;

async function _llamarBackend(texto) {
  // Limitar historial antes de enviar
  const historialLimitado = historialConversacion.slice(-MAX_HISTORIAL);

  const conversationToSend = [
    ...historialLimitado,
    { role: "user", content: texto }
  ];

  const numaUser = localStorage.getItem('numa_user');
  const userId = numaUser ? JSON.parse(numaUser).user_id : null;

  const checkinRecienHecho = consumirFlagCheckin();

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);

  let res;
  try {
    res = await fetch("/chat", {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      signal: controller.signal,
      body: JSON.stringify({
        conversation: conversationToSend,
        user_id: userId,
        perfil: perfilCacheado,
        ultimo_mood: ultimoMood,
        checkin_recien_hecho: checkinRecienHecho,
      })
    });
  } finally {
    clearTimeout(timeoutId);
  }

  if (res.status === 401) {
    localStorage.removeItem('numa_user');
    showAuthScreen();
    throw new Error("Sesión expirada");
}

if (!res.ok) {
    throw new Error("Error en respuesta HTTP");
}

  return await res.json();
}



function _procesarRespuesta(data, textoUsuario) {

  const mood = data.mood || 'neutral';
  ultimoMood = mood;
  const textoLimpio = _limpiarMensaje(data.message);

  ocultarTyping();

  // Respuesta de crisis: tarjeta especial con teléfonos/links clicables.
  // En una emergencia, copiar un número a mano es fricción innecesaria.
  if (data.risk_level === 'high') {
    _agregarMensajeCrisis(textoLimpio);
    if (window.setBearState) window.setBearState('sad');
    actualizarMoodIndicator(mood);
    _actualizarHistorial(textoUsuario, textoLimpio);
    return;
  }

  agregarMensaje(textoLimpio, "oso", mood);

  if (window.setBearState) window.setBearState(MOOD_TO_BEAR_STATE[mood] || 'calm');
  actualizarMoodIndicator(mood);

  _actualizarHistorial(textoUsuario, textoLimpio);
  _manejarSugerencia(data, mood);

  // Si el backend detectó memorias nuevas, agregarlas al perfil cacheado
  // para que los próximos mensajes ya las tengan en cuenta
  if (data.nuevas_memorias?.length && perfilCacheado) {
    if (!perfilCacheado._memorias_sesion) {
      perfilCacheado._memorias_sesion = [];
    }
    for (const m of data.nuevas_memorias) {
      perfilCacheado._memorias_sesion.push(m);
    }
  }
  verificarCheckinDiario();
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
  const regexEjercicio = /\[EJERCICIO:\s*(\w+)\]/;
  const ejercicioId = (data.suggested_action && data.suggested_action !== 'none')
      ? data.suggested_action
      : data.message.match(regexEjercicio)?.[1] ?? null;
  if (!ejercicioId) return;

  // Si el ejercicio requiere espacio físico y el usuario parece estar ocupado/en trabajo
  const ejerciciosFisicos = ['yoga_cuello', 'yoga_ansiedad', 'meditacion_bodyscan', 'meditacion_mindfulness'];
  const ultimoMensajeUsuario = historialConversacion.filter(m => m.role === 'user').slice(-1)[0]?.content?.toLowerCase() || '';
  const contextoCupado = /trabajo|ocupado|cansad|sin tiempo|jefe|reunión|oficina/i.test(ultimoMensajeUsuario);

  if (contextoCupado && ejerciciosFisicos.includes(ejercicioId)) return;

  const ahora = Date.now();
  if (ahora - ultimoEjercicioSugeridoTime > TIEMPO_ENFRIAMIENTO) {
      mostrarBotonSugerencia(ejercicioId, mood);
      ultimoEjercicioSugeridoTime = ahora;
  }
}

function _manejarError(error) {
  ocultarTyping();
  console.error("❌ Error:", error);
  if (error?.name === 'AbortError') {
    agregarMensaje("Me quedé pensando demasiado 🐼 ¿Me lo mandás de nuevo?", "oso");
  } else {
    agregarMensaje("Estoy acá contigo. (Error de conexión)", "oso");
  }
  if (window.setBearState) window.setBearState('calm');
}

// ============================================
// TARJETA DE CRISIS — recursos clicables
// ============================================

function _escaparHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function _linkificarCrisis(texto) {
  return _escaparHtml(texto).split('\n').map(linea => {
    // URLs tipo www.x.org → link
    let out = linea.replace(
      /(www\.[^\s]+)/g,
      '<a href="https://$1" target="_blank" rel="noopener" class="crisis-link">$1</a>'
    );
    // Teléfonos en líneas de recursos (📞) → enlaces tel:
    if (linea.includes('📞')) {
      out = out.replace(
        /(\d[\d\s]{1,13}\d|\b\d{3}\b)/,
        (m) => `<a href="tel:${m.replace(/\s+/g, '')}" class="crisis-tel">${m}</a>`
      );
    }
    return out;
  }).join('<br>');
}

function _agregarMensajeCrisis(texto) {
  const bubble = document.createElement("div");
  bubble.className = "bubble oso crisis-card";
  bubble.innerHTML = _linkificarCrisis(texto);
  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
  messageCount++;
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
  const duracion = _duracionEjercicio(tipoEncontrado, ejercicioEncontrado);

  const bubble = document.createElement("div");
  bubble.className = `bubble oso mood-${mood}`;

  const div = document.createElement("div");
  div.innerHTML = `
    <p class="sugerencia-frase">${frase}</p>
    <button class="exercise-suggestion-btn">
        ✨ ${ejercicioEncontrado.nombre}${duracion ? ` · ${duracion}` : ''}
    </button>
    <p class="sugerencia-cientifico">
       "${ejercicioEncontrado.cientifico || 'Técnica recomendada'}"
    </p>
    <button class="sugerencia-ahora-no">Ahora no</button>
  `;

  const btn = div.querySelector('.exercise-suggestion-btn');
  btn.onclick = () => iniciarEjercicio(tipoEncontrado, ejercicioEncontrado);

  // "Ahora no": descarta la sugerencia sin perder el hilo de la charla
  div.querySelector('.sugerencia-ahora-no').onclick = () => bubble.remove();

  bubble.appendChild(div);
  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
}

function _duracionEjercicio(tipo, data) {
  if (tipo === 'respiracion') return '1 min';
  if (tipo === 'meditacion' || tipo === 'yoga') {
    const segundos = (data.pasos?.length || 0) * (data.tiempoPorPaso || 20);
    if (!segundos) return '';
    const min = Math.max(1, Math.round(segundos / 60));
    return `${min} min`;
  }
  return ''; // lectura: a su ritmo
}



// ============================================
// EXPORTS
// ============================================

export function getHistorial() { return historialConversacion; }
export function resetHistorial() { historialConversacion = []; }

export async function toggleMic() {
  const micBtn = document.getElementById("mic-btn");

  if (micDisabled) {
    // Reset del STT: antes el micrófono quedaba muerto el resto de la sesión
    // tras 3 errores; ahora un toque lo rehabilita para reintentar.
    micDisabled = false;
    sttErrorCount = 0;
    micBtn.classList.remove("disabled");
    mostrarAvisoMic("🎙️ Listo, probemos de nuevo. Tocá el micrófono para grabar.");
    setTimeout(ocultarAvisoMic, 4000);
    return;
  }

  if (!isRecording) {
    // ▶️ EMPIEZA A GRABAR
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    startSilenceDetection(stream);

    mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    audioChunks = [];

    mediaRecorder.ondataavailable = e => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      cleanupSilenceDetection();
      clearTimeout(recordingTimeout);
      const blob = new Blob(audioChunks, { type: "audio/webm" });
      await procesarAudio(blob);
    };

    mediaRecorder.start();
    isRecording = true;

    activarMicUI();

    // ⏱️ Corte automático por tiempo
    recordingTimeout = setTimeout(() => {
      if (isRecording) {
        detenerGrabacionPorLimite();
      }
    }, MAX_RECORDING_MS);

  } else {
    // ⏹️ DETIENE GRABACIÓN
    mediaRecorder.stop();
    isRecording = false;
    desactivarMicUI();
    cleanupSilenceDetection();
  }
}

function startSilenceDetection(stream) {
  audioContext = new AudioContext();
  const source = audioContext.createMediaStreamSource(stream);

  analyserNode = audioContext.createAnalyser();
  analyserNode.fftSize = 2048;

  source.connect(analyserNode);

  const dataArray = new Float32Array(analyserNode.fftSize);

  silenceStartTime = null;

  silenceCheckInterval = setInterval(() => {
    analyserNode.getFloatTimeDomainData(dataArray);

    // Calcular RMS (volumen real)
    let sumSquares = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sumSquares += dataArray[i] * dataArray[i];
    }
    const rms = Math.sqrt(sumSquares / dataArray.length);

    if (rms < SILENCE_THRESHOLD) {
      // Empezó o sigue el silencio
      if (!silenceStartTime) {
        silenceStartTime = Date.now();
      } else if (Date.now() - silenceStartTime >= MAX_SILENCE_MS) {
        console.log("🔇 Silencio detectado, cortando grabación");
        detenerGrabacionPorSilencio();
      }
    } else {
      // Hay voz → reset
      silenceStartTime = null;
    }

  }, 200); // chequea 5 veces por segundo
}

function detenerGrabacionPorSilencio() {
  if (!isRecording) return;

  try {
    mediaRecorder.stop();
  } catch { /* noop */ }

  isRecording = false;
  mostrarAvisoMic("🔇 No detecté voz, corto la grabación");
  cleanupSilenceDetection();
  desactivarMicUI();
}

function detenerGrabacionPorLimite() {
  try {
    mediaRecorder.stop();
  } catch { /* noop */ }

  isRecording = false;
  mostrarAvisoMic("⏱️ Límite de tiempo alcanzado");
  desactivarMicUI();
}

function cleanupSilenceDetection() {
  clearInterval(silenceCheckInterval);
  silenceCheckInterval = null;
  silenceStartTime = null;

  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
}

async function procesarAudio(blob) {
  const formData = new FormData();
  formData.append("file", blob, "voz.webm");

  try {
    const res = await fetch("/speech-to-text", {
      method: "POST",
      headers: authHeaders(),
      body: formData,
    });

    // ✅ ESTE BLOQUE VA ACÁ
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(txt);
    }

    const data = await res.json();
    const texto = data.text?.trim();

    // 🐼 vuelve a estado normal
    window.setBearState?.("calm");

    if (texto) {
      input.value = texto;
      enviarMensaje();
    }
  } catch (e) {
    console.error("Error STT:", e);
    sttErrorCount++;

    if (sttErrorCount >= MAX_STT_ERRORS) {
      micDisabled = true;
      deshabilitarMic();
    }

    window.setBearState?.("calm");
  }
}

function mostrarAvisoMic(texto) {
  const toast = document.getElementById("mic-toast");
  if (!toast) return;
  toast.textContent = texto;
  toast.classList.remove("hidden");
}

function ocultarAvisoMic() {
  document.getElementById("mic-toast")?.classList.add("hidden");
}

function activarMicUI() {
  const micBtn = document.getElementById("mic-btn");
  micBtn.classList.add("recording");
  mostrarAvisoMic("🎧 Numa te está escuchando…");
}

function desactivarMicUI() {
  const micBtn = document.getElementById("mic-btn");
  micBtn.classList.remove("recording");
  ocultarAvisoMic();
}

function deshabilitarMic() {
  const micBtn = document.getElementById("mic-btn");
  // No usar .disabled real: el botón tiene que seguir recibiendo el toque
  // que rehabilita el micrófono (ver toggleMic).
  micBtn.classList.add("disabled");

  mostrarAvisoMic(
    "🎙️ El micrófono falló varias veces. Tocá de nuevo para reintentar, o escribile a Numa."
  );
}