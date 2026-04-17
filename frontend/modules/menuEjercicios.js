// modules/menuEjercicios.js
import { CATALOGO_EJERCICIOS } from '../ejerciciosData.js';
import { iniciarEjercicio } from './utils.js';
import { mostrarSelectorSonido, getSonidoGuardado, SONIDOS_AMBIENTE } from './ambientSound.js';

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
        <span class="bam-icon">⚙️</span>
        <span class="bam-label">Sonido de fondo</span>
        <span class="bam-current" id="bam-current-label">${sonidoActual.label.split(' ')[0]} ${sonidoActual.label.split(' ').slice(1).join(' ')}</span>
    `;
    btnSonido.onclick = () => mostrarSelectorSonido();
    lista.appendChild(btnSonido);

    // Escuchar cambios de sonido para actualizar el label en tiempo real
    const _onSoundChange = (e) => {
        const label = document.getElementById("bam-current-label");
        if (!label) return;
        const s = SONIDOS_AMBIENTE.find(s => s.id === e.detail.id);
        if (s) label.textContent = `${s.label.split(' ')[0]} ${s.label.split(' ').slice(1).join(' ')}`;
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
    sep.style.cssText = "width:100%; max-width:340px; height:1px; background:rgba(183,211,198,0.4); margin:4px 0 10px;";
    lista.appendChild(sep);

    // ── Categorías ──────────────────────────────────
    const categorias = [
        {
            key: "respiracion", label: "Respiración", emoji: "🌬️",
            desc: "Calma el sistema nervioso",
            badge: `${CATALOGO_EJERCICIOS.respiracion.length} ejercicios · desde 1 min`,
            iconBg: "rgba(125,184,158,0.18)"
        },
        {
            key: "meditacion", label: "Meditación", emoji: "🧘",
            desc: "Claridad y pausa mental",
            badge: `${CATALOGO_EJERCICIOS.meditacion.length} ejercicios · 1-3 min`,
            iconBg: "rgba(107,142,197,0.18)"
        },
        {
            key: "yoga", label: "Cuerpo y Movimiento", emoji: "🕉️",
            desc: "Soltar tensión física",
            badge: `${CATALOGO_EJERCICIOS.yoga.length} ejercicios · 3-5 min`,
            iconBg: "rgba(197,168,107,0.18)"
        }
    ];

    categorias.forEach(cat => {
        const btn = document.createElement("button");
        btn.style.cssText = `
            width: 100%; max-width: 340px;
            background: white;
            border: 1.5px solid rgba(183,211,198,0.4);
            border-radius: 18px;
            padding: 14px 16px;
            display: flex; align-items: center; gap: 14px;
            cursor: pointer; text-align: left;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            transition: all 0.2s ease;
            font-family: inherit;
        `;
        btn.innerHTML = `
            <div style="width:46px; height:46px; border-radius:14px; background:${cat.iconBg};
                        display:flex; align-items:center; justify-content:center;
                        font-size:1.45rem; flex-shrink:0;">
                ${cat.emoji}
            </div>
            <div style="flex:1; min-width:0;">
                <div style="font-weight:800; color:#2f4f45; font-size:1rem;">${cat.label}</div>
                <div style="font-size:0.82rem; color:#6b8e7d; margin-top:1px;">${cat.desc}</div>
                <div style="font-size:0.72rem; color:#b7d3c6; margin-top:2px;">${cat.badge}</div>
            </div>
            <div style="color:#b7d3c6; font-size:1.4rem; font-weight:300; margin-left:4px;">›</div>
        `;
        btn.onmouseenter = () => {
            btn.style.transform = "translateY(-2px)";
            btn.style.boxShadow = "0 6px 18px rgba(0,0,0,0.09)";
        };
        btn.onmouseleave = () => {
            btn.style.transform = "translateY(0)";
            btn.style.boxShadow = "0 2px 10px rgba(0,0,0,0.05)";
        };
        btn.onclick = () => abrirSubmenu(cat.key);
        lista.appendChild(btn);
    });

    // Botón de Lectura
    const btnLectura = document.createElement("button");
    btnLectura.style.cssText = `
        width: 100%; max-width: 340px;
        background: white;
        border: 1.5px solid rgba(183,211,198,0.4);
        border-radius: 18px;
        padding: 14px 16px;
        display: flex; align-items: center; gap: 14px;
        cursor: pointer; text-align: left;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        transition: all 0.2s ease;
        font-family: inherit;
    `;
    btnLectura.innerHTML = `
        <div style="width:46px; height:46px; border-radius:14px; background:rgba(158,125,184,0.18);
                    display:flex; align-items:center; justify-content:center; font-size:1.45rem; flex-shrink:0;">
            📖
        </div>
        <div style="flex:1; min-width:0;">
            <div style="font-weight:800; color:#2f4f45; font-size:1rem;">Lectura</div>
            <div style="font-size:0.82rem; color:#6b8e7d; margin-top:1px;">Frases para reflexionar</div>
            <div style="font-size:0.72rem; color:#b7d3c6; margin-top:2px;">Motivación · Espiritualidad · Diaria</div>
        </div>
        <div style="color:#b7d3c6; font-size:1.4rem; font-weight:300; margin-left:4px;">›</div>
    `;
    btnLectura.onmouseenter = () => {
        btnLectura.style.transform = "translateY(-2px)";
        btnLectura.style.boxShadow = "0 6px 18px rgba(0,0,0,0.09)";
    };
    btnLectura.onmouseleave = () => {
        btnLectura.style.transform = "translateY(0)";
        btnLectura.style.boxShadow = "0 2px 10px rgba(0,0,0,0.05)";
    };
    btnLectura.onclick = () => abrirSubmenu('lectura');
    lista.appendChild(btnLectura);

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
        respiracion: "🌬️ Respiración",
        meditacion:  "🧘 Meditación",
        yoga:        "🕉️ Cuerpo y Movimiento",
        lectura:     "📖 Lectura"
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
        card.style.cssText = `
            background: white;
            padding: 16px;
            border-radius: 16px;
            margin-bottom: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            border: 1.5px solid rgba(183,211,198,0.25);
        `;
        card.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px;">
                <h3 style="color:#2f4f45; font-size:1.05rem; font-weight:800; flex:1; margin:0;">${ej.nombre}</h3>
                ${duracion ? `<span style="
                    background: #eaf4ef; color: #7db89e;
                    font-size: 0.7rem; font-weight: 700;
                    padding: 3px 9px; border-radius: 20px;
                    margin-left: 10px; white-space: nowrap; flex-shrink:0;
                ">${duracion}</span>` : ''}
            </div>
            <p style="font-size:0.87rem; color:#5a7a6e; margin:0 0 6px; line-height:1.5;">${ej.descripcion}</p>
            ${ej.cientifico ? `<p style="font-size:0.77rem; color:#9fb5aa; font-style:italic; margin:0 0 12px; line-height:1.4;">💡 ${ej.cientifico}</p>` : '<div style="margin-bottom:12px;"></div>'}
            <button class="btn-start-ejercicio">Comenzar →</button>
        `;
        const btnStart = card.querySelector(".btn-start-ejercicio");
        btnStart.style.cssText = `
            background: linear-gradient(135deg, #7db89e, #5a9e84);
            border: none; padding: 10px 16px; border-radius: 12px;
            cursor: pointer; width: 100%;
            color: white; font-weight: 800; font-size: 0.92rem;
            font-family: inherit; letter-spacing: 0.02em;
            transition: opacity 0.2s;
        `;
        btnStart.onmouseenter = () => btnStart.style.opacity = "0.88";
        btnStart.onmouseleave = () => btnStart.style.opacity = "1";
        btnStart.onclick = () => iniciarEjercicio(categoriaKey, ej);
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
    intro.style.cssText = "font-size:0.85rem; color:#8fb5a3; text-align:center; margin: 0 0 8px; line-height:1.5;";
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
        card.style.cssText = `
            width: 100%; max-width: 340px;
            background: white;
            border-radius: 18px;
            padding: 16px;
            margin-bottom: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            border: 1.5px solid rgba(183,211,198,0.25);
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        `;
        card.innerHTML = `
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:10px;">
                <div style="width:44px; height:44px; border-radius:13px; background:${c.bg};
                            display:flex; align-items:center; justify-content:center;
                            font-size:1.4rem; flex-shrink:0;">
                    ${pack.emoji}
                </div>
                <div style="flex:1;">
                    <div style="font-weight:800; color:#2f4f45; font-size:1rem;">${pack.nombre}</div>
                    <div style="font-size:0.72rem; color:#b7d3c6; margin-top:2px;">${pack.quotes.length} frases</div>
                </div>
            </div>
            <p style="font-size:0.85rem; color:#5a7a6e; margin:0 0 12px; line-height:1.5;">${pack.descripcion}</p>
            <button class="btn-leer-pack" style="
                background: ${c.bg};
                color: ${c.accent};
                border: 1.5px solid ${c.accent}33;
                padding: 9px 16px; border-radius: 12px;
                cursor: pointer; width: 100%;
                font-weight: 800; font-size: 0.9rem;
                font-family: inherit; transition: opacity 0.2s;
            ">Leer →</button>
        `;

        const btn = card.querySelector(".btn-leer-pack");
        btn.onmouseenter = () => { btn.style.opacity = "0.8"; card.style.transform = "translateY(-2px)"; card.style.boxShadow = "0 6px 18px rgba(0,0,0,0.09)"; };
        btn.onmouseleave = () => { btn.style.opacity = "1";   card.style.transform = "translateY(0)";   card.style.boxShadow = "0 2px 8px rgba(0,0,0,0.06)"; };
        btn.onclick = () => {
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