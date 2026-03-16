// modules/ambientSound.js
// Sonidos de fondo con archivos reales de assets

// ============================================
// CATÁLOGO DE SONIDOS
// ============================================

export const SONIDOS_AMBIENTE = [
  { id: "lluvia",  label: "🌧️ Lluvia",       desc: "Gotas suaves y constantes" },
  { id: "olas",    label: "🌊 Olas del mar",  desc: "Mar tranquilo y rítmico" },
  { id: "fuego",   label: "🔥 Fuego",         desc: "Crepitar de leña" },
  { id: "viento",  label: "🍃 Bosque",        desc: "Brisa entre los árboles" },
  { id: "ninguno", label: "🔇 Sin sonido",    desc: "Solo silencio" },
];

const AUDIO_FILES = {
  lluvia: "/static/assets/rain_loop.mp3",
  olas:   "/static/assets/wave_loop.mp3",
  fuego:  "/static/assets/fire_loop.mp3",
  viento: "/static/assets/forest_loop.mp3",
};

const STORAGE_KEY   = "numa_ambient_sound";
const DEFAULT_SOUND = "lluvia";
const VOLUME        = 0.18;

// ============================================
// ESTADO INTERNO
// ============================================

let _audio       = null;
let _currentId   = null;
let _isPlaying   = false;
let _fadeInterval = null;
// FIX: flag para evitar que un fade-out viejo reactive audio
let _stopGeneration = 0;

// ============================================
// INYECTAR ESTILOS AL CARGAR EL MÓDULO
// (antes era solo al abrir el panel — por eso el botón salía sin estilo)
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
  // Ya está sonando el mismo → no hacer nada
  if (_isPlaying && _currentId === sonidoId) return;

  // Detener lo anterior de forma inmediata (sin fade, para evitar overlap)
  _detenerInmediato();

  const src = AUDIO_FILES[sonidoId];
  if (!src) return;

  const audio = new Audio(src);
  audio.loop   = true;
  audio.volume = 0;

  _audio     = audio;
  _currentId = sonidoId;
  _isPlaying = true;

  audio.play().catch(() => {});
  _fadeIn(2000);
}

export function detenerSonidoAmbiente() {
  if (!_audio) return;

  const audioRef = _audio;
  const gen      = ++_stopGeneration; // generación actual

  _audio     = null;
  _currentId = null;
  _isPlaying = false;
  clearInterval(_fadeInterval);
  _fadeInterval = null;

  // Fade-out usando la generación para que no interfiera con el siguiente audio
  _fadeOut(audioRef, 1500, gen);
}

export function cambiarSonido(id) {
    guardarPreferenciaSonido(id);
    window.dispatchEvent(new CustomEvent("numa:soundChanged", { detail: { id } }));


    detenerSonidoAmbiente();
    if (id !== "ninguno") {
        setTimeout(() => iniciarSonidoAmbiente(id), 200); // pequeño margen
    }
}

export function mostrarSelectorSonido() {
  const anterior = document.getElementById("ambient-sound-panel");
  if (anterior) { anterior.remove(); return; }

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
        ${SONIDOS_AMBIENTE.map(s => `
          <button class="as-item ${s.id === actual ? 'as-item--active' : ''}" data-id="${s.id}">
            <span class="as-icon">${s.label.split(' ')[0]}</span>
            <div class="as-info">
              <span class="as-name">${s.label.slice(s.label.indexOf(' ') + 1)}</span>
              <span class="as-desc">${s.desc}</span>
            </div>
            <span class="as-check">${s.id === actual ? '✓' : ''}</span>
          </button>
        `).join('')}
      </div>]
      <p class="as-note">Se activa al iniciar meditación, yoga y lectura</p>
    </div>
  `;

  document.body.appendChild(panel);

  requestAnimationFrame(() => panel.querySelector('.as-sheet').classList.add('as-sheet--visible'));

  const cerrar = () => {
    panel.querySelector('.as-sheet').classList.remove('as-sheet--visible');
    setTimeout(() => panel.remove(), 300);
  };

  panel.querySelector('.as-backdrop').addEventListener('click', cerrar);
  panel.querySelector('#as-close-btn').addEventListener('click', cerrar);

  panel.querySelectorAll('.as-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.id;

      panel.querySelectorAll('.as-item').forEach(b => {
        b.classList.remove('as-item--active');
        b.querySelector('.as-check').textContent = '';
      });
      btn.classList.add('as-item--active');
      btn.querySelector('.as-check').textContent = '✓';

      cambiarSonido(id);
      setTimeout(cerrar, 900);
    });
  });
}

// ============================================
// HELPERS INTERNOS
// ============================================

/** Detiene el audio SIN fade (para cambios inmediatos) */
function _detenerInmediato() {
  clearInterval(_fadeInterval);
  _fadeInterval = null;
  if (_audio) {
    _audio.pause();
    _audio.src = "";
    _audio     = null;
  }
  _currentId = null;
  _isPlaying = false;
  _stopGeneration++; // invalida cualquier fade-out pendiente
}

function _fadeIn(durationMs) {
  clearInterval(_fadeInterval);
  const steps    = 20;
  const stepTime = durationMs / steps;
  const stepVol  = VOLUME / steps;
  let current    = 0;

  _fadeInterval = setInterval(() => {
    if (!_audio) { clearInterval(_fadeInterval); return; }
    current += stepVol;
    _audio.volume = Math.min(current, VOLUME);
    if (current >= VOLUME) clearInterval(_fadeInterval);
  }, stepTime);
}

/** Fade-out sobre una referencia específica.
 *  `gen` evita que un fade-out viejo interfiera con el audio nuevo. */
function _fadeOut(audioRef, durationMs, gen) {
  const steps    = 20;
  const stepTime = durationMs / steps;
  const stepVol  = (audioRef.volume || VOLUME) / steps;

  const interval = setInterval(() => {
    // Si ya arrancó un nuevo ciclo de audio, cancelar este fade-out
    if (gen !== _stopGeneration) {
      clearInterval(interval);
      return;
    }
    audioRef.volume = Math.max(0, audioRef.volume - stepVol);
    if (audioRef.volume <= 0) {
      clearInterval(interval);
      audioRef.pause();
      audioRef.src = "";
    }
  }, stepTime);
}

// ============================================
// ESTILOS DEL PANEL + BOTÓN
// (movido a función que se llama al importar el módulo)
// ============================================

function _inyectarEstilosSonido() {
  if (document.getElementById("ambient-sound-styles")) return;

  const style = document.createElement("style");
  style.id = "ambient-sound-styles";
  style.textContent = `
    #ambient-sound-panel {
      position: fixed; inset: 0; z-index: 1500;
      display: flex; align-items: flex-end; justify-content: center;
    }
    .as-backdrop {
      position: absolute; inset: 0;
      background: rgba(47, 79, 69, 0.25);
      backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
      animation: as-fade-in 0.25s ease;
    }
    @keyframes as-fade-in { from { opacity: 0; } to { opacity: 1; } }
    .as-sheet {
      position: relative; width: 100%; max-width: 430px;
      background: linear-gradient(160deg, #eaf4ef 0%, #f6fbf8 100%);
      border-radius: 24px 24px 0 0; padding: 24px 20px 32px;
      transform: translateY(100%);
      transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
      box-shadow: 0 -8px 40px rgba(47, 79, 69, 0.15);
    }
    .as-sheet--visible { transform: translateY(0); }
    .as-header {
      display: flex; flex-direction: column; align-items: center;
      margin-bottom: 20px; position: relative;
    }
    .as-title { font-size: 1.15rem; font-weight: 800; color: #2f4f45; }
    .as-subtitle { font-size: 0.82rem; color: #8fb5a3; margin-top: 2px; }
    .as-close {
      position: absolute; top: 0; right: 0;
      background: rgba(183, 211, 198, 0.5); border: none;
      width: 36px; height: 36px; border-radius: 50%;
      font-size: 1rem; color: #4a6a5e; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      transition: background 0.2s;
    }
    .as-close:hover { background: rgba(183, 211, 198, 0.9); }
    .as-list { display: flex; flex-direction: column; gap: 8px; }
    .as-item {
      width: 100%; display: flex; align-items: center; gap: 14px;
      padding: 14px 16px; border: 2px solid transparent;
      border-radius: 16px; background: white; cursor: pointer;
      transition: all 0.2s ease; box-shadow: 0 2px 6px rgba(0,0,0,0.04);
    }
    .as-item:hover { border-color: #b7d3c6; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.07); }
    .as-item--active { border-color: #7db89e; background: #eaf4ef; }
    .as-icon { font-size: 1.6rem; flex-shrink: 0; line-height: 1; }
    .as-info { display: flex; flex-direction: column; gap: 2px; flex: 1; text-align: left; }
    .as-name { font-size: 0.95rem; font-weight: 700; color: #2f4f45; }
    .as-desc { font-size: 0.78rem; color: #8fb5a3; }
    .as-check { font-size: 1rem; font-weight: 800; color: #5a9e85; width: 20px; text-align: center; flex-shrink: 0; }
    .as-note { text-align: center; font-size: 0.78rem; color: #a8c8b8; margin-top: 16px; font-style: italic; }
    .btn-ambient-sound {
      display: flex; align-items: center; gap: 8px;
      width: 100%; max-width: 340px; padding: 12px 16px;
      border: 1.5px solid #b7d3c6; border-radius: 14px;
      background: rgba(255,255,255,0.7); color: #5a7a6e;
      font-size: 0.88rem; font-family: inherit; font-weight: 600;
      cursor: pointer; transition: all 0.2s ease; margin-bottom: 4px;
    }
    .btn-ambient-sound:hover { background: white; border-color: #7db89e; transform: translateY(-1px); }
    .btn-ambient-sound .bam-icon { font-size: 1rem; }
    .btn-ambient-sound .bam-label { flex: 1; text-align: left; }
    .btn-ambient-sound .bam-current {
      font-size: 0.78rem; opacity: 0.7;
      background: #d4ece4; padding: 3px 8px; border-radius: 20px;
    }
  `;
  document.head.appendChild(style);
}