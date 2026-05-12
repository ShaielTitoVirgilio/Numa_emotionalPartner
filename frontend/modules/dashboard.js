// modules/dashboard.js

let _cargado = false;

export async function initDashboard() {
  const contenedor = document.getElementById("view-dashboard");
  if (!contenedor) return;

  // Si ya cargó esta sesión, solo reanimar
  if (_cargado) {
    _animarEntrada(contenedor);
    return;
  }

  const numaUser = localStorage.getItem("numa_user");
  if (!numaUser) {
    contenedor.innerHTML = _htmlVacio();
    return;
  }

  const userId = JSON.parse(numaUser).user_id;
  contenedor.innerHTML = _htmlCargando();

  try {
    const res = await fetch(`/dashboard?user_id=${userId}`);
    if (!res.ok) throw new Error("Error al cargar datos");
    const data = await res.json();

    contenedor.innerHTML = _htmlDashboard(data);
    _animarEntrada(contenedor);
    _cargado = true;
  } catch (e) {
    contenedor.innerHTML = _htmlError();
  }
}

// ── Animación de entrada ──────────────────────────────────────────────────────

function _animarEntrada(contenedor) {
  const cards = contenedor.querySelectorAll(".db-card");
  cards.forEach((card, i) => {
    card.style.opacity = "0";
    card.style.transform = "translateY(18px)";
    setTimeout(() => {
      card.style.transition = "opacity 0.5s ease, transform 0.5s ease";
      card.style.opacity = "1";
      card.style.transform = "translateY(0)";
    }, 80 + i * 100);
  });
}

// ── HTML principal ────────────────────────────────────────────────────────────

function _htmlDashboard(data) {
  const { mood_semanal, dias_activos_semana, comparacion_semana, checkins, patrones, resumen } = data;

  return `
    <div class="db-scroll">
      <div class="db-header">
        <h2 class="db-titulo">Tu estado</h2>
        <p class="db-subtitulo">Últimos 30 días</p>
      </div>

      <!-- Resumen -->
      <div class="db-card db-resumen">
        <p class="db-resumen-texto">${resumen}</p>
      </div>

      <!-- Esta semana -->
      <div class="db-card">
        <p class="db-card-titulo">Esta semana</p>
        ${_htmlSemana(mood_semanal, dias_activos_semana, comparacion_semana)}
      </div>

      <!-- Check-ins -->
      <div class="db-card">
        <p class="db-card-titulo">¿Cómo llegaste cada día?</p>
        ${_htmlCheckins(checkins)}
      </div>

      <!-- Patrones -->
      <div class="db-card">
        <p class="db-card-titulo">Temas recurrentes</p>
        ${patrones.length > 0 ? `
        <div class="db-patrones">
          ${patrones.map(p => `
            <div class="db-patron-pill">
              <span class="db-patron-topic">${_labelPatron(p.topic)}</span>
              <span class="db-patron-count">${p.count}x</span>
            </div>
          `).join("")}
        </div>
        ${patrones[0]?.ultimo_contenido ? `
          <p class="db-patron-detalle">"${patrones[0].ultimo_contenido}"</p>
        ` : ""}
        ` : `
        <p class="db-empty">
          Numa todavía no detectó ningún patrón. A medida que hables más, vas a ver acá los temas que más aparecen en tus conversaciones.
        </p>
        `}
      </div>

    </div>
  `;
}

// ── Esta semana ───────────────────────────────────────────────────────────────

const MOOD_EMOJI_MAP = { "Bien": "🙂", "Regular": "😐", "Mal": "😔" };
const DIAS_LABEL = ["D", "L", "M", "M", "J", "V", "S"];

function _htmlSemana(moodSemanal, diasActivos, comparacion) {
  // Mood predominante de la semana
  const vals = moodSemanal.filter(d => d.mood !== null);
  let moodPredominante = null;
  if (vals.length > 0) {
    const conteo = {};
    vals.forEach(d => { conteo[d.mood] = (conteo[d.mood] || 0) + 1; });
    moodPredominante = Object.entries(conteo).sort((a, b) => b[1] - a[1])[0][0];
  }

  const emojiPred = moodPredominante ? MOOD_EMOJI_MAP[moodPredominante] || "😐" : null;
  const textoMood = moodPredominante
    ? `${emojiPred} Tu semana fue mayormente <strong>${moodPredominante.toLowerCase()}</strong>`
    : `Sin registros esta semana aún`;

  // Fila de 7 días
  const filaHtml = moodSemanal.map(d => {
    const fecha = new Date(d.fecha + "T12:00:00");
    const labelDia = DIAS_LABEL[fecha.getDay()];
    const emoji = d.mood ? MOOD_EMOJI_MAP[d.mood] || "😐" : null;
    return `
      <div class="db-sem-dia">
        <span class="db-sem-label">${labelDia}</span>
        <div class="db-sem-punto ${emoji ? "db-sem-con-dato" : ""}">
          ${emoji ? emoji : ""}
        </div>
      </div>`;
  }).join("");

  // Comparación con semana anterior
  const COMP_TEXTO = {
    muy_mejor:      "📈 Tu estado de ánimo fue muy superior al de la semana pasada",
    un_poco_mejor:  "📈 Tu estado de ánimo fue un poco mejor que la semana pasada",
    similar:        "➡️ Similar a la semana pasada",
    un_poco_peor:   "📉 Tu estado de ánimo fue un poco menor que la semana pasada",
    muy_peor:       "📉 Tu estado de ánimo fue bastante menor que la semana pasada",
  };
  const textoComp = comparacion ? COMP_TEXTO[comparacion] : null;

  return `
    <p class="db-sem-mood">${textoMood}</p>
    <div class="db-sem-fila">${filaHtml}</div>
    <p class="db-sem-activos">Estuviste presente <strong>${diasActivos} de 7 días</strong></p>
    ${textoComp ? `<p class="db-sem-comp">${textoComp}</p>` : ""}
  `;
}

// ── Check-ins grid ────────────────────────────────────────────────────────────

function _htmlCheckins(checkins) {
  if (checkins.length === 0) {
    return `<p class="db-empty">Todavía no hay check-ins. Aparecen después de tu primer mensaje del día.</p>`;
  }

  const mapa = {};
  checkins.forEach(c => { mapa[c.checkin_date] = c; });

  const hoy = new Date();
  const dias = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date(hoy);
    d.setDate(hoy.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    dias.push({ key, dayNum: d.getDate(), data: mapa[key] || null });
  }

  const puntos = dias.map(({ key, dayNum, data }) => {
    if (!data) {
      return `<div class="db-ci-dot db-ci-vacio" title="${key}"><span class="db-ci-daynum">${dayNum}</span></div>`;
    }
    const colorClass = `db-ci-v${data.mood_value}`;
    return `<div class="db-ci-dot ${colorClass}" title="${key}">${data.mood_emoji}</div>`;
  }).join("");

  return `<div class="db-ci-grid">${puntos}</div>`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _labelPatron(topic) {
  const MAP = {
    trabajo:    "💼 Trabajo",
    relaciones: "❤️ Relaciones",
    salud:      "🌿 Salud",
    identidad:  "🪞 Identidad",
    emocional:  "💙 Emocional",
  };
  return MAP[topic] || topic;
}

// ── Estados ───────────────────────────────────────────────────────────────────

function _htmlCargando() {
  return `
    <div class="db-scroll db-estado-centro">
      <div class="db-loader"></div>
      <p class="db-estado-texto">Cargando tu estado…</p>
    </div>
  `;
}

function _htmlVacio() {
  return `
    <div class="db-scroll db-estado-centro">
      <p class="db-estado-texto">Iniciá sesión para ver tu estado emocional.</p>
    </div>
  `;
}

function _htmlError() {
  return `
    <div class="db-scroll db-estado-centro">
      <p class="db-estado-texto">No se pudieron cargar los datos. Intentá de nuevo más tarde.</p>
    </div>
  `;
}
