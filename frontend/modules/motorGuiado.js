// modules/motorGuiado.js

import { mostrarFeedback, getRespuestaNuma } from './feedbackPost.js';
import { detenerSonidoAmbiente } from './ambientSound.js';

// ============================================
// ESTADO INTERNO
// ============================================

let guiadoTimer    = null;
let guiadoInterval = null;
let pasoIndex      = 0;
let datosEjercicioActual = null;
let _onFeedbackRespuesta = null;

const TIEMPO_POR_PASO_DEFAULT = 20; // segundos (override con data.tiempoPorPaso)

// ============================================
// AUDIO — PIP DE CAMBIO DE PASO
// Oscillator suave, sin archivos externos.
// AudioContext se crea la primera vez (lazy)
// para respetar la política de autoplay de iOS.
// ============================================

let _pipCtx = null;

function _getCtx() {
    if (!_pipCtx) {
        const AC = window.AudioContext || /** @type {any} */ (window).webkitAudioContext;
        _pipCtx = new AC();
    }
    if (_pipCtx.state === 'suspended') _pipCtx.resume();
    return _pipCtx;
}

/**
 * Toca un "pip" suave — dos tonos breves encadenados (ding ding)
 * para que suene más a campana que a alarma.
 */
function reproducirPip() {
    try {
        const ctx  = _getCtx();
        const now  = ctx.currentTime;

        // Frecuencias: fundamental + quinta (calma, no estrés)
        [528, 660].forEach((freq, i) => {
            const osc  = ctx.createOscillator();
            const gain = ctx.createGain();

            osc.connect(gain);
            gain.connect(ctx.destination);

            osc.type = 'sine';
            osc.frequency.value = freq;

            const t0 = now + i * 0.13; // segundo pip 130ms después del primero
            gain.gain.setValueAtTime(0,    t0);
            gain.gain.linearRampToValueAtTime(0.12, t0 + 0.02);  // ataque rápido
            gain.gain.exponentialRampToValueAtTime(0.001, t0 + 0.22); // decay suave

            osc.start(t0);
            osc.stop(t0 + 0.25);
        });
    } catch (_) {
        // Silencio si el contexto de audio no está disponible
    }
}

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

export function setFeedbackCallback(fn) {
  _onFeedbackRespuesta = fn;
}

export function runGuiado(_tipo, data) {
    const overlay = document.getElementById("overlay-guiado");
    if (!overlay) return;

    overlay.classList.remove("hidden");

    document.getElementById("guiado-titulo").innerText = data.nombre;
    const principal   = document.getElementById("guiado-paso-principal");
    const instruccion = document.getElementById("guiado-instruccion");
    const timerDisplay = document.getElementById("guiado-timer");
    const videoElement = document.getElementById("numa-video-pose");

    timerDisplay.classList.add("hidden");
    principal.innerText   = "";
    instruccion.innerText = "";
    if (videoElement) videoElement.style.display = "none";

    pasoIndex = 0;
    datosEjercicioActual = data;

    const progressBar = document.getElementById("guiado-progress");
    if (progressBar) {
        progressBar.style.transition = "none";
        progressBar.style.width = "0%";
    }

    if (data.pasos && Array.isArray(data.pasos)) {
        mostrarPaso();
    } else if (data.duracion) {
        runTimerSimple(data.duracion);
    }
}

/**
 * Detiene el ejercicio guiado (botón ✕ — sin feedback)
 */
export function detenerGuiado() {
    document.getElementById("overlay-guiado").classList.add("hidden");
    clearTimeout(guiadoTimer);
    clearInterval(guiadoInterval);
    guiadoTimer    = null;
    guiadoInterval = null;
    detenerSonidoAmbiente();
}

/**
 * Finaliza el ejercicio con mensaje de cierre + feedback
 */
export function finalizarEjercicio() {
    clearInterval(guiadoInterval);
    clearTimeout(guiadoTimer);
    guiadoTimer    = null;
    guiadoInterval = null;

    const principal   = document.getElementById("guiado-paso-principal");
    const instruccion = document.getElementById("guiado-instruccion");

    if (principal)   principal.innerText   = "¡Excelente!";
    if (instruccion) instruccion.innerText = "Terminaste. Bien hecho.";

    const video = document.getElementById("numa-video-pose");
    if (video) video.style.display = "none";

    // Detener sonido AQUI, antes del timeout, con referencia todavía válida
    detenerSonidoAmbiente();

    setTimeout(() => {
        const nombreEjercicio = datosEjercicioActual?.nombre || "el ejercicio";

        // Ocultar overlay SIN llamar detenerGuiado (que volvería a llamar detenerSonidoAmbiente)
        document.getElementById("overlay-guiado").classList.add("hidden");

        mostrarFeedback(nombreEjercicio, (valor, textoOpcion) => {
            if (_onFeedbackRespuesta) {
                const respuestaNuma = getRespuestaNuma(valor);
                _onFeedbackRespuesta(textoOpcion, respuestaNuma, valor);
            }
        });
    }, 2500);
}

// ============================================
// FUNCIONES PRIVADAS
// ============================================

async function mostrarPaso() {
    const data = datosEjercicioActual;

    if (pasoIndex >= data.pasos.length) {
        finalizarEjercicio();
        return;
    }

    const paso         = data.pasos[pasoIndex];
    const videoElement = document.getElementById("numa-video-pose");
    const sourceElement = document.getElementById("numa-video-source");
    const principal    = document.getElementById("guiado-paso-principal");
    const instruccion  = document.getElementById("guiado-instruccion");
    const progressBar  = document.getElementById("guiado-progress");

    // Pip de cambio de paso (no en el primero — el usuario acaba de empezar)
    if (pasoIndex > 0) reproducirPip();

    principal.innerText   = paso.pose || "Paso " + (pasoIndex + 1);
    instruccion.innerText = paso.guia || paso;

    if (paso.animacion) {
        videoElement.style.display = "block";
        videoElement.pause();
        sourceElement.src  = paso.animacion;
        sourceElement.type = paso.animacion.toLowerCase().endsWith('.mov')
            ? 'video/quicktime'
            : 'video/mp4';
        videoElement.load();
        videoElement.oncanplay = async () => {
            try { await videoElement.play(); }
            catch (e) { console.log("Play diferido"); }
            videoElement.oncanplay = null;
        };
    } else {
        videoElement.style.display = "none";
    }

    const tiempoPaso = datosEjercicioActual.tiempoPorPaso || TIEMPO_POR_PASO_DEFAULT;

    if (progressBar) {
        progressBar.style.transition = "none";
        progressBar.style.width = "0%";
        setTimeout(() => {
            progressBar.style.transition = `width ${tiempoPaso}s linear`;
            progressBar.style.width = "100%";
        }, 50);
    }

    pasoIndex++;
    guiadoTimer = setTimeout(mostrarPaso, tiempoPaso * 1000);
}

function runTimerSimple(duracion) {
    const timerDisplay = document.getElementById("guiado-timer");
    timerDisplay.classList.remove("hidden");

    let tiempoRestante = duracion;

    function actualizarTimer() {
        const minutos  = Math.floor(tiempoRestante / 60);
        const segundos = tiempoRestante % 60;
        timerDisplay.innerText = `${minutos}:${segundos.toString().padStart(2, '0')}`;

        if (tiempoRestante <= 0) {
            finalizarEjercicio();
            return;
        }
        tiempoRestante--;
    }

    actualizarTimer();
    guiadoInterval = setInterval(actualizarTimer, 1000);
}