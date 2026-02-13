// modules/motorRespiracion.js

// ============================================
// ESTADO INTERNO
// ============================================

let intervalRespiracion = null;

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

/**
 * Ejecuta el motor de respiración guiada
 */
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
    
    // Tiempos en milisegundos
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

        setTimeout(() => {
            // 2. RETENER (si aplica)
            if (retener > 0) {
                instruccion.innerText = "Sostené";
            }
            
            setTimeout(() => {
                // 3. EXHALAR
                instruccion.innerText = "Exhalá";
                circulo.style.transition = `transform ${exhalar}s ease-in-out, background-color ${exhalar}s`;
                circulo.style.transform = "scale(1)";
                circulo.style.backgroundColor = "rgba(183, 211, 198, 0.6)";
                
                setTimeout(() => {
                    // 4. ESPERAR (si aplica)
                    if (esperar > 0) {
                        instruccion.innerText = "Pausa";
                    }
                }, tExhalar);
                
            }, tRetener);
            
        }, tInhalar);
    }

    // Ejecutar inmediatamente y luego repetir
    ciclo();
    intervalRespiracion = setInterval(ciclo, cicloTotal);

    // Finalizar después de 1 minuto
    setTimeout(() => {
        finalizarRespiracion();
    }, 60000);
}

/**
 * Detiene el ejercicio de respiración
 */
export function detenerRespiracion() {
    document.getElementById("overlay-respiracion").classList.add("hidden");
    clearInterval(intervalRespiracion);
    intervalRespiracion = null;
}

// ============================================
// FUNCIONES PRIVADAS
// ============================================

function finalizarRespiracion() {
    clearInterval(intervalRespiracion);
    intervalRespiracion = null;

    const titulo = document.getElementById("resp-titulo");
    const instruccion = document.getElementById("resp-text-instruccion");
    const circulo = document.getElementById("resp-circle");
    
    if (titulo) titulo.innerText = "¡Excelente!";
    if (instruccion) instruccion.innerText = "Podés volver cuando quieras.";
    if (circulo) circulo.style.display = "none";

    setTimeout(() => {
        detenerRespiracion();
        // Restaurar visibilidad del círculo
        if (circulo) circulo.style.display = "block";
    }, 4000);
}