// modules/feedbackTab.js
// Pestaña de Feedback — texto + audio opcional
// Guarda en Supabase a través del backend

// ============================================
// ESTADO INTERNO
// ============================================

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let recordingTimer = null;
let recordingSeconds = 0;
let audioBlob = null;
let audioBase64 = null;

// ============================================
// INICIALIZACIÓN DE LA VISTA
// ============================================

export function initFeedbackTab() {
  const container = document.getElementById('view-feedback');
  if (!container || container.dataset.initialized) return;
  container.dataset.initialized = 'true';

  container.innerHTML = `
    <div class="fb-wrapper">

      <div class="fb-header">
        <div class="fb-icon">💬</div>
        <h2 class="fb-title">Tu opinión importa</h2>
        <p class="fb-subtitle">
          Numa está en fase de prueba. Cada crítica o idea nos ayuda a mejorar.
          Podés escribir, grabar un audio, o los dos.
        </p>
      </div>

      <!-- AUDIO -->
      <div class="fb-section">
        <label class="fb-label">🎙️ Grabá tu opinión</label>
        <p class="fb-hint">Máximo 2 minutos. Decinos lo que quieras: qué te gustó, qué no, ideas.</p>

        <div class="fb-audio-area" id="fb-audio-area">
          <button class="fb-record-btn" id="fb-record-btn" onclick="feedbackToggleRecording()">
            <span class="fb-record-icon" id="fb-record-icon">🎙️</span>
            <span id="fb-record-label">Grabar audio</span>
          </button>

          <div class="fb-timer hidden" id="fb-timer">
            <span class="fb-timer-dot"></span>
            <span id="fb-timer-text">0:00</span>
          </div>

          <div class="fb-audio-preview hidden" id="fb-audio-preview">
            <audio id="fb-audio-player" controls style="width:100%; border-radius:12px;"></audio>
            <button class="fb-discard-btn" onclick="feedbackDiscardAudio()">
              🗑️ Descartar audio
            </button>
          </div>

          <div class="fb-no-mic hidden" id="fb-no-mic">
            <p>⚠️ No se pudo acceder al micrófono. Usá el texto abajo.</p>
          </div>
        </div>
      </div>

      <!-- TEXTO -->
      <div class="fb-section">
        <label class="fb-label" for="fb-text">✍️ O escribí tu feedback</label>
        <textarea
          id="fb-text"
          class="fb-textarea"
          placeholder="Ej: me gustó que Numa responda natural, pero a veces tarda mucho... o me gustaría que tenga modo oscuro..."
          rows="5"
        ></textarea>
      </div>

      <!-- CATEGORÍA -->
      <div class="fb-section">
        <label class="fb-label">¿De qué trata tu feedback?</label>
        <div class="fb-tags" id="fb-tags">
          <button class="fb-tag selected" data-value="general" onclick="feedbackSelectTag(this)">General</button>
          <button class="fb-tag" data-value="bug" onclick="feedbackSelectTag(this)">🐛 Bug / Error</button>
          <button class="fb-tag" data-value="idea" onclick="feedbackSelectTag(this)">💡 Idea</button>
          <button class="fb-tag" data-value="ux" onclick="feedbackSelectTag(this)">🎨 Diseño / UX</button>
          <button class="fb-tag" data-value="contenido" onclick="feedbackSelectTag(this)">💬 Respuestas de Numa</button>
          <button class="fb-tag" data-value="ejercicios" onclick="feedbackSelectTag(this)">🧘 Ejercicios</button>
        </div>
      </div>

      <!-- VALORACIÓN RÁPIDA -->
      <div class="fb-section">
        <label class="fb-label">¿Cómo te sentiste usando Numa hoy?</label>
        <div class="fb-rating" id="fb-rating">
          <button class="fb-rating-btn" data-value="1" onclick="feedbackSelectRating(this)" title="Mal">😞</button>
          <button class="fb-rating-btn" data-value="2" onclick="feedbackSelectRating(this)" title="Regular">😐</button>
          <button class="fb-rating-btn" data-value="3" onclick="feedbackSelectRating(this)" title="Bien">🙂</button>
          <button class="fb-rating-btn" data-value="4" onclick="feedbackSelectRating(this)" title="Muy bien">😊</button>
          <button class="fb-rating-btn" data-value="5" onclick="feedbackSelectRating(this)" title="Excelente">🤩</button>
        </div>
      </div>

      <!-- SUBMIT -->
      <button class="fb-submit-btn" id="fb-submit-btn" onclick="feedbackSubmit()">
        Enviar feedback
      </button>

      <p class="fb-privacy">
        🔒 Tu feedback es anónimo (no incluye conversaciones) y solo lo lee el equipo de Numa.
      </p>

      <!-- ESTADO ENVIADO -->
      <div class="fb-success hidden" id="fb-success">
        <div class="fb-success-icon">🐼</div>
        <h3>¡Gracias! Recibido.</h3>
        <p>Tu opinión nos ayuda a hacer Numa mejor. De verdad.</p>
        <button class="fb-new-btn" onclick="feedbackReset()">Enviar otro feedback</button>
      </div>

    </div>
  `;

  _inyectarEstilos();
}

// ============================================
// GRABACIÓN DE AUDIO
// ============================================

async function _iniciarGrabacion() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    // Elegir el formato soportado
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : 'audio/ogg';

    mediaRecorder = new MediaRecorder(stream, { mimeType });
    audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = () => {
      audioBlob = new Blob(audioChunks, { type: mimeType });
      const url = URL.createObjectURL(audioBlob);
      const player = document.getElementById('fb-audio-player');
      if (player) player.src = url;

      // Convertir a base64 para enviar al backend
      const reader = new FileReader();
      reader.onloadend = () => {
        audioBase64 = reader.result.split(',')[1];
      };
      reader.readAsDataURL(audioBlob);

      document.getElementById('fb-audio-preview').classList.remove('hidden');
      stream.getTracks().forEach(t => t.stop());
    };

    mediaRecorder.start(100);
    isRecording = true;
    recordingSeconds = 0;
    _actualizarUI(true);

    // Timer visual
    recordingTimer = setInterval(() => {
      recordingSeconds++;
      const min = Math.floor(recordingSeconds / 60);
      const sec = String(recordingSeconds % 60).padStart(2, '0');
      const timerText = document.getElementById('fb-timer-text');
      if (timerText) timerText.textContent = `${min}:${sec}`;

      // Máximo 2 minutos
      if (recordingSeconds >= 120) _detenerGrabacion();
    }, 1000);

  } catch (err) {
    console.warn('Micrófono no disponible:', err);
    document.getElementById('fb-no-mic')?.classList.remove('hidden');
  }
}

function _detenerGrabacion() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
  clearInterval(recordingTimer);
  isRecording = false;
  _actualizarUI(false);
  document.getElementById('fb-timer').classList.add('hidden');
}

function _actualizarUI(grabando) {
  const btn = document.getElementById('fb-record-btn');
  const icon = document.getElementById('fb-record-icon');
  const label = document.getElementById('fb-record-label');
  const timer = document.getElementById('fb-timer');

  if (!btn) return;

  if (grabando) {
    btn.classList.add('recording');
    if (icon) icon.textContent = '⏹️';
    if (label) label.textContent = 'Detener';
    timer?.classList.remove('hidden');
  } else {
    btn.classList.remove('recording');
    if (icon) icon.textContent = '🎙️';
    if (label) label.textContent = audioBase64 ? 'Volver a grabar' : 'Grabar audio';
  }
}

// ============================================
// FUNCIONES GLOBALES (llamadas desde HTML inline)
// ============================================

window.feedbackToggleRecording = () => {
  if (isRecording) {
    _detenerGrabacion();
  } else {
    // Descartar audio previo si había
    audioBase64 = null;
    audioBlob = null;
    document.getElementById('fb-audio-preview')?.classList.add('hidden');
    _iniciarGrabacion();
  }
};

window.feedbackDiscardAudio = () => {
  audioBase64 = null;
  audioBlob = null;
  document.getElementById('fb-audio-preview')?.classList.add('hidden');
  const icon = document.getElementById('fb-record-icon');
  const label = document.getElementById('fb-record-label');
  if (icon) icon.textContent = '🎙️';
  if (label) label.textContent = 'Grabar audio';
};

window.feedbackSelectTag = (btn) => {
  document.querySelectorAll('.fb-tag').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
};

window.feedbackSelectRating = (btn) => {
  document.querySelectorAll('.fb-rating-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
};

window.feedbackSubmit = async () => {
  const texto = document.getElementById('fb-text')?.value.trim();
  const categoria = document.querySelector('.fb-tag.selected')?.dataset.value || 'general';
  const rating = document.querySelector('.fb-rating-btn.selected')?.dataset.value || null;

  if (!texto && !audioBase64) {
    _mostrarToast('Escribí algo o grabá un audio antes de enviar 🙂');
    return;
  }

  const submitBtn = document.getElementById('fb-submit-btn');
  if (submitBtn) {
    submitBtn.textContent = 'Enviando...';
    submitBtn.disabled = true;
  }

  try {
    const numaUser = localStorage.getItem('numa_user');
    const userId = numaUser ? JSON.parse(numaUser).user_id : null;

    const payload = {
      user_id: userId,
      texto: texto || null,
      categoria,
      rating: rating ? Number(rating) : null,
      audio_base64: audioBase64 || null,
      audio_mime: audioBase64
        ? (MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm' : 'audio/ogg')
        : null,
    };

    const res = await fetch('/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error('Error del servidor');

    // Mostrar éxito
    document.getElementById('fb-success')?.classList.remove('hidden');
    document.getElementById('fb-submit-btn')?.classList.add('hidden');

  } catch (err) {
    console.error('Error enviando feedback:', err);
    _mostrarToast('No se pudo enviar. Intentá de nuevo.');
    if (submitBtn) {
      submitBtn.textContent = 'Enviar feedback';
      submitBtn.disabled = false;
    }
  }
};

window.feedbackReset = () => {
  // Limpiar estado
  audioBase64 = null;
  audioBlob = null;
  isRecording = false;

  const container = document.getElementById('view-feedback');
  if (container) {
    delete container.dataset.initialized;
    initFeedbackTab();
  }
};

// ============================================
// HELPERS
// ============================================

function _mostrarToast(msg) {
  const t = document.createElement('div');
  t.style.cssText = `
    position:fixed; bottom:24px; left:50%; transform:translateX(-50%);
    background:#2f4f45; color:white; padding:12px 20px; border-radius:20px;
    font-size:.9rem; font-weight:600; z-index:9999; white-space:nowrap;
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

    .fb-icon {
      width: 64px; height: 64px;
      background: linear-gradient(135deg, #b7d3c6, #8fb5a3);
      border-radius: 22px;
      display: flex; align-items: center; justify-content: center;
      font-size: 2rem;
      box-shadow: 0 6px 20px rgba(143,181,163,.3);
      margin-bottom: 4px;
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

    .fb-hint {
      font-size: .8rem;
      color: #8fb5a3;
      margin: 0;
      line-height: 1.5;
    }

    /* ── Audio ── */
    .fb-audio-area {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .fb-record-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      padding: 14px 20px;
      border: 2px solid #b7d3c6;
      border-radius: 16px;
      background: white;
      color: #2f4f45;
      font-family: inherit;
      font-size: 1rem;
      font-weight: 700;
      cursor: pointer;
      transition: all .2s ease;
    }

    .fb-record-btn:hover {
      border-color: #7db89e;
      background: #f0f8f4;
    }

    .fb-record-btn.recording {
      background: #fff0f0;
      border-color: #e07070;
      color: #c0392b;
      animation: pulse-record 1.2s ease-in-out infinite;
    }

    @keyframes pulse-record {
      0%, 100% { box-shadow: 0 0 0 0 rgba(224,112,112,.3); }
      50%       { box-shadow: 0 0 0 8px rgba(224,112,112,0); }
    }

    .fb-record-icon { font-size: 1.3rem; }

    .fb-timer {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 14px;
      background: #fff0f0;
      border-radius: 10px;
      font-size: .9rem;
      font-weight: 700;
      color: #c0392b;
    }

    .fb-timer-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #e07070;
      animation: blink-dot 1s ease-in-out infinite;
    }

    @keyframes blink-dot {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0; }
    }

    .fb-audio-preview {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .fb-discard-btn {
      background: none;
      border: none;
      color: #8fb5a3;
      font-family: inherit;
      font-size: .85rem;
      cursor: pointer;
      text-decoration: underline;
      text-underline-offset: 3px;
      text-align: left;
      padding: 0;
      transition: color .2s;
    }

    .fb-discard-btn:hover { color: #c0392b; }

    .fb-no-mic {
      padding: 10px 14px;
      background: #fff8e0;
      border-radius: 12px;
      font-size: .85rem;
      color: #8a6a00;
    }
    .fb-no-mic p { margin: 0; }

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

    /* ── Tags ── */
    .fb-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .fb-tag {
      padding: 8px 14px;
      border: 2px solid #d4e5df;
      border-radius: 20px;
      background: white;
      color: #4a6a5e;
      font-family: inherit;
      font-size: .85rem;
      font-weight: 700;
      cursor: pointer;
      transition: all .2s ease;
    }

    .fb-tag:hover {
      border-color: #7db89e;
      background: #f0f8f4;
    }

    .fb-tag.selected {
      background: #c2ddd3;
      border-color: #7db89e;
      color: #2f4f45;
    }

    /* ── Rating ── */
    .fb-rating {
      display: flex;
      gap: 8px;
      justify-content: space-between;
    }

    .fb-rating-btn {
      flex: 1;
      font-size: 1.6rem;
      padding: 10px 4px;
      border: 2px solid #d4e5df;
      border-radius: 14px;
      background: white;
      cursor: pointer;
      transition: all .2s ease;
      line-height: 1;
    }

    .fb-rating-btn:hover {
      transform: scale(1.12);
      border-color: #7db89e;
    }

    .fb-rating-btn.selected {
      background: #eaf4ef;
      border-color: #5a9e85;
      transform: scale(1.15);
      box-shadow: 0 4px 12px rgba(90,158,133,.2);
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

    .fb-success-icon {
      font-size: 3.5rem;
      animation: bounce-in .5s cubic-bezier(.34,1.56,.64,1);
    }

    @keyframes bounce-in {
      0%   { transform: scale(0); opacity: 0; }
      100% { transform: scale(1); opacity: 1; }
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

    @keyframes fadeInUp {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }
  `;

  document.head.appendChild(style);
}