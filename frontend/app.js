import { CATALOGO_EJERCICIOS } from './ejerciciosData.js';

// ============================================
// 1. CONFIGURACIÓN E INICIALIZACIÓN
// ============================================

const chat = document.getElementById("chat");
const input = document.getElementById("input");
const bear = document.getElementById("bear");

// 🧠 Historial de conversación
let historialConversacion = [];

// ⏱️ Control de "Enfriamiento" (Throttling)
// Evita que la IA sugiera ejercicios en cada mensaje seguido
let ultimoEjercicioSugeridoTime = 0;
const TIEMPO_ENFRIAMIENTO = 300000; // 5 minutos (300,000 ms)

/**
 * Agrega un mensaje al chat visualmente
 */
function agregarMensaje(texto, tipo) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${tipo}`;

  if (typeof texto === "string") {
    bubble.innerText = texto;
  } else if (texto && typeof texto === "object" && texto.oso) {
    bubble.innerText = texto.oso;
  } else {
    bubble.innerText = "…";
  }

  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
}

/**
 * Envía mensaje al backend y procesa la respuesta inteligente
 */
async function enviarMensaje() {
    const texto = input.value.trim();
    if (!texto) return;
  
    // 1. Mostrar mensaje usuario
    agregarMensaje(texto, "user");
    input.value = "";
    historialConversacion.push({ role: "user", content: texto });
  
    // 2. Estado del oso: Atento
    if (window.setBearState) window.setBearState('listening');
  
    try {
      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          texto,
          historial: historialConversacion
        })
      });
  
      if (!res.ok) throw new Error("Error en respuesta HTTP");
      
      const data = await res.json();
      let respuestaOso = data.oso;

      // ======================================================
      // 🕵️‍♀️ DETECCIÓN INTELIGENTE DE EJERCICIOS (NUEVO)
      // ======================================================
      // Buscamos si la IA mandó una etiqueta oculta tipo: [EJERCICIO: respiracion_box]
      const regexEjercicio = /\[EJERCICIO:\s*(\w+)\]/;
      const match = respuestaOso.match(regexEjercicio);
      
      // Limpiamos la etiqueta para que el usuario no vea el código técnico
      let textoLimpio = respuestaOso.replace(regexEjercicio, "").trim();

      // 3. Mostrar respuesta limpia del oso
      agregarMensaje(textoLimpio, "oso");
      historialConversacion.push({ role: "assistant", content: textoLimpio });

      // 4. Lógica de Sugerencia
      if (match) {
        const ejercicioId = match[1]; // ej: "respiracion_478"
        const ahora = Date.now();

        // Verificamos si pasó el tiempo de enfriamiento
        if (ahora - ultimoEjercicioSugeridoTime > TIEMPO_ENFRIAMIENTO) {
            mostrarBotonSugerencia(ejercicioId);
            ultimoEjercicioSugeridoTime = ahora;
        } else {
            console.log("Sugerencia suprimida por enfriamiento (anti-spam).");
        }
      }

    } catch (error) {
      console.error("❌ Error:", error);
      agregarMensaje("Estoy acá contigo. (Error de conexión)", "oso");
    } finally {
      if (window.setBearState) window.setBearState('calm');
    }
}

// Exponer enviarMensaje globalmente para el botón HTML
window.enviarMensaje = enviarMensaje;


// ============================================
// 2. RENDERIZADO DE SUGERENCIAS (CHAT)
// ============================================

function mostrarBotonSugerencia(id) {
    // Buscar el ejercicio en el catálogo importado
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

    const bubble = document.createElement("div");
    bubble.className = "bubble oso";
    
    // Crear tarjeta bonita dentro del chat
    const div = document.createElement("div");
    div.innerHTML = `
        <p style="font-size: 0.9em; margin-bottom: 8px;">Creo que esto te puede ayudar ahora:</p>
        <button class="exercise-suggestion-btn">
            ✨ ${ejercicioEncontrado.nombre}
        </button>
        <p style="font-size: 0.75em; opacity: 0.8; margin-top: 6px; font-style: italic;">
           "${ejercicioEncontrado.cientifico || 'Técnica recomendada'}"
        </p>
    `;
    
    // Estilar botón dinámicamente
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
// 3. SISTEMA DE MENÚS DINÁMICOS
// ============================================

// Abre el menú principal de categorías
window.irAEjercicios = function() {
    const menu = document.getElementById("ejercicios-menu"); // Nuevo ID
    const lista = document.getElementById("lista-categorias");
    
    if(!menu || !lista) return console.error("Faltan elementos del menú nuevo en HTML");

    lista.innerHTML = ""; // Limpiar lista anterior

    const categorias = [
        { key: "respiracion", label: "🌬️ Respiración", desc: "Calma el sistema nervioso" },
        { key: "meditacion", label: "🧘 Meditación", desc: "Claridad y pausa mental" },
        { key: "yoga", label: "🕉️ Cuerpo y Movimiento", desc: "Soltar tensión física" }
    ];

    categorias.forEach(cat => {
        const btn = document.createElement("button");
        btn.className = "exercise-btn"; 
        btn.innerHTML = `
            <strong>${cat.label}</strong>
            <br>
            <span style="font-size:0.8em; opacity:0.8">${cat.desc}</span>
        `;
        btn.onclick = () => abrirSubmenu(cat.key);
        lista.appendChild(btn);
    });

    // Agregar botón de Lectura (Legacy) al final
    const btnLectura = document.createElement("button");
    btnLectura.className = "exercise-btn";
    btnLectura.innerHTML = `<strong>📖 Lectura</strong><br><span style="font-size:0.8em; opacity:0.8">Frases inspiradoras</span>`;
    btnLectura.onclick = () => window.showReading(); // Función legacy
    lista.appendChild(btnLectura);

    menu.classList.remove("hidden");
};

window.cerrarMenuEjercicios = function() {
    document.getElementById("ejercicios-menu").classList.add("hidden");
};

// Abre el submenú con la lista de ejercicios de esa categoría
function abrirSubmenu(categoriaKey) {
    document.getElementById("ejercicios-menu").classList.add("hidden");
    const submenu = document.getElementById("submenu-detalle");
    submenu.classList.remove("hidden");
    
    const titulo = document.getElementById("titulo-submenu");
    const lista = document.getElementById("lista-ejercicios-detalle");
    lista.innerHTML = "";

    // Capitalizar título
    titulo.innerText = categoriaKey.charAt(0).toUpperCase() + categoriaKey.slice(1);

    const ejercicios = CATALOGO_EJERCICIOS[categoriaKey];

    ejercicios.forEach(ej => {
        const card = document.createElement("div");
        card.style.cssText = "background: white; padding: 15px; border-radius: 12px; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);";
        
        card.innerHTML = `
            <h3 style="color: #4a6a5e; margin-bottom: 5px; font-size: 1.1rem;">${ej.nombre}</h3>
            <p style="font-size: 0.9rem; color: #666; margin-bottom: 8px;">${ej.descripcion}</p>
            <p style="font-size: 0.8rem; color: #8fb5a3; font-style: italic; margin-bottom: 10px;">💡 ${ej.cientifico || "Validado."}</p>
            <button class="btn-start-ejercicio">Empezar</button>
        `;
        
        const btnStart = card.querySelector(".btn-start-ejercicio");
        btnStart.style.cssText = "background:#b7d3c6; border:none; padding:8px 16px; border-radius:20px; cursor:pointer; width:100%; color: #2f4f45; font-weight: bold;";
        
        btnStart.onclick = () => iniciarEjercicio(categoriaKey, ej);
        lista.appendChild(card);
    });
}

window.volverAMenuPrincipal = function() {
    document.getElementById("submenu-detalle").classList.add("hidden");
    document.getElementById("ejercicios-menu").classList.remove("hidden");
};

window.volverAlChat = function() {
    document.getElementById("ejercicios-menu").classList.add("hidden");
    document.getElementById("submenu-detalle").classList.add("hidden");
    // También cerrar overlays por si acaso
    window.detenerRespiracion();
    window.detenerGuiado();
    window.closeReading();
};


// ============================================
// 4. MOTOR DE EJERCICIOS (EJECUCIÓN)
// ============================================

// MODIFICACIÓN: Función de inicio con pantalla de preparación
function iniciarEjercicio(tipo, data) {
    const prep = document.getElementById("prep-screen");
    const prepText = document.getElementById("prep-text");
    
    // Cerrar menús
    document.getElementById("ejercicios-menu").classList.add("hidden");
    document.getElementById("submenu-detalle").classList.add("hidden");

    // Mostrar pantalla de preparación
    prep.classList.remove("hidden");
    prepText.innerText = `Preparando ${data.nombre}...`;

    // Esperar 3 segundos de "aire" antes de empezar
    setTimeout(() => {
        prep.classList.add("hidden");
        if (tipo === "respiracion") runRespiracion(data);
        else if (tipo === "meditacion" || tipo === "yoga") runGuiado(tipo, data);
    }, 3000);
}

// MODIFICACIÓN: Motor guiado con CONTADOR VISUAL
function runGuiado(tipo, data) {
    const overlay = document.getElementById("overlay-guiado");
    if(!overlay) return;

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
        // Modo Yoga o Meditación con guía paso a paso
        mostrarPaso(); 
    } 
    else if (data.duracion) {
        // Modo Meditación simple (solo tiempo y respiración)
        runTimerSimple(data.duracion);
    }
}

function finalizarEjercicio() {
    // 1. Detener todos los timers activos para que no se pisen
    clearInterval(intervalRespiracion);
    clearInterval(guiadoInterval);
    clearTimeout(guiadoTimer);

    // 2. Mostrar mensaje de despedida en el overlay que esté abierto
    const principal = document.getElementById("guiado-paso-principal") || document.getElementById("resp-titulo");
    const instruccion = document.getElementById("guiado-instruccion") || document.getElementById("resp-text-instruccion");
    
    if (principal) principal.innerText = "¡Excelente!";
    if (instruccion) instruccion.innerText = "Podés volver cuando quieras.";

    // 3. Ocultar video o círculos
    const video = document.getElementById("numa-video-pose");
    const circulo = document.getElementById("resp-circle");
    if (video) video.style.display = "none";
    if (circulo) circulo.style.display = "none";

    // 4. Cerrar todo automáticamente en 4 segundos
    setTimeout(() => {
        window.detenerGuiado();
        window.detenerRespiracion();
        // Resetear visibilidad por si se vuelve a entrar
        if (circulo) circulo.style.display = "block"; 
    }, 4000);
}

async function mostrarPaso() {
    const data = datosEjercicioActual; // Usamos la data guardada
    const TIEMPO_POR_PASO = 15; 

    if (pasoIndex >= data.pasos.length) {
        finalizarEjercicio(); // <--- Llamada a la nueva función
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

    // Lógica de Video mejorada para evitar el error de ruta
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
            try { await videoElement.play(); } catch (e) { console.log("Play diferido"); }
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

function renderSuggestions(suggestions) {
    if (!suggestions || suggestions.length === 0) return;
  
    const container = document.createElement("div");
    container.className = "suggestions";
  
    suggestions.forEach(s => {
      const chip = document.createElement("button");
      chip.className = "suggestion-chip";
      chip.innerText = s.label;
  
      chip.onclick = () => openExercise(s.id);
  
      container.appendChild(chip);
    });
  
    chat.appendChild(container);
  }

  
  import { ejercicios } from "./ejerciciosData.js";

function openExercise(id) {
  const ejercicio = ejercicios[id];
  if (!ejercicio) return;

  const modal = document.getElementById("exercise-modal");

  modal.querySelector("h2").innerText = ejercicio.titulo;
  modal.querySelector("p").innerText = ejercicio.descripcion;
  modal.querySelector("video").src = ejercicio.video;

  modal.classList.add("open");
}


// --- A. MOTOR DE RESPIRACIÓN ---
let intervalRespiracion = null;

function runRespiracion(data) {
    const overlay = document.getElementById("overlay-respiracion");
    const titulo = document.getElementById("resp-titulo");
    const instruccion = document.getElementById("resp-text-instruccion");
    const circulo = document.getElementById("resp-circle");
    const subtext = document.getElementById("resp-subtext");
    
    if(!overlay) return;

    overlay.classList.remove("hidden");
    titulo.innerText = data.nombre;
    subtext.innerText = data.instruccion || "";
    
    const { inhalar, retener, exhalar, esperar } = data.patron;
    // Tiempos en MS
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
        circulo.style.backgroundColor = "rgba(143, 181, 163, 0.8)"; // Más oscuro

        setTimeout(() => {
            // 2. RETENER (Si aplica)
            if (retener > 0) {
                instruccion.innerText = "Sostené";
            }
            
            setTimeout(() => {
                // 3. EXHALAR
                instruccion.innerText = "Exhalá";
                circulo.style.transition = `transform ${exhalar}s ease-in-out, background-color ${exhalar}s`;
                circulo.style.transform = "scale(1)";
                circulo.style.backgroundColor = "rgba(183, 211, 198, 0.6)"; // Original
                
                setTimeout(() => {
                    // 4. ESPERAR (Si aplica)
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

    setTimeout(() => {
        finalizarEjercicio();
    }, 60000);  // 1 minuto
}

window.detenerRespiracion = function() {
    document.getElementById("overlay-respiracion").classList.add("hidden");
    clearInterval(intervalRespiracion);
    intervalRespiracion = null;
};


// --- B. MOTOR GUIADO (YOGA / MEDITACIÓN) ---
let guiadoTimer = null;
let guiadoInterval = null;
let pasoIndex = 0; // Lo movemos afuera para que sea accesible
let datosEjercicioActual = null;

window.detenerGuiado = function() {
    document.getElementById("overlay-guiado").classList.add("hidden");
    clearTimeout(guiadoTimer);
    clearInterval(guiadoInterval);
    guiadoTimer = null;
    guiadoInterval = null;
};


// ============================================
// 5. LEGACY (LECTURA) - Mantenido simple
// ============================================

const lecturas = [
    { quote: "La paz viene de adentro. No la busques afuera.", author: "Buda" },
    { quote: "No podés detener las olas, pero podés aprender a surfear.", author: "Jon Kabat-Zinn" },
    { quote: "La calma es la cuna del poder.", author: "J.G. Holland" },
    { quote: "Respira. Es solo un mal día, no una mala vida.", author: "Anónimo" }
];
let lecturaIndex = 0;

window.showReading = function() {
    document.getElementById("reading").classList.remove("hidden");
    window.volverAlChat = function() { // Override temporal para el botón cerrar del legacy
        document.getElementById("reading").classList.add("hidden");
        // Restaurar función original después
        window.volverAlChat = function() {
             document.getElementById("ejercicios-menu").classList.add("hidden");
             document.getElementById("submenu-detalle").classList.add("hidden");
             window.detenerRespiracion();
             window.detenerGuiado();
             document.getElementById("reading").classList.add("hidden");
        };
    };
    mostrarLectura();
};

function mostrarLectura() {
    const lectura = lecturas[lecturaIndex];
    document.querySelector(".quote").innerText = `"${lectura.quote}"`;
    document.querySelector(".author").innerText = `— ${lectura.author}`;
}

window.nextReading = function() {
    lecturaIndex = (lecturaIndex + 1) % lecturas.length;
    mostrarLectura();
};

window.closeReading = function() {
    document.getElementById("reading").classList.add("hidden");
};