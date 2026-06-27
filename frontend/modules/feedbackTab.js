// modules/feedbackTab.js
// Sección "Tu opinión" — puntuación 1-5 + comentario libre.
// Guarda en Supabase a través del backend (POST /feedback).

import { authHeaders } from './utils.js';

// ============================================
// ESTADO INTERNO
// ============================================

let ratingSeleccionado = null;

// ============================================
// INICIALIZACIÓN DE LA VISTA
// ============================================

export function initFeedbackTab() {
  const container = document.getElementById('view-feedback');
  if (!container) return;

  ratingSeleccionado = null;
  container.dataset.initialized = 'true';

  container.innerHTML = `
    <div class="fb-wrapper">

      <div class="fb-header">
        <h2 class="fb-title">Tu opinión importa</h2>
        <p class="fb-subtitle">
          Numa está en fase de prueba. Cada crítica o idea nos ayuda a mejorar.
        </p>
      </div>

      <!-- PUNTUACIÓN -->
      <div class="fb-section">
        <label class="fb-label">¿Qué tan conforme estás con Numa?</label>
        <div class="fb-rating" id="fb-rating">
          ${[1, 2, 3, 4, 5].map(n => `
            <button class="fb-rating-num" data-value="${n}" onclick="feedbackSelectRating(this)">${n}</button>
          `).join('')}
        </div>
        <div class="fb-rating-legend">
          <span>Nada conforme</span>
          <span>Muy conforme</span>
        </div>
      </div>

      <!-- COMENTARIO -->
      <div class="fb-section">
        <label class="fb-label" for="fb-text">¿Querés contarnos algo más?</label>
        <textarea
          id="fb-text"
          class="fb-textarea"
          placeholder="Qué te gustó, qué no, qué te gustaría que mejore o que agreguemos..."
          rows="5"
        ></textarea>
      </div>

      <!-- SUBMIT -->
      <button class="fb-submit-btn" id="fb-submit-btn" onclick="feedbackSubmit()">
        Enviar
      </button>

      <p class="fb-privacy">
        Tu opinión es anónima (no incluye tus conversaciones) y solo la lee el equipo de Numa.
      </p>

      <!-- ESTADO ENVIADO -->
      <div class="fb-success hidden" id="fb-success">
        <h3>¡Gracias! Recibido.</h3>
        <p>Tu opinión nos ayuda a hacer Numa mejor. De verdad.</p>
        <button class="fb-new-btn" onclick="feedbackReset()">Enviar otra opinión</button>
      </div>

    </div>
  `;

  _inyectarEstilos();
}

// ============================================
// FUNCIONES GLOBALES (llamadas desde HTML inline)
// ============================================

window.feedbackSelectRating = (btn) => {
  document.querySelectorAll('.fb-rating-num').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  ratingSeleccionado = Number(btn.dataset.value);
};

window.feedbackSubmit = async () => {
  const texto = document.getElementById('fb-text')?.value.trim();

  if (!texto && !ratingSeleccionado) {
    _mostrarToast('Elegí una puntuación o escribí un comentario antes de enviar.');
    return;
  }

  const submitBtn = document.getElementById('fb-submit-btn');
  if (submitBtn) {
    submitBtn.textContent = 'Enviando...';
    submitBtn.disabled = true;
  }

  try {
    const res = await fetch('/feedback', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        texto: texto || null,
        categoria: 'general',
        rating: ratingSeleccionado || null,
      }),
    });

    if (!res.ok) throw new Error('Error del servidor');

    document.getElementById('fb-success')?.classList.remove('hidden');
    document.getElementById('fb-submit-btn')?.classList.add('hidden');

  } catch (err) {
    console.error('Error enviando feedback:', err);
    _mostrarToast('No se pudo enviar. Intentá de nuevo.');
    if (submitBtn) {
      submitBtn.textContent = 'Enviar';
      submitBtn.disabled = false;
    }
  }
};

window.feedbackReset = () => {
  ratingSeleccionado = null;
  initFeedbackTab();
};

// ============================================
// HELPERS
// ============================================

function _mostrarToast(msg) {
  const t = document.createElement('div');
  t.style.cssText = `
    position:fixed; bottom:24px; left:50%; transform:translateX(-50%);
    background:#2f4f45; color:white; padding:12px 20px; border-radius:20px;
    font-size:.9rem; font-weight:600; z-index:9999; max-width:90%; text-align:center;
    animation: fadeInUp .3s ease;
  `;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2800);
}

// ============================================
// ESTILOS
// ============================================

function _inyectarEstilos() {
  if (document.getElementById('fb-styles')) return;

  const style = document.createElement('style');
  style.id = 'fb-styles';
  style.textContent = `
    /* ── Wrapper ── */
    .fb-wrapper {
      width: 100%;
      display: flex;
      flex-direction: column;
      gap: 0;
      padding: 4px 0 32px;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
    }

    /* ── Header ── */
    .fb-header {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      padding: 16px 16px 20px;
      gap: 8px;
    }

    .fb-title {
      font-size: 1.35rem;
      font-weight: 800;
      color: #2f4f45;
      margin: 0;
    }

    .fb-subtitle {
      font-size: .9rem;
      color: #6b8e7d;
      line-height: 1.6;
      max-width: 300px;
      margin: 0;
    }

    /* ── Secciones ── */
    .fb-section {
      padding: 0 16px 18px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .fb-label {
      font-size: .9rem;
      font-weight: 800;
      color: #2f4f45;
      letter-spacing: .01em;
    }

    /* ── Textarea ── */
    .fb-textarea {
      width: 100%;
      padding: 14px 16px;
      font-size: 16px;
      font-family: inherit;
      line-height: 1.6;
      border: 2px solid #b7d3c6;
      border-radius: 16px;
      outline: none;
      background: white;
      color: #2f4f45;
      resize: none;
      transition: border-color .2s;
      box-sizing: border-box;
    }

    .fb-textarea:focus {
      border-color: #7db89e;
      box-shadow: 0 0 0 3px rgba(125,184,158,.12);
    }

    .fb-textarea::placeholder { color: #a8c8b8; }

    /* ── Rating 1-5 ── */
    .fb-rating {
      display: flex;
      gap: 8px;
      justify-content: space-between;
    }

    .fb-rating-num {
      flex: 1;
      font-size: 1.1rem;
      font-weight: 800;
      font-family: inherit;
      padding: 12px 4px;
      border: 2px solid #d4e5df;
      border-radius: 14px;
      background: white;
      color: #4a6a5e;
      cursor: pointer;
      transition: all .2s ease;
      line-height: 1;
    }

    .fb-rating-num:hover {
      transform: translateY(-2px);
      border-color: #7db89e;
    }

    .fb-rating-num.selected {
      background: #7db89e;
      border-color: #5a9e85;
      color: white;
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(90,158,133,.25);
    }

    .fb-rating-legend {
      display: flex;
      justify-content: space-between;
      font-size: .72rem;
      color: #a8c8b8;
      padding: 0 2px;
    }

    /* ── Submit ── */
    .fb-submit-btn {
      margin: 0 16px;
      padding: 16px;
      border: none;
      border-radius: 18px;
      background: #7db89e;
      color: white;
      font-family: inherit;
      font-size: 1.05rem;
      font-weight: 800;
      cursor: pointer;
      transition: all .2s ease;
    }

    .fb-submit-btn:hover:not(:disabled) {
      background: #6aaa8f;
      transform: translateY(-2px);
      box-shadow: 0 6px 16px rgba(107,170,143,.3);
    }

    .fb-submit-btn:disabled {
      opacity: .6;
      cursor: default;
    }

    .fb-privacy {
      margin: 10px 16px 0;
      font-size: .75rem;
      color: #a8c8b8;
      text-align: center;
      line-height: 1.5;
    }

    /* ── Success ── */
    .fb-success {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 10px;
      padding: 32px 24px;
      text-align: center;
      animation: fadeInUp .4s ease;
    }

    .fb-success h3 {
      margin: 0;
      font-size: 1.3rem;
      color: #2f4f45;
      font-weight: 800;
    }

    .fb-success p {
      margin: 0;
      color: #6b8e7d;
      font-size: .95rem;
      line-height: 1.5;
    }

    .fb-new-btn {
      margin-top: 8px;
      padding: 12px 24px;
      border: 2px solid #b7d3c6;
      border-radius: 16px;
      background: white;
      color: #4a6a5e;
      font-family: inherit;
      font-weight: 700;
      cursor: pointer;
      transition: all .2s;
    }

    .fb-new-btn:hover {
      background: #eaf4ef;
      border-color: #7db89e;
    }

    .hidden { display: none !important; }

    @keyframes fadeInUp {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }
  `;

  document.head.appendChild(style);
}
