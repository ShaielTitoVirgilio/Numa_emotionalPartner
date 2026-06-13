// modules/profile.js

import { authHeaders } from './utils.js';

const PRIVACY_URL = 'https://shaieltitovirgilio.github.io/landing-numa/privacy-policy.html';
const TERMS_URL   = 'https://shaieltitovirgilio.github.io/landing-numa/terms.html';

const MOODS = [
  { value: 1, emoji: '😔', label: 'Mal' },
  { value: 2, emoji: '😐', label: 'Regular' },
  { value: 3, emoji: '🙂', label: 'Bien' },
  { value: 4, emoji: '😄', label: 'Genial' },
];

let _cargado = false;

// Estado local de la sección de memorias: lista + si está expandida.
// Por defecto se muestran solo las 2 más recientes con "Mostrar más".
let _memorias = [];
let _memoriasExpandido = false;
const MEMORIAS_VISIBLES = 2;

export async function initProfile() {
  const contenedor = document.getElementById('view-profile');
  if (!contenedor) return;

  const numaUser = localStorage.getItem('numa_user');
  if (!numaUser) return;

  const { user_id, email } = JSON.parse(numaUser);

  contenedor.innerHTML = _htmlCargando();

  try {
    const [profileRes, checkinRes, memoriasRes] = await Promise.all([
      fetch(`/profile/${user_id}`, { headers: authHeaders() }),
      fetch('/checkin/today', { headers: authHeaders() }),
      fetch('/memories', { headers: authHeaders() }),
    ]);

    const profile  = profileRes.ok ? await profileRes.json() : {};
    const checkinData = checkinRes.ok ? await checkinRes.json() : {};
    _memorias = memoriasRes.ok ? (await memoriasRes.json()).memories || [] : [];
    _memoriasExpandido = false;

    const nombre   = profile.nombre || '';
    const checkin  = checkinData.checkin || null;

    contenedor.innerHTML = _htmlPerfil(nombre, email, checkin, user_id);
    _bindEvents(contenedor, user_id);
    _renderMemorias();
    _cargado = true;
  } catch (e) {
    contenedor.innerHTML = _htmlError();
  }
}

// ── Render ────────────────────────────────────────────────────────────────────

function _escapar(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _htmlPerfil(nombre, email, checkin, userId) {
  const inicial = (nombre || email || '?')[0].toUpperCase();

  return `
    <div class="prf-scroll">

      <!-- Header avatar -->
      <div class="prf-header">
        <div class="prf-avatar">${inicial}</div>
        ${nombre ? `<p class="prf-nombre">${_escapar(nombre)}</p>` : ''}
        <p class="prf-email">${_escapar(email || '')}</p>
      </div>

      <!-- Check-in de hoy -->
      <div class="prf-card">
        <p class="prf-card-titulo">¿Cómo estás hoy?</p>
        <div id="prf-checkin-content">
          ${_htmlCheckinContent(checkin)}
        </div>
      </div>

      <!-- Lo que Numa recuerda -->
      <div class="prf-card" id="prf-memorias-card">
        <p class="prf-card-titulo">🧠 Lo que Numa recuerda de vos</p>
        <p class="prf-card-subtexto">Podés borrar lo que no quieras que recuerde.</p>
        <div id="prf-memorias-list"></div>
      </div>

      <!-- Tema -->
      <div class="prf-card">
        <p class="prf-card-titulo">Tema</p>
        <div class="prf-tema-row" role="group" aria-label="Tema de la app">
          <button class="prf-tema-btn" data-tema="auto"   aria-label="Tema automático">📱 Auto</button>
          <button class="prf-tema-btn" data-tema="claro"  aria-label="Tema claro">☀️ Claro</button>
          <button class="prf-tema-btn" data-tema="oscuro" aria-label="Tema oscuro">🌙 Oscuro</button>
        </div>
      </div>

      <!-- Tamaño de texto -->
      <div class="prf-card">
        <p class="prf-card-titulo">Tamaño de texto</p>
        <div class="prf-font-row" role="group" aria-label="Tamaño de texto">
          <button class="prf-font-btn" data-size="small"  aria-label="Texto chico">A</button>
          <button class="prf-font-btn" data-size="normal" aria-label="Texto normal">A</button>
          <button class="prf-font-btn" data-size="large"  aria-label="Texto grande">A</button>
        </div>
      </div>

      <!-- Disclaimer -->
      <div class="prf-card prf-disclaimer">
        <p class="prf-card-titulo">Sobre Numa</p>
        <p class="prf-disclaimer-texto">
          Numa es un compañero de bienestar emocional.
          <strong>No reemplaza la atención de un profesional de salud mental.</strong>
          Si estás pasando un momento muy difícil, buscá ayuda profesional.
        </p>
      </div>

      <!-- Links legales -->
      <div class="prf-links">
        <a href="${PRIVACY_URL}" target="_blank" rel="noopener" class="prf-link">Política de privacidad</a>
        <span class="prf-link-sep">·</span>
        <a href="${TERMS_URL}" target="_blank" rel="noopener" class="prf-link">Términos y condiciones</a>
      </div>

      <!-- Cerrar sesión -->
      <button class="prf-btn-logout" id="prf-btn-logout">Cerrar sesión</button>

      <!-- Eliminar cuenta -->
      <button class="prf-btn-delete" id="prf-btn-delete">Eliminar mi cuenta</button>

    </div>
  `;
}

function _renderMemorias() {
  const list = document.getElementById('prf-memorias-list');
  if (!list) return;

  if (!_memorias.length) {
    list.innerHTML = `<p class="prf-memoria-vacio">Todavía no hay nada guardado. A medida que charlen, Numa va a recordar lo importante.</p>`;
    return;
  }

  const visibles = _memoriasExpandido ? _memorias : _memorias.slice(0, MEMORIAS_VISIBLES);
  const ocultas = _memorias.length - MEMORIAS_VISIBLES;

  let html = visibles.map(m => `
    <div class="prf-memoria-item" data-id="${_escapar(m.id)}">
      <span class="prf-memoria-texto">${_escapar(m.content)}</span>
      <button class="prf-memoria-borrar" data-id="${_escapar(m.id)}" aria-label="Borrar esta memoria">✕</button>
    </div>
  `).join('');

  if (ocultas > 0) {
    html += _memoriasExpandido
      ? `<button class="prf-memorias-toggle" id="prf-memorias-toggle">Mostrar menos ▲</button>`
      : `<button class="prf-memorias-toggle" id="prf-memorias-toggle">Mostrar más (${ocultas}) ▼</button>`;
  }

  list.innerHTML = html;

  list.querySelectorAll('.prf-memoria-borrar').forEach(btn => {
    btn.addEventListener('click', () => _borrarMemoria(btn.dataset.id));
  });

  const toggle = list.querySelector('#prf-memorias-toggle');
  if (toggle) {
    toggle.addEventListener('click', () => {
      _memoriasExpandido = !_memoriasExpandido;
      _renderMemorias();
      if (!_memoriasExpandido) {
        // Al colapsar desde abajo de una lista larga, volver a la tarjeta
        document.getElementById('prf-memorias-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }
}

function _htmlCheckinContent(checkin) {
  if (checkin) {
    return `
      <div class="prf-checkin-done">
        <span class="prf-checkin-emoji">${checkin.mood_emoji}</span>
        <p class="prf-checkin-done-texto">Ya registraste tu día. Volvé mañana.</p>
      </div>
    `;
  }
  return `
    <div class="prf-mood-row">
      ${MOODS.map(m => `
        <button class="prf-mood-btn" data-value="${m.value}" aria-label="${m.label}">
          <span class="prf-mood-emoji">${m.emoji}</span>
          <span class="prf-mood-label">${m.label}</span>
        </button>
      `).join('')}
    </div>
  `;
}

// ── Event binding ─────────────────────────────────────────────────────────────

function _bindEvents(contenedor, userId) {
  // Check-in buttons
  contenedor.querySelectorAll('.prf-mood-btn').forEach(btn => {
    btn.addEventListener('click', () => _guardarCheckin(userId, parseInt(btn.dataset.value)));
  });

  // Logout
  const btnLogout = contenedor.querySelector('#prf-btn-logout');
  if (btnLogout) {
    btnLogout.addEventListener('click', () => {
      if (window.logout) window.logout();
    });
  }

  // Delete account
  const btnDelete = contenedor.querySelector('#prf-btn-delete');
  if (btnDelete) {
    btnDelete.addEventListener('click', () => _mostrarModalEliminar(userId));
  }

  // Borrar memorias
  contenedor.querySelectorAll('.prf-memoria-borrar').forEach(btn => {
    btn.addEventListener('click', () => _borrarMemoria(btn.dataset.id));
  });

  // Tamaño de texto
  const actual = localStorage.getItem('numa_font_size') || 'normal';
  contenedor.querySelectorAll('.prf-font-btn').forEach(btn => {
    if (btn.dataset.size === actual) btn.classList.add('activo');
    btn.addEventListener('click', () => {
      aplicarTamanoFuente(btn.dataset.size);
      contenedor.querySelectorAll('.prf-font-btn').forEach(b => b.classList.toggle('activo', b === btn));
    });
  });

  // Tema (auto / claro / oscuro) — por defecto "claro"
  const temaActual = localStorage.getItem('numa_tema') || 'claro';
  contenedor.querySelectorAll('.prf-tema-btn').forEach(btn => {
    if (btn.dataset.tema === temaActual) btn.classList.add('activo');
    btn.addEventListener('click', () => {
      aplicarTema(btn.dataset.tema);
      contenedor.querySelectorAll('.prf-tema-btn').forEach(b => b.classList.toggle('activo', b === btn));
    });
  });
}

// ── Memorias ──────────────────────────────────────────────────────────────────

async function _borrarMemoria(id) {
  try {
    const res = await fetch(`/memories/${id}`, { method: 'DELETE', headers: authHeaders() });
    if (!res.ok) throw new Error('No se pudo borrar');
    // Actualizar el estado local y re-renderizar: así las "últimas 2" visibles
    // y el contador de "Mostrar más" quedan siempre correctos.
    _memorias = _memorias.filter(m => String(m.id) !== String(id));
    _renderMemorias();
    _cargado = false; // recargar la próxima vez que entre al perfil
  } catch (e) {
    console.warn('No se pudo borrar la memoria:', e);
  }
}

// ── Tamaño de fuente ──────────────────────────────────────────────────────────

const FONT_SIZES = { small: '14px', normal: '16px', large: '18.5px' };

export function aplicarTamanoFuente(size) {
  const px = FONT_SIZES[size] || FONT_SIZES.normal;
  document.documentElement.style.fontSize = px;
  localStorage.setItem('numa_font_size', size);
}

export function aplicarTamanoFuenteGuardado() {
  const guardado = localStorage.getItem('numa_font_size');
  if (guardado && guardado !== 'normal') aplicarTamanoFuente(guardado);
}

// ── Tema (claro / oscuro / automático) ───────────────────────────────────────
// El modo oscuro se aplica con la clase .tema-oscuro en <html>.
// "auto" sigue la preferencia del sistema y reacciona si cambia en vivo.

const _mediaOscuro = window.matchMedia('(prefers-color-scheme: dark)');

// SVG sol / luna en gris claro para el botón del chat
const _ICONO_SOL = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><line x1="12" y1="2" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="22"/><line x1="4.2" y1="4.2" x2="5.6" y2="5.6"/><line x1="18.4" y1="18.4" x2="19.8" y2="19.8"/><line x1="2" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="22" y2="12"/><line x1="4.2" y1="19.8" x2="5.6" y2="18.4"/><line x1="18.4" y1="5.6" x2="19.8" y2="4.2"/></svg>';
const _ICONO_LUNA = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';

function _refrescarTema() {
  const tema = localStorage.getItem('numa_tema') || 'claro';
  const oscuro = tema === 'oscuro' || (tema === 'auto' && _mediaOscuro.matches);
  document.documentElement.classList.toggle('tema-oscuro', oscuro);
  _actualizarBotonTemaChat(oscuro);
}

// Refleja el estado actual en el botón del chat: sol = claro, luna = oscuro
function _actualizarBotonTemaChat(oscuro) {
  const btn = document.getElementById('chat-theme-toggle');
  if (!btn) return;
  btn.innerHTML = oscuro ? _ICONO_LUNA : _ICONO_SOL;
  btn.setAttribute('aria-label', oscuro ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro');
}

_mediaOscuro.addEventListener?.('change', _refrescarTema);

export function aplicarTema(tema) {
  localStorage.setItem('numa_tema', tema);
  _refrescarTema();
}

export function aplicarTemaGuardado() {
  _refrescarTema();
}

// Alterna entre claro y oscuro desde el botón del chat
export function alternarTemaChat() {
  const oscuroActual = document.documentElement.classList.contains('tema-oscuro');
  aplicarTema(oscuroActual ? 'claro' : 'oscuro');
}

// ── Check-in ──────────────────────────────────────────────────────────────────

async function _guardarCheckin(userId, moodValue) {
  const content = document.getElementById('prf-checkin-content');
  if (!content) return;

  // Feedback visual inmediato
  content.querySelectorAll('.prf-mood-btn').forEach(b => b.disabled = true);
  const seleccionado = content.querySelector(`[data-value="${moodValue}"]`);
  if (seleccionado) seleccionado.classList.add('seleccionado');

  try {
    const res = await fetch('/checkin', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ mood_value: moodValue }),
    });
    const data = res.ok ? await res.json() : {};
    const emoji = data.mood_emoji || MOODS.find(m => m.value === moodValue)?.emoji || '🙂';

    setTimeout(() => {
      if (content) {
        content.innerHTML = `
          <div class="prf-checkin-done">
            <span class="prf-checkin-emoji">${emoji}</span>
            <p class="prf-checkin-done-texto">Ya registraste tu día. Volvé mañana.</p>
          </div>
        `;
      }
    }, 500);
  } catch (e) {
    console.warn('No se pudo guardar el check-in:', e);
  }
}

// ── Modal eliminar cuenta ─────────────────────────────────────────────────────

function _mostrarModalEliminar(userId) {
  if (document.getElementById('modal-eliminar')) return;

  const modal = document.createElement('div');
  modal.id = 'modal-eliminar';
  modal.className = 'prf-modal-overlay';
  modal.innerHTML = `
    <div class="prf-modal">
      <h3 class="prf-modal-titulo">¿Te vas?</h3>
      <p class="prf-modal-subtitulo">Si querés, contanos por qué — nos ayuda a mejorar.</p>
      <textarea
        id="prf-delete-reason"
        class="prf-modal-textarea"
        placeholder="Motivo (opcional)"
        maxlength="300"
      ></textarea>
      <div class="prf-modal-warning">
        ⚠️ Se eliminarán tu cuenta y todos tus datos de forma permanente.
      </div>
      <div class="prf-modal-btns">
        <button class="prf-modal-btn-cancel" id="prf-cancel-delete">Mantengo la cuenta</button>
        <button class="prf-modal-btn-confirm" id="prf-confirm-delete">Eliminar cuenta</button>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
  requestAnimationFrame(() => modal.classList.add('visible'));

  modal.querySelector('#prf-cancel-delete').addEventListener('click', () => _cerrarModal(modal));
  modal.querySelector('#prf-confirm-delete').addEventListener('click', () => _eliminarCuenta(userId, modal));
  modal.addEventListener('click', e => { if (e.target === modal) _cerrarModal(modal); });
}

function _cerrarModal(modal) {
  modal.classList.remove('visible');
  modal.addEventListener('transitionend', () => modal.remove(), { once: true });
}

async function _eliminarCuenta(userId, modal) {
  const btn = modal.querySelector('#prf-confirm-delete');
  const reason = modal.querySelector('#prf-delete-reason')?.value?.trim() || '';

  btn.disabled = true;
  btn.textContent = 'Eliminando…';

  try {
    const res = await fetch('/account/delete', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ reason }),
    });

    if (!res.ok) throw new Error('Error al eliminar');

    localStorage.removeItem('numa_user');
    window.location.reload();
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Eliminar cuenta';
    const warning = modal.querySelector('.prf-modal-warning');
    if (warning) warning.textContent = '❌ No se pudo eliminar la cuenta. Intentá de nuevo.';
  }
}

// ── Estados ───────────────────────────────────────────────────────────────────

function _htmlCargando() {
  return `<div class="prf-estado-centro"><div class="db-loader"></div></div>`;
}

function _htmlError() {
  return `<div class="prf-estado-centro"><p class="prf-estado-texto">No se pudo cargar el perfil.</p></div>`;
}
