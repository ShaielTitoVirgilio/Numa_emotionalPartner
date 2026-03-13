// modules/motorRespiracion.js

import { mostrarFeedback, getRespuestaNuma } from './feedbackPost.js';

// ============================================
// ESTADO INTERNO
// ============================================

let intervalRespiracion = null;
let _onFeedbackRespuesta = null;
let audioTimeout = null;
let finalizarTimeout = null; // timeout del minuto completo

// ============================================
// AUDIO — archivos reales
// ============================================

const audioInhalar = new Audio('/static/assets/inhale.mp3');
const audioExhalar = new Audio('/static/assets/exhale.mp3');

audioInhalar.preload = 'auto';
audioExhalar.preload = 'auto';

/**
 * Reproduce el audio de la fase durante exactamente N segundos.
 * Si el archivo es más corto que la fase, lo loopea.
 * Si es más largo, lo corta.
 */
function reproducirSonidoFase(fase, duracionSegundos) {
  // Detener cualquier audio anterior
  _detenerAudios();

  if (fase === 'retener' || fase === 'esperar') return; // silencio en pausa

  const audio = fase === 'inhalar' ? audioInhalar : audioExhalar;

  audio.loop = true; // loopea si el archivo es más corto que la fase
  audio.currentTime = 0;
  audio.play().catch(() => {}); // silencia error si el browser bloquea

  // Cortar exactamente cuando termina la fase
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

    // 1. INHALAR
    instruccion.innerText = "Inhalá";
    circulo.style.transition = `transform ${inhalar}s ease-in-out, background-color ${inhalar}s`;
    circulo.style.transform = "scale(1.5)";
    circulo.style.backgroundColor = "rgba(143, 181, 163, 0.8)";
    reproducirSonidoFase('inhalar', inhalar);

    setTimeout(() => {
      // 2. RETENER
      if (retener > 0) {
        instruccion.innerText = "Sostené";
        reproducirSonidoFase('retener', retener);
      }

      setTimeout(() => {
        // 3. EXHALAR
        instruccion.innerText = "Exhalá";
        circulo.style.transition = `transform ${exhalar}s ease-in-out, background-color ${exhalar}s`;
        circulo.style.transform = "scale(1)";
        circulo.style.backgroundColor = "rgba(183, 211, 198, 0.6)";
        reproducirSonidoFase('exhalar', exhalar);

        setTimeout(() => {
          // 4. ESPERAR
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
}

// ============================================
// FUNCIONES PRIVADAS
// ============================================

function finalizarRespiracion(nombreEjercicio) {
  clearInterval(intervalRespiracion);
  intervalRespiracion = null;
  _detenerAudios();

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