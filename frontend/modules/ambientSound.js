// modules/ambientSound.js
// Sonidos de fondo — versión robusta para mobile (iOS / Android)
// ===============================================================

// ============================================
// CATÁLOGO DE SONIDOS
// ============================================
export const SONIDOS_AMBIENTE = [
  { id: "lluvia", label: "🌧️ Lluvia", desc: "Gotas suaves y constantes" },
  { id: "olas", label: "🌊 Olas del mar", desc: "Mar tranquilo y rítmico" },
  { id: "fuego", label: "🔥 Fuego", desc: "Crepitar de leña" },
  { id: "viento", label: "🍃 Bosque", desc: "Brisa entre los árboles" },
  { id: "ninguno", label: "🔇 Sin sonido", desc: "Solo silencio" },
];

const AUDIO_FILES = {
  lluvia: "/static/assets/rain_loop.mp3",
  olas: "/static/assets/wave_loop.mp3",
  fuego: "/static/assets/fire_loop.mp3",
  viento: "/static/assets/forest_loop.mp3",
};

const STORAGE_KEY = "numa_ambient_sound";
const DEFAULT_SOUND = "lluvia";
const VOLUME = 0.13;

// ============================================
// ESTADO INTERNO
// ============================================
let _audio = null;
let _currentId = null;
let _isPlaying = false;
let _fadeInterval = null;

// ============================================
// INYECTAR ESTILOS AL CARGAR
// ============================================
_inyectarEstilosSonido();

// ============================================
// FUNCIONES PÚBLICAS
// ============================================
export function getSonidoGuardado() {
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_SOUND;
}

export function guardarPreferenciaSonido(id) {
  localStorage.setItem(STORAGE_KEY, id);
}

export function iniciarSonidoAmbiente(id = null) {
  const sonidoId = id || getSonidoGuardado();
  if (sonidoId === "ninguno") return;

  // Si ya está sonando el mismo, no hacer nada
  if (_isPlaying && _currentId === sonidoId) return;

  // 🔴 CORTE DURO DEL AUDIO ANTERIOR (mobile-safe)
  _detenerInmediato();

  const src = AUDIO_FILES[sonidoId];
  if (!src) return;

  const audio = new Audio(src);
  audio.loop = true;
  audio.volume = 0;

  _audio = audio;
  _currentId = sonidoId;
  _isPlaying = true;

  audio.play().catch(() => {});
  _fadeIn(2000);
}

export function detenerSonidoAmbiente() {
  // Corte inmediato y definitivo (sin fade en mobile)
  _detenerInmediato();
}

export function cambiarSonido(id) {
  guardarPreferenciaSonido(id);
  window.dispatchEvent(new CustomEvent("numa:soundChanged", { detail: { id } }));

  _detenerInmediato();

  if (id !== "ninguno") {
    setTimeout(() => iniciarSonidoAmbiente(id), 200);
  }
}

// ============================================
// SELECTOR DE SONIDO (UI)
// ============================================
export function mostrarSelectorSonido() {
  const anterior = document.getElementById("ambient-sound-panel");
  if (anterior) {
    anterior.remove();
    return;
  }

  const panel = document.createElement("div");
  panel.id = "ambient-sound-panel";

  const actual = getSonidoGuardado();

  panel.innerHTML = `
    <div class="as-backdrop"></div>
    <div class="as-sheet">
      <div class="as-header">
        <span class="as-title">🎵 Sonido de fondo</span>
        <span class="as-subtitle">Para meditación, yoga y lectura</span>
        <button class="as-close" id="as-close-btn">✕</button>
      </div>
      <div class="as-list">
        ${SONIDOS_AMBIENTE.map(
          s => `
          <button class="as-item ${s.id === actual ? "as-item--active" : ""}" data-id="${s.id}">
            <span class="as-icon">${s.label.split(" ")[0]}</span>
            <div class="as-info">
              <span class="as-name">${s.label.slice(s.label.indexOf(" ") + 1)}</span>
              <span class="as-desc">${s.desc}</span>
            </div>
            <span class="as-check">${s.id === actual ? "✓" : ""}</span>
          </button>
        `
        ).join("")}
      </div>
      <p class="as-note">Se activa al iniciar meditación, yoga y lectura</p>
    </div>
  `;

  document.body.appendChild(panel);
  requestAnimationFrame(() =>
    panel.querySelector(".as-sheet").classList.add("as-sheet--visible")
  );

  const cerrar = () => {
    panel.querySelector(".as-sheet").classList.remove("as-sheet--visible");
    setTimeout(() => panel.remove(), 300);
  };

  panel.querySelector(".as-backdrop").addEventListener("click", cerrar);
  panel.querySelector("#as-close-btn").addEventListener("click", cerrar);

  panel.querySelectorAll(".as-item").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      cambiarSonido(id);
      setTimeout(cerrar, 600);
    });
  });
}

// ============================================
// HELPERS INTERNOS — CLAVE PARA MOBILE
// ============================================

/**
 * 🔴 CORTE REAL DEL AUDIO
 * Esto es lo que evita los audios “fantasma” en iOS / Android
 */
function _detenerInmediato() {
  clearInterval(_fadeInterval);
  _fadeInterval = null;

  if (_audio) {
    try {
      _audio.pause();
      _audio.currentTime = 0;

      // 🔥 CLAVE MOBILE
      _audio.removeAttribute("src");
      _audio.load();
    } catch (_) {}

    _audio = null;
  }

  _currentId = null;
  _isPlaying = false;
}

function _fadeIn(durationMs) {
  clearInterval(_fadeInterval);

  if (!_audio) return;

  const steps = 20;
  const stepTime = durationMs / steps;
  const stepVol = VOLUME / steps;
  let current = 0;

  _fadeInterval = setInterval(() => {
    if (!_audio) {
      clearInterval(_fadeInterval);
      return;
    }
    current += stepVol;
    _audio.volume = Math.min(current, VOLUME);
    if (current >= VOLUME) clearInterval(_fadeInterval);
  }, stepTime);
}

// ============================================
// ESTILOS (sin cambios funcionales)
// ============================================
function _inyectarEstilosSonido() {
  if (document.getElementById("ambient-sound-styles")) return;

  const style = document.createElement("style");
  style.id = "ambient-sound-styles";
  style.textContent = `
  /* ============================================
     OVERLAY FULLSCREEN
  ============================================ */
  #ambient-sound-panel {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    z-index: 9999;

    display: flex;
    align-items: flex-end;
    justify-content: center;
  }

  .as-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(47, 79, 69, 0.25);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
  }

  /* ============================================
     SHEET DESDE ABAJO
  ============================================ */
  .as-sheet {
    position: relative;
    width: 100%;
    max-width: 430px;

    background: linear-gradient(160deg, #eaf4ef 0%, #f6fbf8 100%);
    border-radius: 24px 24px 0 0;

    padding: 24px 20px 32px;

    transform: translateY(100%);
    transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);

    box-shadow: 0 -8px 40px rgba(47, 79, 69, 0.15);
  }

  .as-sheet--visible {
    transform: translateY(0);
  }

  /* ============================================
     HEADER
  ============================================ */
  .as-header {
    display: flex;
    flex-direction: column;
    align-items: center;
    position: relative;
    margin-bottom: 20px;
  }

  .as-title {
    font-size: 1.15rem;
    font-weight: 800;
    color: #2f4f45;
  }

  .as-subtitle {
    font-size: 0.82rem;
    color: #8fb5a3;
    margin-top: 2px;
  }

  .as-close {
    position: absolute;
    top: 0;
    right: 0;

    background: rgba(183, 211, 198, 0.5);
    border: none;

    width: 36px;
    height: 36px;
    border-radius: 50%;

    font-size: 1rem;
    color: #4a6a5e;
    cursor: pointer;
  }

  /* ============================================
     LISTA DE SONIDOS
  ============================================ */
  .as-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .as-item {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 14px;

    padding: 14px 16px;
    border-radius: 16px;

    background: white;
    border: 2px solid transparent;

    cursor: pointer;
    transition: all 0.2s ease;
  }

  .as-item:hover {
    border-color: #b7d3c6;
    background: #f0f8f4;
  }

  .as-item--active {
    border-color: #7db89e;
    background: #eaf4ef;
  }

  .as-icon {
    font-size: 1.6rem;
    line-height: 1;
  }

  .as-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
    text-align: left;
  }

  .as-name {
    font-size: 0.95rem;
    font-weight: 700;
    color: #2f4f45;
  }

  .as-desc {
    font-size: 0.78rem;
    color: #8fb5a3;
  }

  .as-check {
    font-size: 1rem;
    font-weight: 800;
    color: #5a9e85;
  }

  .as-note {
    text-align: center;
    font-size: 0.78rem;
    color: #a8c8b8;
    margin-top: 16px;
    font-style: italic;
  }

  /* ============================================
     BOTÓN DEL MENÚ DE EJERCICIOS
  ============================================ */
  .btn-ambient-sound {
    width: 100%;
    max-width: 340px;

    margin-bottom: 12px;

    display: flex;
    align-items: center;
    justify-content: space-between;

    padding: 12px 16px;
    border-radius: 16px;

    background: rgba(255,255,255,0.85);
    border: 1.5px solid #b7d3c6;

    font-size: 0.9rem;
    font-weight: 600;
    color: #4a6a5e;

    cursor: pointer;
  }
  `;
  document.head.appendChild(style);
}