// modules/chat.js
import { CATALOGO_EJERCICIOS } from '../ejerciciosData.js';
import { iniciarEjercicio } from './utils.js';

// ============================================
// ESTADO Y CONFIGURACIÓN
// ============================================

const chat = document.getElementById("chat");
const input = document.getElementById("input");

// 🧠 Historial de conversación
let historialConversacion = [];

// ⏱️ Control de "Enfriamiento" (Throttling)
let ultimoEjercicioSugeridoTime = 0;
const TIEMPO_ENFRIAMIENTO = 300000; // 5 minutos

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

/**
 * Agrega un mensaje al chat visualmente
 */
export function agregarMensaje(texto, tipo) {
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
export async function enviarMensaje() {
    const texto = input.value.trim();
    if (!texto) return;
  
    // 1. Mostrar mensaje usuario
    agregarMensaje(texto, "user");
    input.value = "";
    
    // 2. Estado del oso: Atento
    if (window.setBearState) window.setBearState('listening');
  
    try {
      // 🔥 IMPORTANTE: El backend espera SOLO "conversation"
      // Agregamos el mensaje actual al final del historial antes de enviar
      const conversationToSend = [
        ...historialConversacion,
        { role: "user", content: texto }
      ];

      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          conversation: conversationToSend  // ✅ Solo conversation
        })
      });
  
      if (!res.ok) {
        const errorText = await res.text();
        console.error("❌ ERROR DEL SERVIDOR:", errorText);
        throw new Error("Error en respuesta HTTP");
      }
      
      const data = await res.json();
      
      // El backend ahora devuelve { message, mood, suggested_action, risk_level }
      let respuestaOso = data.message;

      // Detección de ejercicios sugeridos (si lo implementás en el futuro)
      const regexEjercicio = /\[EJERCICIO:\s*(\w+)\]/;
      const match = respuestaOso.match(regexEjercicio);
      
      // Limpiar etiqueta técnica
      let textoLimpio = respuestaOso.replace(regexEjercicio, "").trim();

      // 3. Mostrar respuesta limpia
      agregarMensaje(textoLimpio, "oso");
      
      // 4. Actualizar historial DESPUÉS de recibir respuesta
      historialConversacion.push({ role: "user", content: texto });
      historialConversacion.push({ role: "assistant", content: textoLimpio });

      // 5. Lógica de Sugerencia con enfriamiento
      if (match) {
        const ejercicioId = match[1];
        const ahora = Date.now();

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

/**
 * Muestra un botón de sugerencia de ejercicio en el chat
 */
function mostrarBotonSugerencia(id) {
    // Buscar el ejercicio en el catálogo
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
    
    // Crear tarjeta de sugerencia
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
    
    // Estilar botón
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

// Exportar historial si otros módulos lo necesitan
export function getHistorial() {
    return historialConversacion;
}

export function resetHistorial() {
    historialConversacion = [];
}