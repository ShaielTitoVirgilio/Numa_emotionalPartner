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
    _dibujarGrafica(data.mood_semanal);
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
  const { mood_semanal, checkins, patrones, resumen } = data;

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

      <!-- Mood semanal -->
      <div class="db-card">
        <p class="db-card-titulo">Esta semana</p>
        <div class="db-grafica-wrap">
          <canvas id="db-grafica" width="320" height="110"></canvas>
          <div class="db-grafica-labels" id="db-grafica-labels"></div>
        </div>
        <div class="db-mood-leyenda">
          <span>😔 Mal</span><span>😐 Regular</span><span>🙂 Bien</span>
        </div>
      </div>

      <!-- Check-ins -->
      <div class="db-card">
        <p class="db-card-titulo">¿Cómo llegaste cada día?</p>
        ${_htmlCheckins(checkins)}
      </div>

      <!-- Patrones -->
      ${patrones.length > 0 ? `
      <div class="db-card">
        <p class="db-card-titulo">Temas recurrentes</p>
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
      </div>
      ` : ""}

    </div>
  `;
}

// ── Check-ins grid ────────────────────────────────────────────────────────────

function _htmlCheckins(checkins) {
  if (checkins.length === 0) {
    return `<p class="db-empty">Todavía no hay check-ins. Aparecen después de tu primer mensaje del día.</p>`;
  }

  // Mapa fecha → datos
  const mapa = {};
  checkins.forEach(c => { mapa[c.checkin_date] = c; });

  // Últimos 30 días
  const hoy = new Date();
  const dias = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date(hoy);
    d.setDate(hoy.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    dias.push({ key, data: mapa[key] || null });
  }

  const puntos = dias.map(({ key, data }) => {
    if (!data) {
      return `<div class="db-ci-dot db-ci-vacio" title="${key}"></div>`;
    }
    const colorClass = `db-ci-v${data.mood_value}`;
    return `<div class="db-ci-dot ${colorClass}" title="${key}">${data.mood_emoji}</div>`;
  }).join("");

  return `<div class="db-ci-grid">${puntos}</div>`;
}

// ── Gráfica SVG con canvas ────────────────────────────────────────────────────

function _dibujarGrafica(moodSemanal) {
  const canvas = document.getElementById("db-grafica");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  const W = canvas.width;
  const H = canvas.height;
  const PAD_X = 20;
  const PAD_TOP = 14;
  const PAD_BOT = 20;

  // Colores
  const COLOR_LINEA = "#7db89e";
  const COLOR_AREA  = "rgba(125, 184, 158, 0.15)";
  const COLOR_PUNTO = "#2f4f45";
  const COLOR_NULL  = "#e0ebe7";
  const COLOR_TEXT  = "#8fb5a3";

  const dias = moodSemanal;
  const n = dias.length;
  const stepX = (W - PAD_X * 2) / (n - 1);

  function xOf(i) { return PAD_X + i * stepX; }
  function yOf(v) {
    if (v === null) return null;
    // valor 1-3, mapear a altura
    const rango = H - PAD_TOP - PAD_BOT;
    return PAD_TOP + rango - ((v - 1) / 2) * rango;
  }

  ctx.clearRect(0, 0, W, H);

  // Filtrar puntos con valor
  const puntos = dias.map((d, i) => ({ x: xOf(i), y: yOf(d.value), v: d.value }));

  // Área bajo la curva
  const conValor = puntos.filter(p => p.v !== null);
  if (conValor.length >= 2) {
    ctx.beginPath();
    ctx.moveTo(conValor[0].x, H - PAD_BOT);
    ctx.lineTo(conValor[0].x, conValor[0].y);
    for (let i = 1; i < conValor.length; i++) {
      const prev = conValor[i - 1];
      const curr = conValor[i];
      const cx = (prev.x + curr.x) / 2;
      ctx.bezierCurveTo(cx, prev.y, cx, curr.y, curr.x, curr.y);
    }
    ctx.lineTo(conValor[conValor.length - 1].x, H - PAD_BOT);
    ctx.closePath();
    ctx.fillStyle = COLOR_AREA;
    ctx.fill();

    // Línea
    ctx.beginPath();
    ctx.moveTo(conValor[0].x, conValor[0].y);
    for (let i = 1; i < conValor.length; i++) {
      const prev = conValor[i - 1];
      const curr = conValor[i];
      const cx = (prev.x + curr.x) / 2;
      ctx.bezierCurveTo(cx, prev.y, cx, curr.y, curr.x, curr.y);
    }
    ctx.strokeStyle = COLOR_LINEA;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.stroke();
  }

  // Puntos y labels de días
  const DIAS_LABEL = ["D", "L", "M", "M", "J", "V", "S"];
  dias.forEach((d, i) => {
    const x = xOf(i);
    const y = yOf(d.value);
    const fecha = new Date(d.fecha + "T12:00:00");
    const label = DIAS_LABEL[fecha.getDay()];

    // Label del día
    ctx.fillStyle = COLOR_TEXT;
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(label, x, H - 2);

    if (y !== null) {
      // Punto
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fillStyle = COLOR_PUNTO;
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.stroke();
    } else {
      // Punto gris sin dato
      ctx.beginPath();
      ctx.arc(x, H - PAD_BOT - 14, 3, 0, Math.PI * 2);
      ctx.fillStyle = COLOR_NULL;
      ctx.fill();
    }
  });
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
