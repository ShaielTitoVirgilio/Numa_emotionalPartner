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
        { key: "respiracion", label: "🌬️ Respiración", desc: "Calma el sistema nervioso" },
        { key: "meditacion",  label: "🧘 Meditación",  desc: "Claridad y pausa mental" },
        { key: "yoga",        label: "🕉️ Cuerpo y Movimiento", desc: "Soltar tensión física" }
    ];

    categorias.forEach(cat => {
        const btn = document.createElement("button");
        btn.className = "exercise-btn";
        btn.innerHTML = `
            <strong>${cat.label}</strong>
            <br>
            <span style="font-size:0.8em; opacity:0.8">${cat.desc}</span>
        `;
        btn.onclick = () => abrirSubmenu(cat.key);
        lista.appendChild(btn);
    });

    // Botón de Lectura
    const btnLectura = document.createElement("button");
    btnLectura.className = "exercise-btn";
    btnLectura.innerHTML = `<strong>📖 Lectura</strong><br><span style="font-size:0.8em; opacity:0.8">Frases inspiradoras</span>`;
    btnLectura.onclick = () => { if (window.showReading) window.showReading(); };
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

    titulo.innerText = categoriaKey.charAt(0).toUpperCase() + categoriaKey.slice(1);

    const ejercicios = CATALOGO_EJERCICIOS[categoriaKey];

    ejercicios.forEach(ej => {
        const card = document.createElement("div");
        card.style.cssText = "background: white; padding: 15px; border-radius: 12px; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);";
        card.innerHTML = `
            <h3 style="color: #4a6a5e; margin-bottom: 5px; font-size: 1.1rem;">${ej.nombre}</h3>
            <p style="font-size: 0.9rem; color: #666; margin-bottom: 8px;">${ej.descripcion}</p>
            <p style="font-size: 0.8rem; color: #8fb5a3; font-style: italic; margin-bottom: 10px;">💡 ${ej.cientifico || "Validado."}</p>
            <button class="btn-start-ejercicio">Empezar</button>
        `;
        const btnStart = card.querySelector(".btn-start-ejercicio");
        btnStart.style.cssText = "background:#b7d3c6; border:none; padding:8px 16px; border-radius:20px; cursor:pointer; width:100%; color: #2f4f45; font-weight: bold;";
        btnStart.onclick = () => iniciarEjercicio(categoriaKey, ej);
        lista.appendChild(card);
    });
}

export function volverAMenuPrincipal() {
    document.getElementById("submenu-detalle").classList.add("hidden");
    document.getElementById("ejercicios-menu").classList.remove("hidden");
}

export function volverAlChat() {
    document.getElementById("ejercicios-menu").classList.add("hidden");
    document.getElementById("submenu-detalle").classList.add("hidden");
    if (window.detenerRespiracion) window.detenerRespiracion();
    if (window.detenerGuiado) window.detenerGuiado();
    if (window.closeReading) window.closeReading();
}