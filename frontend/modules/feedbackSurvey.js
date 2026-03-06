// frontend/modules/feedbackSurvey.js
let _onSubmit = null, _onSkip = null;

export function mostrarSurvey(onSubmit, onSkip) {
  _onSubmit = onSubmit; _onSkip = onSkip;

  // Contenedor
  const panel = document.createElement('div');
  panel.id = 'survey-modal';
  panel.style.cssText = `
    position:fixed; inset:0; z-index:3000; display:flex; 
    align-items:center; justify-content:center; 
    background:rgba(0,0,0,.25); padding:16px;
  `;

  // Card
  const card = document.createElement('div');
  card.style.cssText = `
    width:100%; max-width:420px; background:#fff; border-radius:16px; 
    box-shadow:0 10px 30px rgba(0,0,0,.12); padding:20px; 
    font-family:system-ui, -apple-system, Segoe UI, Roboto;
  `;
  card.innerHTML = `
    <h3 style="margin:0 0 12px; color:#2f4f45;">Antes de irte, ¿nos contás?</h3>
    <p style="margin:0 0 12px; color:#6b8e7d; font-size:.95rem;">
      Son 5 preguntas rápidas. Nos ayuda a mejorar.
    </p>

    <label style="display:block; margin:14px 0 6px; font-weight:600;">1) ¿Qué tan probable es que recomiendes Numa?</label>
    <div id="nps" style="display:flex; gap:6px; flex-wrap:wrap;"></div>

    <label style="display:block; margin:14px 0 6px; font-weight:600;">2) ¿Te resultó útil hoy?</label>
    <select id="utilidad" style="width:100%; padding:10px; border:1px solid #d4e5df; border-radius:10px;">
      <option value="">Elegí una opción</option>
      <option>Mucho</option>
      <option>Un poco</option>
      <option>Nada</option>
    </select>

    <label style="display:block; margin:14px 0 6px; font-weight:600;">3) Opinión general</label>
    <textarea id="opinion" rows="3" style="width:100%; padding:10px; border:1px solid #d4e5df; border-radius:10px;"></textarea>

    <label style="display:block; margin:14px 0 6px; font-weight:600;">4) ¿Qué funciones te gustaría que agreguemos?</label>
    <textarea id="features" rows="3" style="width:100%; padding:10px; border:1px solid #d4e5df; border-radius:10px;"></textarea>

    <label style="display:block; margin:14px 0 6px; font-weight:600;">5) ¿Qué no usarías o qué te falla?</label>
    <textarea id="fallas" rows="3" style="width:100%; padding:10px; border:1px solid #d4e5df; border-radius:10px;"></textarea>

    <div style="display:flex; gap:8px; margin-top:16px;">
      <button id="survey-skip" style="flex:1; padding:12px; border-radius:12px; border:1px solid #d4e5df; background:#fff; color:#4a6a5e; cursor:pointer;">
        Omitir
      </button>
      <button id="survey-send" style="flex:1; padding:12px; border:none; border-radius:12px; background:#b7d3c6; color:#2f4f45; font-weight:700; cursor:pointer;">
        Enviar
      </button>
    </div>
  `;

  // Construir escala NPS 0..10
  const nps = card.querySelector('#nps');
  for (let i = 0; i <= 10; i++) {
    const b = document.createElement('button');
    b.textContent = i;
    b.style.cssText = `
      width:34px; height:34px; border-radius:8px; border:1px solid #d4e5df; background:#fff; 
      cursor:pointer; color:#2f4f45; font-weight:600;
    `;
    b.onclick = () => {
      [...nps.children].forEach(x => x.style.background = '#fff');
      b.style.background = '#eaf4ef';
      nps.dataset.value = String(i);
    };
    nps.appendChild(b);
  }

  panel.appendChild(card);
  document.body.appendChild(panel);

  // Bind
  card.querySelector('#survey-skip').onclick = () => {
    if (_onSkip) _onSkip();
    cerrarSurvey();
  };
  card.querySelector('#survey-send').onclick = () => {
    const npsVal = nps.dataset.value ?? null;
    const utilidad = card.querySelector('#utilidad').value.trim();
    const opinion  = card.querySelector('#opinion').value.trim();
    const features = card.querySelector('#features').value.trim();
    const fallas   = card.querySelector('#fallas').value.trim();

    if (npsVal === null) {
      alert('Elegí un valor de la pregunta 1 (0 a 10).');
      return;
    }

    const payload = {
      nps: Number(npsVal),
      utilidad,
      opinion,
      features,
      fallas,
    };
    if (_onSubmit) _onSubmit(payload);
    cerrarSurvey();
  };
}

export function cerrarSurvey() {
  const el = document.getElementById('survey-modal');
  if (el) el.remove();
}