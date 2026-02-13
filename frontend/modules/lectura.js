// modules/lectura.js

// ============================================
// DATOS DE LECTURAS
// ============================================

const lecturas = [
    { quote: "La paz viene de adentro. No la busques afuera.", author: "Buda" },
    { quote: "No podés detener las olas, pero podés aprender a surfear.", author: "Jon Kabat-Zinn" },
    { quote: "La calma es la cuna del poder.", author: "J.G. Holland" },
    { quote: "Respira. Es solo un mal día, no una mala vida.", author: "Anónimo" }
];

let lecturaIndex = 0;

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

/**
 * Muestra la pantalla de lectura
 */
export function showReading() {
    const readingPanel = document.getElementById("reading");
    readingPanel.classList.remove("hidden");
    mostrarLectura();
}

/**
 * Cierra la pantalla de lectura
 */
export function closeReading() {
    document.getElementById("reading").classList.add("hidden");
}

/**
 * Muestra la siguiente lectura
 */
export function nextReading() {
    lecturaIndex = (lecturaIndex + 1) % lecturas.length;
    mostrarLectura();
}

// ============================================
// FUNCIONES PRIVADAS
// ============================================

function mostrarLectura() {
    const lectura = lecturas[lecturaIndex];
    const quoteElement = document.querySelector(".quote");
    const authorElement = document.querySelector(".author");
    
    if (quoteElement) quoteElement.innerText = `"${lectura.quote}"`;
    if (authorElement) authorElement.innerText = `— ${lectura.author}`;
}