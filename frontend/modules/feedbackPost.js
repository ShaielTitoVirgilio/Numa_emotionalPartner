// modules/feedbackPost.js
// Sistema de feedback post-ejercicio para Numa

// ============================================
// CONFIGURACIÓN DE OPCIONES
// ============================================

const OPCIONES_FEEDBACK = [
    { id: "helped_a_lot", emoji: "✨", texto: "Me sirvió mucho", valor: "positive_high" },
    { id: "helped_a_bit", emoji: "🌿", texto: "Un poco mejor", valor: "positive_low" },
    { id: "same",         emoji: "😐", texto: "Sigo igual",    valor: "neutral" },
    { id: "not_really",  emoji: "😔", texto: "No tanto",      valor: "negative" },
  ];
  
  // Respuestas de Numa según el resultado — mantiene el tono de amigo
  const RESPUESTAS_NUMA = {
    positive_high: [
      "Me alegra. El cuerpo sabe cuándo algo le hace bien.",
      "Bueno, eso. Guardalo para la próxima vez que lo necesités.",
      "Eso. Ahora ya sabés que funciona para vos.",
    ],
    positive_low: [
      "Un poco es suficiente para empezar.",
      "Aunque sea un poco, algo se movió. Eso cuenta.",
      "Bien. A veces el cuerpo necesita más de una vez, pero ya arrancaste.",
    ],
    neutral: [
      "Está bien. No todos los ejercicios funcionan igual para todos.",
      "A veces el cuerpo tarda en responder. ¿Querés probar algo diferente?",
      "No pasa nada. ¿Hubo algo que te molestó del ejercicio o simplemente no era el momento?",
    ],
    negative: [
      "Gracias por decirme. ¿Querés contarme qué está pasando?",
      "Entendido. Seguís acá, eso ya es algo. ¿Qué necesitás ahora?",
      "Okey. No te voy a mandar otro ejercicio. ¿Querés hablar un rato?",
    ],
  };
  
  // ============================================
  // ESTADO INTERNO
  // ============================================
  
  let onFeedbackCallback = null; // función para enviar respuesta al chat
  
  // ============================================
  // FUNCIONES PÚBLICAS
  // ============================================
  
  /**
   * Muestra el panel de feedback post-ejercicio
   * @param {string} nombreEjercicio - nombre del ejercicio finalizado
   * @param {Function} onRespuesta - callback(valorFeedback, textoFeedback) cuando el usuario responde
   */
  export function mostrarFeedback(nombreEjercicio, onRespuesta) {
    onFeedbackCallback = onRespuesta;
  
    // Remover panel anterior si existe
    const anterior = document.getElementById("feedback-post-ejercicio");
    if (anterior) anterior.remove();
  
    const panel = document.createElement("div");
    panel.id = "feedback-post-ejercicio";
    panel.innerHTML = _buildHTML(nombreEjercicio);
  
    // Estilos del panel (overlay suave encima del chat)
    Object.assign(panel.style, {
      position: "fixed",
      bottom: "0",
      left: "50%",
      transform: "translateX(-50%)",
      width: "100%",
      maxWidth: "390px",
      background: "linear-gradient(to top, #eaf4ef 80%, transparent)",
      padding: "28px 24px 32px",
      zIndex: "500",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      gap: "12px",
      animation: "feedbackSlideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards",
    });
  
    document.body.appendChild(panel);
    _inyectarEstilos();
  
    // Bind de botones
    panel.querySelectorAll(".feedback-opcion").forEach(btn => {
      btn.addEventListener("click", () => {
        const valor = btn.dataset.valor;
        const texto = btn.dataset.texto;
        _seleccionarOpcion(btn, valor, texto);
      });
    });
  }
  
  /**
   * Cierra el panel de feedback (sin respuesta)
   */
  export function cerrarFeedback() {
    const panel = document.getElementById("feedback-post-ejercicio");
    if (panel) {
      panel.style.animation = "feedbackSlideDown 0.3s ease forwards";
      setTimeout(() => panel.remove(), 300);
    }
  }
  
  /**
   * Genera la respuesta de Numa para un valor de feedback dado
   */
  export function getRespuestaNuma(valor) {
    const opciones = RESPUESTAS_NUMA[valor] || RESPUESTAS_NUMA.neutral;
    return opciones[Math.floor(Math.random() * opciones.length)];
  }
  
  // ============================================
  // FUNCIONES PRIVADAS
  // ============================================
  
  function _buildHTML(nombreEjercicio) {
    const opcionesHTML = OPCIONES_FEEDBACK.map(op => `
      <button 
        class="feedback-opcion" 
        data-valor="${op.valor}" 
        data-texto="${op.texto}"
        aria-label="${op.texto}"
      >
        <span class="feedback-emoji">${op.emoji}</span>
        <span class="feedback-label">${op.texto}</span>
      </button>
    `).join("");
  
    return `
      <p class="feedback-pregunta">
        ¿Cómo quedaste después de <strong>${nombreEjercicio}</strong>?
      </p>
      <div class="feedback-opciones">
        ${opcionesHTML}
      </div>
      <button class="feedback-skip" id="feedback-skip-btn">Saltar</button>
    `;
  }
  
  function _seleccionarOpcion(btnEl, valor, texto) {
    // Feedback visual — marcar seleccionado
    document.querySelectorAll(".feedback-opcion").forEach(b => {
      b.classList.remove("selected");
      b.disabled = true;
    });
    btnEl.classList.add("selected");
  
    // Pequeño delay antes de cerrar para que se vea la selección
    setTimeout(() => {
      cerrarFeedback();
      if (onFeedbackCallback) {
        onFeedbackCallback(valor, texto);
      }
    }, 500);
  }
  
  function _inyectarEstilos() {
    if (document.getElementById("feedback-styles")) return;
  
    const style = document.createElement("style");
    style.id = "feedback-styles";
    style.textContent = `
      @keyframes feedbackSlideUp {
        from { opacity: 0; transform: translateX(-50%) translateY(20px); }
        to   { opacity: 1; transform: translateX(-50%) translateY(0); }
      }
      @keyframes feedbackSlideDown {
        from { opacity: 1; transform: translateX(-50%) translateY(0); }
        to   { opacity: 0; transform: translateX(-50%) translateY(20px); }
      }
  
      .feedback-pregunta {
        font-size: 1rem;
        color: #4a6a5e;
        text-align: center;
        margin: 0;
        line-height: 1.5;
      }
  
      .feedback-pregunta strong {
        color: #2f4f45;
      }
  
      .feedback-opciones {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
        width: 100%;
      }
  
      .feedback-opcion {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 6px;
        padding: 14px 10px;
        border: 2px solid #d4e5df;
        border-radius: 16px;
        background: white;
        cursor: pointer;
        transition: all 0.2s ease;
        color: #4a6a5e;
      }
  
      .feedback-opcion:hover:not(:disabled) {
        border-color: #a6c7b8;
        background: #f0f8f4;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
      }
  
      .feedback-opcion:disabled {
        opacity: 0.5;
        cursor: default;
      }
  
      .feedback-opcion.selected {
        border-color: #6b8e7d;
        background: #e8f5f0;
        opacity: 1 !important;
        transform: scale(1.03);
        box-shadow: 0 4px 16px rgba(107, 142, 125, 0.25);
      }
  
      .feedback-emoji {
        font-size: 1.6rem;
        line-height: 1;
      }
  
      .feedback-label {
        font-size: 0.82rem;
        font-weight: 600;
        text-align: center;
        line-height: 1.3;
      }
  
      .feedback-skip {
        background: none;
        border: none;
        color: #8fb5a3;
        font-size: 0.8rem;
        cursor: pointer;
        padding: 4px 8px;
        text-decoration: underline;
        text-underline-offset: 3px;
        transition: color 0.2s;
      }
  
      .feedback-skip:hover {
        color: #4a6a5e;
      }
    `;
    document.head.appendChild(style);
  
    // Bind del botón saltar
    setTimeout(() => {
      const skipBtn = document.getElementById("feedback-skip-btn");
      if (skipBtn) skipBtn.addEventListener("click", cerrarFeedback);
    }, 0);
  }