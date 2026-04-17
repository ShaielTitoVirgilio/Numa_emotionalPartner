// modules/motorRespiracion.js

import { mostrarFeedback, getRespuestaNuma } from './feedbackPost.js';
import { detenerSonidoAmbiente } from './ambientSound.js';

// ============================================
// ESTADO INTERNO
// ============================================

let intervalRespiracion = null;
let _onFeedbackRespuesta = null;
let finalizarTimeout = null;

// ============================================
// AUDIO
// FIX: usamos AudioContext para TODOS los sonidos de fase.
// new Audio() dentro de setTimeout es bloqueado por iOS/Android
// porque ya no está en el mismo tick del evento del usuario.
// AudioContext creado en el primer click del usuario queda
// "desbloqueado" y puede reproducir audio en cualquier momento.
// ============================================

let _tonoCtx = null;
let _fuenteActiva = null;   // AudioBufferSourceNode o OscillatorNode activo
let _gainActivo   = null;
let _audioTimeout = null;

// Cache de buffers decodificados para no releer el archivo en cada fase
const _bufferCache = {};

/** Desbloquear AudioContext en el primer gesto del usuario */
function _getCtx() {
  if (!_tonoCtx) {
    _tonoCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (_tonoCtx.state === 'suspended') _tonoCtx.resume();
  return _tonoCtx;
}

/** Carga y cachea un archivo de audio como AudioBuffer */
async function _cargarBuffer(src) {
  if (_bufferCache[src]) return _bufferCache[src];
  try {
    const res  = await fetch(src);
    const arr  = await res.arrayBuffer();
    const ctx  = _getCtx();
    const buf  = await ctx.decodeAudioData(arr);
    _bufferCache[src] = buf;
    return buf;
  } catch (e) {
    console.warn('No se pudo cargar audio:', src, e);
    return null;
  }
}

/** Precarga inhale y exhale al arrancar para que estén listos */
async function _precargarAudios() {
  await _cargarBuffer('/static/assets/inhale.mp3');
  await _cargarBuffer('/static/assets/exhale.mp3');
}

function _pararAudioActivo() {
  clearTimeout(_audioTimeout);
  _audioTimeout = null;

  if (_fuenteActiva) {
    try { _fuenteActiva.stop(); } catch (_) {}
    _fuenteActiva = null;
  }
  _gainActivo = null;
}

async function reproducirSonidoFase(fase, duracionSegundos) {
  _pararAudioActivo();

  const ctx = _getCtx();

  if (fase === 'retener' || fase === 'esperar') {
    _tonoSostener(ctx, duracionSegundos);
    return;
  }

  const src = fase === 'inhalar'
    ? '/static/assets/inhale.mp3'
    : '/static/assets/exhale.mp3';

  const buffer = await _cargarBuffer(src);
  if (!buffer) return;

  // Volver a chequear que no se haya cancelado mientras cargaba
  if (fase === 'inhalar' && !intervalRespiracion && !finalizarTimeout) return;

  const source = ctx.createBufferSource();
  const gain   = ctx.createGain();

  source.buffer = buffer;
  source.loop   = true;
  source.connect(gain);
  gain.connect(ctx.destination);
  gain.gain.value = 0.8;

  source.start(0);
  _fuenteActiva = source;
  _gainActivo   = gain;

  // Parar al terminar la fase
  _audioTimeout = setTimeout(() => {
    if (_fuenteActiva === source) {
      try { source.stop(); } catch (_) {}
      _fuenteActiva = null;
    }
  }, duracionSegundos * 1000);
}

function _tonoSostener(ctx, duracionSegundos) {
  const osc  = ctx.createOscillator();
  const gain = ctx.createGain();

  osc.connect(gain);
  gain.connect(ctx.destination);

  osc.type = 'sine';
  osc.frequency.value = 432;

  const now = ctx.currentTime;
  gain.gain.setValueAtTime(0, now);
  gain.gain.linearRampToValueAtTime(0.01, now + 0.8);
  gain.gain.setValueAtTime(0.01, now + Math.max(duracionSegundos - 1, 0.1));
  gain.gain.linearRampToValueAtTime(0, now + duracionSegundos);

  osc.start(now);
  osc.stop(now + duracionSegundos);
  _fuenteActiva = osc;
  _gainActivo   = gain;
}

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

export function setFeedbackCallback(fn) {
  _onFeedbackRespuesta = fn;
}

function formatPatron({ inhalar, retener, exhalar, esperar }) {
  const partes = [];
  if (inhalar) partes.push(`↑ ${inhalar}s`);
  if (retener) partes.push(`· ${retener}s`);
  if (exhalar) partes.push(`↓ ${exhalar}s`);
  if (esperar) partes.push(`· ${esperar}s`);
  return partes.join('  ');
}

export function runRespiracion(data) {
  const overlay      = document.getElementById("overlay-respiracion");
  const titulo       = document.getElementById("resp-titulo");
  const patronInfo   = document.getElementById("resp-text-instruccion");
  const faseDisplay  = document.getElementById("resp-instruccion");
  const circulo      = document.getElementById("resp-circle");
  const subtext      = document.getElementById("resp-subtext");

  if (!overlay) return;

  overlay.classList.remove("hidden");
  titulo.innerText      = data.nombre;
  patronInfo.innerText  = formatPatron(data.patron);
  subtext.innerText     = data.instruccion || "";
  if (faseDisplay) faseDisplay.innerText = "";

  const { inhalar, retener, exhalar, esperar } = data.patron;

  const tInhalar  = inhalar * 1000;
  const tRetener  = retener * 1000;
  const tExhalar  = exhalar * 1000;
  const tEsperar  = esperar * 1000;
  const cicloTotal = tInhalar + tRetener + tExhalar + tEsperar;

  // Precargar audios en el mismo tick del gesto del usuario
  // (esto desbloquea el AudioContext en iOS)
  _getCtx();
  _precargarAudios();

  function setFase(texto) {
    if (faseDisplay) faseDisplay.innerText = texto;
  }

  function ciclo() {
    if (overlay.classList.contains("hidden")) return;

    // 1. INHALAR
    setFase("Inhalá");
    circulo.style.transition = `transform ${inhalar}s ease-in-out, background-color ${inhalar}s`;
    circulo.style.transform = "scale(1.5)";
    circulo.style.backgroundColor = "rgba(143, 181, 163, 0.8)";
    reproducirSonidoFase('inhalar', inhalar);

    // 2. RETENER
    if (retener > 0) {
      setTimeout(() => {
        if (overlay.classList.contains("hidden")) return;
        setFase("Sostené");
        reproducirSonidoFase('retener', retener);
      }, tInhalar);
    }

    // 3. EXHALAR
    setTimeout(() => {
      if (overlay.classList.contains("hidden")) return;
      setFase("Exhalá");
      circulo.style.transition = `transform ${exhalar}s ease-in-out, background-color ${exhalar}s`;
      circulo.style.transform = "scale(1)";
      circulo.style.backgroundColor = "rgba(183, 211, 198, 0.6)";
      reproducirSonidoFase('exhalar', exhalar);
    }, tInhalar + tRetener);

    // 4. ESPERAR
    if (esperar > 0) {
      setTimeout(() => {
        if (overlay.classList.contains("hidden")) return;
        setFase("Pausa");
        reproducirSonidoFase('esperar', esperar);
      }, tInhalar + tRetener + tExhalar);
    }
  }

  ciclo();
  intervalRespiracion = setInterval(ciclo, cicloTotal);

  finalizarTimeout = setTimeout(() => {
    finalizarRespiracion(data.nombre);
  }, 60000);
}

export function detenerRespiracion() {
  document.getElementById("overlay-respiracion").classList.add("hidden");
  clearInterval(intervalRespiracion);
  intervalRespiracion = null;
  clearTimeout(finalizarTimeout);
  finalizarTimeout = null;
  _pararAudioActivo();
  detenerSonidoAmbiente();
}

// ============================================
// PRIVADO
// ============================================

function finalizarRespiracion(nombreEjercicio) {
  clearInterval(intervalRespiracion);
  intervalRespiracion = null;
  clearTimeout(finalizarTimeout);
  finalizarTimeout = null;
  _pararAudioActivo();

  const titulo      = document.getElementById("resp-titulo");
  const instruccion = document.getElementById("resp-text-instruccion");
  const circulo     = document.getElementById("resp-circle");

  if (titulo)      titulo.innerText      = "¡Excelente!";
  if (instruccion) instruccion.innerText = "Terminaste. Bien hecho.";
  if (circulo)     circulo.style.display = "none";

  setTimeout(() => {
    detenerRespiracion();
    if (circulo) circulo.style.display = "block";

    mostrarFeedback(nombreEjercicio || "la respiración", (valor, textoOpcion) => {
      if (_onFeedbackRespuesta) {
        const respuestaNuma = getRespuestaNuma(valor);
        _onFeedbackRespuesta(textoOpcion, respuestaNuma, valor);
      }
    });
  }, 2500);
}