// modules/motorGuiado.js

// ============================================
// ESTADO INTERNO
// ============================================

let guiadoTimer = null;
let guiadoInterval = null;
let pasoIndex = 0;
let datosEjercicioActual = null;

const TIEMPO_POR_PASO = 15; // segundos

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

/**
 * Ejecuta ejercicios guiados (meditación/yoga)
 */
export function runGuiado(tipo, data) {
    const overlay = document.getElementById("overlay-guiado");
    if (!overlay) return;

    // 1. Mostrar el panel
    overlay.classList.remove("hidden");
    
    // 2. Referencias a elementos
    document.getElementById("guiado-titulo").innerText = data.nombre;
    const principal = document.getElementById("guiado-paso-principal");
    const instruccion = document.getElementById("guiado-instruccion");
    const timerDisplay = document.getElementById("guiado-timer");
    const videoElement = document.getElementById("numa-video-pose");
    
    // 3. Resetear estado
    timerDisplay.classList.add("hidden");
    principal.innerText = "";
    instruccion.innerText = "";
    if (videoElement) videoElement.style.display = "none";
    
    pasoIndex = 0; 
    datosEjercicioActual = data; 

    // 4. Resetear barra de progreso
    const progressBar = document.getElementById("guiado-progress");
    if (progressBar) {
        progressBar.style.transition = "none";
        progressBar.style.width = "0%";
    }

    // 5. Decidir qué motor arrancar
    if (data.pasos && Array.isArray(data.pasos)) {
        // Modo con pasos (Yoga/Meditación guiada)
        mostrarPaso(); 
    } 
    else if (data.duracion) {
        // Modo simple con timer
        runTimerSimple(data.duracion);
    }
}

/**
 * Detiene el ejercicio guiado
 */
export function detenerGuiado() {
    document.getElementById("overlay-guiado").classList.add("hidden");
    clearTimeout(guiadoTimer);
    clearInterval(guiadoInterval);
    guiadoTimer = null;
    guiadoInterval = null;
}

/**
 * Finaliza el ejercicio con mensaje de cierre
 */
export function finalizarEjercicio() {
    // Detener timers
    clearInterval(guiadoInterval);
    clearTimeout(guiadoTimer);

    const principal = document.getElementById("guiado-paso-principal");
    const instruccion = document.getElementById("guiado-instruccion");
    
    if (principal) principal.innerText = "¡Excelente!";
    if (instruccion) instruccion.innerText = "Podés volver cuando quieras.";

    // Ocultar video
    const video = document.getElementById("numa-video-pose");
    if (video) video.style.display = "none";

    // Cerrar automáticamente después de 4 segundos
    setTimeout(() => {
        detenerGuiado();
    }, 4000);
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

    // Manejo de video
    if (paso.animacion) {
        videoElement.style.display = "block";
        videoElement.pause();
        sourceElement.src = paso.animacion;

        if (paso.animacion.toLowerCase().endsWith('.mov')) {
            sourceElement.type = 'video/quicktime';
        } else {
            sourceElement.type = 'video/mp4';
        }

        videoElement.load();
        videoElement.oncanplay = async () => {
            try { 
                await videoElement.play(); 
            } catch (e) { 
                console.log("Play diferido"); 
            }
            videoElement.oncanplay = null;
        };
    } else {
        videoElement.style.display = "none";
    }

    // Barra de progreso
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
    // Implementación simple para meditaciones sin pasos
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