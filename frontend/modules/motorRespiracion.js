// modules/motorRespiracion.js

import { mostrarFeedback, getRespuestaNuma } from './feedbackPost.js';
import { detenerSonidoAmbiente } from './ambientSound.js';  // ← NUEVO

// ============================================
// ESTADO INTERNO
// ============================================

let intervalRespiracion = null;
let _onFeedbackRespuesta = null;
let audioTimeout = null;
let finalizarTimeout = null;

// ============================================
// AUDIO — archivos reales
// ============================================

const audioInhalar = new Audio('/static/assets/inhale.mp3');
const audioExhalar = new Audio('/static/assets/exhale.mp3');

audioInhalar.preload = 'auto';
audioExhalar.preload = 'auto';

function reproducirSonidoFase(fase, duracionSegundos) {
  _detenerAudios();

  if (fase === 'retener' || fase === 'esperar') {
    tonoSostener(duracionSegundos);
    return;
  }

  const audio = fase === 'inhalar' ? audioInhalar : audioExhalar;

  audio.loop = true;
  audio.currentTime = 0;
  audio.play().catch(() => {});

  audioTimeout = setTimeout(() => {
    audio.loop = false;
    audio.pause();
    audio.currentTime = 0;
  }, duracionSegundos * 1000);
}

function _detenerAudios() {
  clearTimeout(audioTimeout);
  audioTimeout = null;

  audioInhalar.loop = false;
  audioInhalar.pause();
  audioInhalar.currentTime = 0;

  audioExhalar.loop = false;
  audioExhalar.pause();
  audioExhalar.currentTime = 0;

  if (_tonoOsc) {
    try { _tonoOsc.stop(); } catch (_) {}
    _tonoOsc = null;
  }
}

let _tonoCtx = null;
let _tonoOsc = null;

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
  gain.gain.setValueAtTime(0.01, now + duracionSegundos - 1);
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
  const overlay = document.getElementById("overlay-respiracion");
  const titulo = document.getElementById("resp-titulo");
  const instruccion = document.getElementById("resp-text-instruccion");
  const circulo = document.getElementById("resp-circle");
  const subtext = document.getElementById("resp-subtext");

  if (!overlay) return;

  overlay.classList.remove("hidden");
  titulo.innerText = data.nombre;
  subtext.innerText = data.instruccion || "";

  const { inhalar, retener, exhalar, esperar } = data.patron;

  const tInhalar = inhalar * 1000;
  const tRetener = retener * 1000;
  const tExhalar = exhalar * 1000;
  const tEsperar = esperar * 1000;

  const cicloTotal = tInhalar + tRetener + tExhalar + tEsperar;

  function ciclo() {
    if (overlay.classList.contains("hidden")) return;

    instruccion.innerText = "Inhalá";
    circulo.style.transition = `transform ${inhalar}s ease-in-out, background-color ${inhalar}s`;
    circulo.style.transform = "scale(1.5)";
    circulo.style.backgroundColor = "rgba(143, 181, 163, 0.8)";
    reproducirSonidoFase('inhalar', inhalar);

    setTimeout(() => {
      if (retener > 0) {
        instruccion.innerText = "Sostené";
        reproducirSonidoFase('retener', retener);
      }

      setTimeout(() => {
        instruccion.innerText = "Exhalá";
        circulo.style.transition = `transform ${exhalar}s ease-in-out, background-color ${exhalar}s`;
        circulo.style.transform = "scale(1)";
        circulo.style.backgroundColor = "rgba(183, 211, 198, 0.6)";
        reproducirSonidoFase('exhalar', exhalar);

        setTimeout(() => {
          if (esperar > 0) {
            instruccion.innerText = "Pausa";
            reproducirSonidoFase('esperar', esperar);
          }
        }, tExhalar);

      }, tRetener);

    }, tInhalar);
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
  _detenerAudios();
  detenerSonidoAmbiente();  // ← NUEVO: apagar sonido de fondo al cerrar con ✕
}

// ============================================
// FUNCIONES PRIVADAS
// ============================================

function finalizarRespiracion(nombreEjercicio) {
  clearInterval(intervalRespiracion);
  intervalRespiracion = null;
  _detenerAudios();
  detenerSonidoAmbiente();  // ← NUEVO: apagar sonido de fondo al terminar el minuto

  const titulo = document.getElementById("resp-titulo");
  const instruccion = document.getElementById("resp-text-instruccion");
  const circulo = document.getElementById("resp-circle");

  if (titulo) titulo.innerText = "¡Excelente!";
  if (instruccion) instruccion.innerText = "Terminaste. Bien hecho.";
  if (circulo) circulo.style.display = "none";

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