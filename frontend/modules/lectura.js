// modules/lectura.js
import { detenerSonidoAmbiente, iniciarSonidoAmbiente } from './ambientSound.js';

// ============================================
// ESTADO
// ============================================

let packActual  = null;
let indiceActual = 0;

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

/**
 * Abre el overlay de lectura con el pack seleccionado.
 * @param {Object} packData — entrada de CATALOGO_EJERCICIOS.lectura
 */
export function showReading(packData) {
    packActual   = packData;
    indiceActual = Math.floor(Math.random() * packData.quotes.length);

    iniciarSonidoAmbiente();

    const panel = document.getElementById("reading");
    panel.classList.remove("hidden");

    _renderPack();
    _renderLectura();
}

export function closeReading() {
    document.getElementById("reading").classList.add("hidden");
    detenerSonidoAmbiente();
    packActual   = null;
    indiceActual = 0;
}

export function nextReading() {
    if (!packActual) return;
    indiceActual = (indiceActual + 1) % packActual.quotes.length;
    _renderLectura(true);
}

export function prevReading() {
    if (!packActual) return;
    indiceActual = (indiceActual - 1 + packActual.quotes.length) % packActual.quotes.length;
    _renderLectura(true);
}

// ============================================
// FUNCIONES PRIVADAS
// ============================================

function _renderPack() {
    const badge  = document.getElementById("reading-pack-badge");
    const counter = document.getElementById("reading-counter");

    if (badge && packActual) {
        badge.textContent = `${packActual.emoji}  ${packActual.nombre}`;
    }
    _actualizarCounter(counter);
}

function _renderLectura(animar = false) {
    if (!packActual) return;

    const lectura       = packActual.quotes[indiceActual];
    const quoteEl       = document.querySelector("#reading .reading-quote");
    const authorEl      = document.querySelector("#reading .reading-author");
    const counter       = document.getElementById("reading-counter");

    _actualizarCounter(counter);

    if (!quoteEl || !authorEl) return;

    if (animar) {
        quoteEl.style.opacity  = "0";
        authorEl.style.opacity = "0";
        setTimeout(() => {
            quoteEl.textContent  = `"${lectura.quote}"`;
            authorEl.textContent = `— ${lectura.author}`;
            quoteEl.style.opacity  = "1";
            authorEl.style.opacity = "1";
        }, 200);
    } else {
        quoteEl.textContent  = `"${lectura.quote}"`;
        authorEl.textContent = `— ${lectura.author}`;
    }
}

function _actualizarCounter(el) {
    if (el && packActual) {
        el.textContent = `${indiceActual + 1} / ${packActual.quotes.length}`;
    }
}
