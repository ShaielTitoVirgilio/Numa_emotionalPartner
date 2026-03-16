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
// AUDIO — archivos reales
// ============================================

// Creamos los Audio al momento de usar para evitar problemas en mobile
let _audioActivo = null;
let _audioTimeout = null;
let _tonoCtx = null;
let _tonoOsc = null;

function reproducirSonidoFase(fase, duracionSegundos) {
  // 1. Detener lo que estaba sonando
  _pararAudioActivo();

  if (fase === 'retener' || fase === 'esperar') {
    tonoSostener(duracionSegundos);
    return;
  }

  // 2. Crear instancia nueva cada vez (más confiable en mobile/iOS)
  const src = fase === 'inhalar'
    ? '/static/assets/inhale.mp3'
    : '/static/assets/exhale.mp3';

  const audio = new Audio(src);
  audio.loop = true;
  _audioActivo = audio;

  // En iOS necesitamos intentar el play después de un tick
  setTimeout(() => {
    audio.play().catch(() => {});
  }, 0);

  // Cortar al terminar la fase
  _audioTimeout = setTimeout(() => {
    audio.loop = false;
    audio.pause();
    audio.src = "";
    if (_audioActivo === audio) _audioActivo = null;
  }, duracionSegundos * 1000);
}

function _pararAudioActivo() {
  clearTimeout(_audioTimeout);
  _audioTimeout = null;

  if (_audioActivo) {
    _audioActivo.loop = false;
    _audioActivo.pause();
    _audioActivo.src = "";
    _audioActivo = null;
  }

  if (_tonoOsc) {
    try { _tonoOsc.stop(); } catch (_) {}
    _tonoOsc = null;
  }
}

function tonoSostener(duracionSegundos) {
  if (!_tonoCtx) {
    _tonoCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (_tonoCtx.state === 'suspended') _tonoCtx.resume();

  if (_tonoOsc) {
    try { _tonoOsc.stop(); } catch (_) {}
    _tonoOsc = null;
  }

  const ctx = _tonoCtx;
  const osc = ctx.createOscillator();
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
  _tonoOsc = osc;
}

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

export function setFeedbackCallback(fn) {
  _onFeedbackRespuesta = fn;
}

export function runRespiracion(data) {
  const overlay    = document.getElementById("overlay-respiracion");
  const titulo     = document.getElementById("resp-titulo");
  const instruccion = document.getElementById("resp-text-instruccion");
  const circulo    = document.getElementById("resp-circle");
  const subtext    = document.getElementById("resp-subtext");

  if (!overlay) return;

  overlay.classList.remove("hidden");
  titulo.innerText   = data.nombre;
  subtext.innerText  = data.instruccion || "";

  const { inhalar, retener, exhalar, esperar } = data.patron;

  const tInhalar = inhalar * 1000;
  const tRetener = retener * 1000;
  const tExhalar = exhalar * 1000;
  const tEsperar = esperar * 1000;
  const cicloTotal = tInhalar + tRetener + tExhalar + tEsperar;

  function ciclo() {
    if (overlay.classList.contains("hidden")) return;

    // 1. INHALAR
    instruccion.innerText = "Inhalá";
    circulo.style.transition = `transform ${inhalar}s ease-in-out, background-color ${inhalar}s`;
    circulo.style.transform = "scale(1.5)";
    circulo.style.backgroundColor = "rgba(143, 181, 163, 0.8)";
    reproducirSonidoFase('inhalar', inhalar);

    // 2. RETENER
    if (retener > 0) {
      setTimeout(() => {
        if (overlay.classList.contains("hidden")) return;
        instruccion.innerText = "Sostené";
        reproducirSonidoFase('retener', retener);
      }, tInhalar);
    }

    // 3. EXHALAR
    setTimeout(() => {
      if (overlay.classList.contains("hidden")) return;
      instruccion.innerText = "Exhalá";
      circulo.style.transition = `transform ${exhalar}s ease-in-out, background-color ${exhalar}s`;
      circulo.style.transform = "scale(1)";
      circulo.style.backgroundColor = "rgba(183, 211, 198, 0.6)";
      reproducirSonidoFase('exhalar', exhalar);
    }, tInhalar + tRetener);

    // 4. ESPERAR
    if (esperar > 0) {
      setTimeout(() => {
        if (overlay.classList.contains("hidden")) return;
        instruccion.innerText = "Pausa";
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

  if (titulo)      titulo.innerText     = "¡Excelente!";
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