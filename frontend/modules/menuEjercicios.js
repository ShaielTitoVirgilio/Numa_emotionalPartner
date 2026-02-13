// modules/menuEjercicios.js
import { CATALOGO_EJERCICIOS } from '../ejerciciosData.js';
import { iniciarEjercicio } from './utils.js';

// ============================================
// MENÚ PRINCIPAL DE EJERCICIOS
// ============================================

/**
 * Abre el menú principal de categorías
 */
export function irAEjercicios() {
    const menu = document.getElementById("ejercicios-menu");
    const lista = document.getElementById("lista-categorias");
    
    if (!menu || !lista) {
        return console.error("Faltan elementos del menú en HTML");
    }

    lista.innerHTML = ""; // Limpiar lista anterior

    const categorias = [
        { key: "respiracion", label: "🌬️ Respiración", desc: "Calma el sistema nervioso" },
        { key: "meditacion", label: "🧘 Meditación", desc: "Claridad y pausa mental" },
        { key: "yoga", label: "🕉️ Cuerpo y Movimiento", desc: "Soltar tensión física" }
    ];

    // Renderizar botones de categorías
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

    // Agregar botón de Lectura (Legacy)
    const btnLectura = document.createElement("button");
    btnLectura.className = "exercise-btn";
    btnLectura.innerHTML = `<strong>📖 Lectura</strong><br><span style="font-size:0.8em; opacity:0.8">Frases inspiradoras</span>`;
    btnLectura.onclick = () => {
        if (window.showReading) window.showReading();
    };
    lista.appendChild(btnLectura);

    menu.classList.remove("hidden");
}

/**
 * Cierra el menú principal
 */
export function cerrarMenuEjercicios() {
    document.getElementById("ejercicios-menu").classList.add("hidden");
}

/**
 * Abre el submenú con ejercicios de una categoría específica
 */
export function abrirSubmenu(categoriaKey) {
    document.getElementById("ejercicios-menu").classList.add("hidden");
    const submenu = document.getElementById("submenu-detalle");
    submenu.classList.remove("hidden");
    
    const titulo = document.getElementById("titulo-submenu");
    const lista = document.getElementById("lista-ejercicios-detalle");
    lista.innerHTML = "";

    // Capitalizar título
    titulo.innerText = categoriaKey.charAt(0).toUpperCase() + categoriaKey.slice(1);

    const ejercicios = CATALOGO_EJERCICIOS[categoriaKey];

    // Renderizar cards de ejercicios
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

/**
 * Vuelve del submenú al menú principal
 */
export function volverAMenuPrincipal() {
    document.getElementById("submenu-detalle").classList.add("hidden");
    document.getElementById("ejercicios-menu").classList.remove("hidden");
}

/**
 * Cierra todos los menús y overlays, vuelve al chat
 */
export function volverAlChat() {
    document.getElementById("ejercicios-menu").classList.add("hidden");
    document.getElementById("submenu-detalle").classList.add("hidden");
    
    // Cerrar overlays de ejercicios
    if (window.detenerRespiracion) window.detenerRespiracion();
    if (window.detenerGuiado) window.detenerGuiado();
    if (window.closeReading) window.closeReading();
}