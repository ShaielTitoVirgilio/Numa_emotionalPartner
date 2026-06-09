// modules/profile.js

const PRIVACY_URL = 'https://shaieltitovirgilio.github.io/landing-numa/privacy-policy.html';
const TERMS_URL   = 'https://shaieltitovirgilio.github.io/landing-numa/terms.html';

const MOODS = [
  { value: 1, emoji: '😔', label: 'Mal' },
  { value: 2, emoji: '😐', label: 'Regular' },
  { value: 3, emoji: '🙂', label: 'Bien' },
  { value: 4, emoji: '😄', label: 'Genial' },
];

let _cargado = false;

export async function initProfile() {
  const contenedor = document.getElementById('view-profile');
  if (!contenedor) return;

  const numaUser = localStorage.getItem('numa_user');
  if (!numaUser) return;

  const { user_id, email } = JSON.parse(numaUser);

  contenedor.innerHTML = _htmlCargando();

  try {
    const [profileRes, checkinRes] = await Promise.all([
      fetch(`/profile/${user_id}`),
      fetch(`/checkin/today?user_id=${user_id}`),
    ]);

    const profile  = profileRes.ok ? await profileRes.json() : {};
    const checkinData = checkinRes.ok ? await checkinRes.json() : {};

    const nombre   = profile.nombre || '';
    const checkin  = checkinData.checkin || null;

    contenedor.innerHTML = _htmlPerfil(nombre, email, checkin, user_id);
    _bindEvents(contenedor, user_id);
    _cargado = true;
  } catch (e) {
    contenedor.innerHTML = _htmlError();
  }
}

// ── Render ────────────────────────────────────────────────────────────────────

function _htmlPerfil(nombre, email, checkin, userId) {
  const inicial = (nombre || email || '?')[0].toUpperCase();

  return `
    <div class="prf-scroll">

      <!-- Header avatar -->
      <div class="prf-header">
        <div class="prf-avatar">${inicial}</div>
        ${nombre ? `<p class="prf-nombre">${nombre}</p>` : ''}
        <p class="prf-email">${email || ''}</p>
      </div>

      <!-- Check-in de hoy -->
      <div class="prf-card">
        <p class="prf-card-titulo">¿Cómo estás hoy?</p>
        <div id="prf-checkin-content">
          ${_htmlCheckinContent(checkin)}
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
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, mood_value: moodValue }),
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
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, reason }),
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
