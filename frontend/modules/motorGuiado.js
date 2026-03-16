// modules/motorGuiado.js

import { mostrarFeedback, getRespuestaNuma } from './feedbackPost.js';
import { detenerSonidoAmbiente } from './ambientSound.js';

// ============================================
// ESTADO INTERNO
// ============================================

let guiadoTimer = null;
let guiadoInterval = null;
let pasoIndex = 0;
let datosEjercicioActual = null;
let _onFeedbackRespuesta = null;

const TIEMPO_POR_PASO = 15; // segundos

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

export function setFeedbackCallback(fn) {
  _onFeedbackRespuesta = fn;
}

export function runGuiado(tipo, data) {
    const overlay = document.getElementById("overlay-guiado");
    if (!overlay) return;

    overlay.classList.remove("hidden");
    
    document.getElementById("guiado-titulo").innerText = data.nombre;
    const principal = document.getElementById("guiado-paso-principal");
    const instruccion = document.getElementById("guiado-instruccion");
    const timerDisplay = document.getElementById("guiado-timer");
    const videoElement = document.getElementById("numa-video-pose");
    
    timerDisplay.classList.add("hidden");
    principal.innerText = "";
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
    } 
    else if (data.duracion) {
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
    guiadoTimer = null;
    guiadoInterval = null;
    // 🎵 Detener sonido de fondo
    detenerSonidoAmbiente();
}

/**
 * Finaliza el ejercicio con mensaje de cierre + feedback
 */
export function finalizarEjercicio() {
    clearInterval(guiadoInterval);
    clearTimeout(guiadoTimer);

    const principal = document.getElementById("guiado-paso-principal");
    const instruccion = document.getElementById("guiado-instruccion");
    
    if (principal) principal.innerText = "¡Excelente!";
    if (instruccion) instruccion.innerText = "Terminaste. Bien hecho.";

    const video = document.getElementById("numa-video-pose");
    if (video) video.style.display = "none";

    setTimeout(() => {
        const nombreEjercicio = datosEjercicioActual?.nombre || "el ejercicio";

        // 🎵 Detener sonido de fondo (fade out antes del feedback)
        detenerSonidoAmbiente();

        detenerGuiado();

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

    const paso = data.pasos[pasoIndex];
    const videoElement = document.getElementById("numa-video-pose");
    const sourceElement = document.getElementById("numa-video-source");
    const principal = document.getElementById("guiado-paso-principal");
    const instruccion = document.getElementById("guiado-instruccion");
    const progressBar = document.getElementById("guiado-progress");

    principal.innerText = paso.pose || "Paso " + (pasoIndex + 1);
    instruccion.innerText = paso.guia || paso;

    if (paso.animacion) {
        videoElement.style.display = "block";
        videoElement.pause();
        sourceElement.src = paso.animacion;
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

    if (progressBar) {
        progressBar.style.transition = "none";
        progressBar.style.width = "0%";
        setTimeout(() => {
            progressBar.style.transition = `width ${TIEMPO_POR_PASO}s linear`;
            progressBar.style.width = "100%";
        }, 50);
    }

    pasoIndex++;
    guiadoTimer = setTimeout(mostrarPaso, TIEMPO_POR_PASO * 1000);
}

function runTimerSimple(duracion) {
    const timerDisplay = document.getElementById("guiado-timer");
    timerDisplay.classList.remove("hidden");
    
    let tiempoRestante = duracion;
    
    function actualizarTimer() {
        const minutos = Math.floor(tiempoRestante / 60);
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