// modules/menuEjercicios.js
import { CATALOGO_EJERCICIOS } from '../ejerciciosData.js';
import { iniciarEjercicio } from './utils.js';
import { mostrarSelectorSonido, getSonidoGuardado, SONIDOS_AMBIENTE } from './ambientSound.js';

// Los estilos estructurales viven en styles.css (.menu-cat-btn, .ej-card, etc.);
// inline solo quedan los colores dinámicos por categoría/pack.

// ============================================
// MENÚ PRINCIPAL DE EJERCICIOS
// ============================================

export function irAEjercicios() {
    const menu = document.getElementById("ejercicios-menu");
    const lista = document.getElementById("lista-categorias");

    if (!menu || !lista) {
        return console.error("Faltan elementos del menú en HTML");
    }

    lista.innerHTML = "";

    // ── Botón de sonido de fondo ──────────────────────
    const sonidoActualId = getSonidoGuardado();
    const sonidoActual = SONIDOS_AMBIENTE.find(s => s.id === sonidoActualId) || SONIDOS_AMBIENTE[0];

    const btnSonido = document.createElement("button");
    btnSonido.className = "btn-ambient-sound";
    btnSonido.innerHTML = `
        <span class="bam-label">Sonido de fondo</span>
        <span class="bam-current" id="bam-current-label">${sonidoActual.label}</span>
    `;
    btnSonido.onclick = () => mostrarSelectorSonido();
    lista.appendChild(btnSonido);

    // Escuchar cambios de sonido para actualizar el label en tiempo real
    const _onSoundChange = (e) => {
        const label = document.getElementById("bam-current-label");
        if (!label) return;
        const s = SONIDOS_AMBIENTE.find(s => s.id === e.detail.id);
        if (s) label.textContent = s.label;
    };
    window.addEventListener("numa:soundChanged", _onSoundChange);

    // Limpiar el listener cuando se cierre el menú
    menu.addEventListener("transitionend", () => {
        if (menu.classList.contains("hidden")) {
            window.removeEventListener("numa:soundChanged", _onSoundChange);
        }
    }, { once: true });

    // Separador visual
    const sep = document.createElement("div");
    sep.className = "menu-sep";
    lista.appendChild(sep);

    // ── Categorías ──────────────────────────────────
    const categorias = [
        {
            key: "respiracion", label: "Respiración",
            desc: "Calma el sistema nervioso",
            badge: `${CATALOGO_EJERCICIOS.respiracion.length} ejercicios · desde 1 min`,
            iconBg: "rgba(125,184,158,0.55)"
        },
        {
            key: "meditacion", label: "Meditación",
            desc: "Claridad y pausa mental",
            badge: `${CATALOGO_EJERCICIOS.meditacion.length} ejercicios · 1-3 min`,
            iconBg: "rgba(107,142,197,0.55)"
        },
        {
            key: "yoga", label: "Cuerpo y Movimiento",
            desc: "Soltar tensión física",
            badge: `${CATALOGO_EJERCICIOS.yoga.length} ejercicios · 3-5 min`,
            iconBg: "rgba(197,168,107,0.55)"
        },
        {
            key: "lectura", label: "Lectura",
            desc: "Frases para reflexionar",
            badge: "Motivación · Espiritualidad · Diaria",
            iconBg: "rgba(158,125,184,0.55)"
        }
    ];

    categorias.forEach(cat => {
        const btn = document.createElement("button");
        btn.className = "menu-cat-btn";
        btn.innerHTML = `
            <div class="menu-cat-icon" style="background:${cat.iconBg};"></div>
            <div class="menu-cat-info">
                <div class="menu-cat-label">${cat.label}</div>
                <div class="menu-cat-desc">${cat.desc}</div>
                <div class="menu-cat-badge">${cat.badge}</div>
            </div>
            <div class="menu-cat-chevron">›</div>
        `;
        btn.onclick = () => abrirSubmenu(cat.key);
        lista.appendChild(btn);
    });

    menu.classList.remove("hidden");
}

export function cerrarMenuEjercicios() {
    document.getElementById("ejercicios-menu").classList.add("hidden");
}

export function abrirSubmenu(categoriaKey) {
    document.getElementById("ejercicios-menu").classList.add("hidden");
    const submenu = document.getElementById("submenu-detalle");
    submenu.classList.remove("hidden");

    const titulo = document.getElementById("titulo-submenu");
    const lista  = document.getElementById("lista-ejercicios-detalle");
    lista.innerHTML = "";

    const titulos = {
        respiracion: "Respiración",
        meditacion:  "Meditación",
        yoga:        "Cuerpo y Movimiento",
        lectura:     "Lectura"
    };
    titulo.innerText = titulos[categoriaKey] || (categoriaKey.charAt(0).toUpperCase() + categoriaKey.slice(1));

    const ejercicios = CATALOGO_EJERCICIOS[categoriaKey];

    if (categoriaKey === 'lectura') {
        _renderPacksLectura(lista, ejercicios);
        return;
    }

    ejercicios.forEach(ej => {
        const duracion = getDuracion(categoriaKey, ej);

        const card = document.createElement("div");
        card.className = "ej-card";
        card.innerHTML = `
            <div class="ej-card-head">
                <h3 class="ej-card-titulo">${ej.nombre}</h3>
                ${duracion ? `<span class="ej-card-duracion">${duracion}</span>` : ''}
            </div>
            <p class="ej-card-desc">${ej.descripcion}</p>
            ${ej.cientifico ? `<p class="ej-card-cientifico">${ej.cientifico}</p>` : '<div class="ej-card-spacer"></div>'}
            <button class="btn-start-ejercicio">Comenzar →</button>
        `;
        card.querySelector(".btn-start-ejercicio").onclick = () => iniciarEjercicio(categoriaKey, ej);
        lista.appendChild(card);
    });
}

export function volverAMenuPrincipal() {
    document.getElementById("submenu-detalle").classList.add("hidden");
    document.getElementById("ejercicios-menu").classList.remove("hidden");
}

function _renderPacksLectura(lista, packs) {
    // Intro text
    const intro = document.createElement("p");
    intro.className = "lectura-intro";
    intro.textContent = "Elegí un tipo de lectura para este momento";
    lista.appendChild(intro);

    const colores = {
        lectura_motivacion:    { bg: "rgba(255,140,60,0.12)",  accent: "#e07830" },
        lectura_diaria:        { bg: "rgba(255,200,60,0.12)",  accent: "#c49a10" },
        lectura_espiritual:    { bg: "rgba(107,142,197,0.15)", accent: "#5a7ab8" },
        lectura_autocompasion: { bg: "rgba(107,197,142,0.15)", accent: "#2f8a5a" },
    };

    packs.forEach(pack => {
        const c = colores[pack.id] || { bg: "rgba(183,211,198,0.15)", accent: "#7db89e" };

        const card = document.createElement("div");
        card.className = "lectura-card";
        card.innerHTML = `
            <div class="lectura-card-head">
                <div class="lectura-card-icon" style="background:${c.accent}88;"></div>
                <div class="lectura-card-info">
                    <div class="lectura-card-nombre">${pack.nombre}</div>
                    <div class="lectura-card-count">${pack.quotes.length} frases</div>
                </div>
            </div>
            <p class="lectura-card-desc">${pack.descripcion}</p>
            <button class="btn-leer-pack" style="background:${c.bg}; color:${c.accent}; border-color:${c.accent}33;">Leer →</button>
        `;

        card.querySelector(".btn-leer-pack").onclick = () => {
            document.getElementById("submenu-detalle").classList.add("hidden");
            if (window.showReading) window.showReading(pack);
        };

        lista.appendChild(card);
    });
}

function getDuracion(tipo, ej) {
    if (tipo === 'respiracion') return '~1 min';
    if (tipo === 'lectura')     return '';
    if (ej.pasos) {
        const spp = ej.tiempoPorPaso || 20;
        const mins = Math.round(ej.pasos.length * spp / 60);
        return `~${mins} min`;
    }
    if (ej.duracion) return `${Math.round(ej.duracion / 60)} min`;
    return '';
}

export function volverAlChat() {
    document.getElementById("ejercicios-menu").classList.add("hidden");
    document.getElementById("submenu-detalle").classList.add("hidden");
    if (window.detenerRespiracion) window.detenerRespiracion();
    if (window.detenerGuiado) window.detenerGuiado();
    if (window.closeReading) window.closeReading();
}
