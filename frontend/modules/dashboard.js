// modules/dashboard.js

import { authHeaders } from './utils.js';

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
    const res = await fetch('/dashboard', { headers: authHeaders() });
    if (!res.ok) throw new Error("Error al cargar datos");
    const data = await res.json();

    contenedor.innerHTML = _htmlDashboard(data);
    contenedor.querySelector('#db-btn-export')?.addEventListener('click', () => _exportarEstado(data));
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
  const { mood_semanal, dias_activos_semana, comparacion_semana, checkins, patrones, resumen, insight_ia, racha_checkins } = data;

  // Sin ningún dato aún → pantalla vacía con una sola frase
  const hasData = insight_ia !== null || patrones.length > 0 || checkins.length > 0;

  if (!hasData) {
    return `
      <div class="db-scroll">
        <div class="db-header">
          <h2 class="db-titulo">Tu estado</h2>
          <p class="db-subtitulo">Últimos 30 días</p>
        </div>
        <p class="db-empty db-empty-inicio">
          Cuando chatees con Numa y registres tu ánimo, acá vas a ver tu progreso y lo que Numa nota sobre vos.
        </p>
      </div>
    `;
  }

  return `
    <div class="db-scroll">
      <div class="db-header">
        <h2 class="db-titulo">Tu estado</h2>
        <p class="db-subtitulo">Últimos 30 días</p>
      </div>

      ${insight_ia ? _htmlInsightIA(insight_ia) : _htmlInsightPlaceholder()}

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
        ${racha_checkins >= 2 ? `
        <p class="db-racha">${racha_checkins} días seguidos registrando cómo llegás</p>
        ` : ""}
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

      <!-- Exportar -->
      <button class="db-btn-export" id="db-btn-export">Compartir mi estado</button>
      <p class="db-export-hint">Por ejemplo, para llevárselo a tu terapeuta.</p>

    </div>
  `;
}

// ── Exportar / compartir ──────────────────────────────────────────────────────

function _textoExport(data) {
  const lineas = [
    "Mi estado — Numa 🐼",
    `Generado: ${new Date().toLocaleDateString("es-AR")}`,
    "",
    data.resumen || "",
  ];
  if (data.insight_ia?.texto) {
    lineas.push("", `Lo que Numa nota: "${data.insight_ia.texto}"`);
  }
  if (data.patrones?.length) {
    lineas.push("", "Temas recurrentes del mes:");
    data.patrones.forEach(p => lineas.push(`  • ${_labelPatron(p.topic)} (${p.count} veces)`));
  }
  if (data.checkins?.length) {
    const buenos = data.checkins.filter(c => c.mood_value >= 3).length;
    lineas.push("", `Check-ins del mes: ${data.checkins.length} (${buenos} días bien)`);
  }
  if (data.racha_checkins >= 2) {
    lineas.push(`Racha actual: ${data.racha_checkins} días seguidos registrando el ánimo`);
  }
  return lineas.join("\n");
}

async function _exportarEstado(data) {
  const texto = _textoExport(data);
  if (navigator.share) {
    try {
      await navigator.share({ title: "Mi estado — Numa", text: texto });
      return;
    } catch (e) {
      if (e.name === "AbortError") return; // canceló el share
    }
  }
  // Fallback: descargar como .txt
  const blob = new Blob([texto], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "mi-estado-numa.txt";
  a.click();
  URL.revokeObjectURL(url);
}

// ── Insight IA ────────────────────────────────────────────────────────────────

function _htmlInsightPlaceholder() {
  return `
    <div class="db-card db-insight db-insight-placeholder">
      <p class="db-insight-placeholder-texto">
        Cuando chatees con Numa y registres tu ánimo, acá vas a ver tu progreso y lo que Numa nota sobre vos.
      </p>
    </div>
  `;
}

const INSIGHT_CONFIG = {
  fortaleza: { bg: "#eef7f1", color: "#5a9e7a", label: "Fortaleza" },
  patron:    { bg: "#eef0fa", color: "#6b7fc4", label: "Patrón"    },
  tendencia: { bg: "#faf3ea", color: "#c47a3a", label: "Tendencia" },
  reflexion: { bg: "#eaf5f8", color: "#3a9eb5", label: "Reflexión" },
};

function _htmlInsightIA(insight) {
  const cfg = INSIGHT_CONFIG[insight.tipo] || INSIGHT_CONFIG.reflexion;
  return `
    <div class="db-card db-insight" style="background:${cfg.bg}; border-color:${cfg.color}40;">
      <span class="db-insight-label" style="color:${cfg.color}">${cfg.label.toUpperCase()}</span>
      <p class="db-insight-texto">"${insight.texto}"</p>
      <p class="db-insight-autor" style="color:${cfg.color}">— Numa</p>
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
    muy_mejor:      "Tu estado de ánimo fue muy superior al de la semana pasada",
    un_poco_mejor:  "Tu estado de ánimo fue un poco mejor que la semana pasada",
    similar:        "Similar a la semana pasada",
    un_poco_peor:   "Tu estado de ánimo fue un poco menor que la semana pasada",
    muy_peor:       "Tu estado de ánimo fue bastante menor que la semana pasada",
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
    trabajo:    "Trabajo",
    relaciones: "Relaciones",
    salud:      "Salud",
    identidad:  "Identidad",
    emocional:  "Emocional",
  };
  return MAP[topic] || (topic.charAt(0).toUpperCase() + topic.slice(1));
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
