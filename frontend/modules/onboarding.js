// modules/onboarding.js
import { mostrarAvisoTesterCada } from './utils.js';

// ============================================
// PREGUNTAS
// ============================================

const PREGUNTAS = [
    {
        numero: 1,
        pregunta: "¿Cómo querés que te llame?",
        tipo: "texto",
        placeholder: "Tu nombre o apodo..."
    },
    {
        numero: 2,
        pregunta: "¿Con qué pronombres te sentís más cómodo/a?",
        tipo: "opcion_unica",
        opciones: ["Él", "Ella", "Prefiero que no use pronombres", "Otro"],
        otroIndex: 3  // índice de la opción "Otro"
    },
    {
        numero: 3,
        pregunta: "¿Cómo está tu vida ahora mismo?",
        tipo: "opcion_multiple",
        opciones: [
            "Estudiando",
            "Trabajando",
            "Buscando trabajo",
            "Con familia o pareja",
            "Viviendo solo/a",
            "Otra etapa"
        ],
        otroIndex: 5
    },
    {
        numero: 4,
        pregunta: "¿Qué es lo que más te pesa últimamente?",
        tipo: "opcion_unica",
        opciones: [
            "El rendimiento (estudio o trabajo)",
            "Las relaciones con otros",
            "No saber bien hacia dónde voy",
            "El cuerpo o la salud",
            "Nada en particular por ahora",
            "Otro"
        ],
        otroIndex: 5
    },
    {
        numero: 5,
        pregunta: "En momentos de estrés o tensión, ¿qué te pasa habitualmente?",
        tipo: "opcion_unica",
        opciones: [
            "Me acelero o me pongo ansioso/a",
            "Me cierro y me quedo callado/a",
            "Me enojo o me frustro fácilmente",
            "Busco distracción (teléfono, series, etc.)",
            "Me cuesta darme cuenta de lo que siento"
        ]
    },
    {
        numero: 6,
        pregunta: "¿Cómo preferís que Numa responda?",
        tipo: "opcion_unica",
        opciones: [
            "Corto y directo, sin rodeos",
            "Con calma, que me acompañe",
            "Que me haga preguntas para entender mejor",
            "Que mezcle escucha con algo concreto"
        ]
    },
    {
        numero: 7,
        pregunta: "¿Hay algo que querés que Numa sepa antes de empezar?",
        tipo: "textarea",
        placeholder: "Ej: estoy pasando un momento difícil, no me gustan los consejos genéricos, prefiero que sea directo..."
    }
];

// ============================================
// ESTADO
// ============================================

let pasoActual = 0;
let respuestas = {};
let userId = null;

// ============================================
// FUNCIONES PÚBLICAS
// ============================================

export function showOnboarding(user_id) {
    userId = user_id;
    pasoActual = 0;
    respuestas = {};

    if (!document.getElementById('onboarding-screen')) {
        _crearOnboardingScreen();
    }

    document.getElementById('onboarding-screen').classList.remove('hidden');
    _mostrarPaso(0);
}

export function hideOnboarding() {
    const screen = document.getElementById('onboarding-screen');
    if (screen) screen.classList.add('hidden');
}

// ============================================
// CREAR PANTALLA
// ============================================

function _crearOnboardingScreen() {
    const screen = document.createElement('div');
    screen.id = 'onboarding-screen';
    screen.innerHTML = `
        <div class="onboarding-container">

            <div class="onboarding-header">
                <span>🐼</span>
                <h2>Hola, soy Numa</h2>
                <p>Antes de empezar, quiero conocerte un poco</p>
            </div>

            <div class="onboarding-progress">
                <div class="onboarding-progress-bar" id="onboarding-progress-bar"></div>
            </div>
            <p class="onboarding-step-label" id="onboarding-step-label">1 de 10</p>

            <div id="onboarding-pregunta-container" class="onboarding-pregunta-container">
            </div>

            <div class="onboarding-nav">
                <button class="onboarding-btn-back hidden" id="onboarding-back" onclick="onboardingBack()">
                    ← Atrás
                </button>
                <button class="onboarding-btn-next" id="onboarding-next" onclick="onboardingNext()">
                    Siguiente →
                </button>
            </div>

        </div>
    `;

    document.body.appendChild(screen);
}

// ============================================
// MOSTRAR PASO
// ============================================

function _mostrarPaso(index) {
    const pregunta = PREGUNTAS[index];
    const container = document.getElementById('onboarding-pregunta-container');
    const progressBar = document.getElementById('onboarding-progress-bar');
    const stepLabel = document.getElementById('onboarding-step-label');
    const backBtn = document.getElementById('onboarding-back');
    const nextBtn = document.getElementById('onboarding-next');

    // Actualizar progreso
    const progreso = ((index + 1) / PREGUNTAS.length) * 100;
    progressBar.style.width = `${progreso}%`;
    stepLabel.textContent = `${index + 1} de ${PREGUNTAS.length}`;

    // Mostrar/ocultar botón atrás
    if (index === 0) {
        backBtn.classList.add('hidden');
    } else {
        backBtn.classList.remove('hidden');
    }

    // Cambiar texto del botón en el último paso
    if (index === PREGUNTAS.length - 1) {
        nextBtn.textContent = 'Empezar 🐼';
    } else {
        nextBtn.textContent = 'Siguiente →';
    }

    // Renderizar pregunta
    container.innerHTML = `
        <h3 class="onboarding-pregunta">${pregunta.pregunta}</h3>
        ${_renderInput(pregunta)}
    `;

    // Restaurar respuesta previa si existe
    if (respuestas[index] !== undefined) {
        _restaurarRespuesta(pregunta, respuestas[index]);
    }
}

// ============================================
// RENDER INPUTS
// ============================================

function _renderInput(pregunta) {
    if (pregunta.tipo === 'texto') {
        return `<input 
            type="text" 
            id="onboarding-input" 
            class="auth-input" 
            placeholder="${pregunta.placeholder}"
            style="width:100%"
        />`;
    }

    if (pregunta.tipo === 'textarea') {
        return `<textarea 
            id="onboarding-input" 
            class="auth-input onboarding-textarea" 
            placeholder="${pregunta.placeholder}"
        ></textarea>`;
    }

    if (pregunta.tipo === 'opcion_unica') {
        return `<div class="onboarding-opciones">
            ${pregunta.opciones.map((op, i) => `
                <button 
                    class="onboarding-opcion" 
                    data-index="${i}"
                    onclick="seleccionarOpcion(this, ${pregunta.otroIndex !== undefined ? pregunta.otroIndex : -1})"
                >
                    ${op}
                </button>
            `).join('')}
            <textarea
                id="otro-textarea"
                class="auth-input onboarding-textarea"
                placeholder="Contame un poco más..."
                style="display:none; margin-top: 4px; min-height: 80px;"
            ></textarea>
        </div>`;
    }

    if (pregunta.tipo === 'opcion_multiple') {
        return `<div class="onboarding-opciones">
            ${pregunta.opciones.map((op, i) => `
                <button 
                    class="onboarding-opcion" 
                    data-index="${i}"
                    onclick="seleccionarOpcionMultiple(this)"
                >
                    ${op}
                </button>
            `).join('')}
        </div>
        <p style="font-size:0.8rem; color:#8fb5a3; text-align:center; margin-top:8px;">
            Podés elegir varias opciones
        </p>`;
    }

    return '';
}

// ============================================
// RESTAURAR RESPUESTA
// ============================================

function _restaurarRespuesta(pregunta, respuesta) {
    if (pregunta.tipo === 'texto' || pregunta.tipo === 'textarea') {
        const input = document.getElementById('onboarding-input');
        if (input) input.value = respuesta;
    }

    if (pregunta.tipo === 'opcion_unica') {
        const botones = document.querySelectorAll('.onboarding-opcion');
        botones.forEach(btn => {
            if (btn.textContent.trim() === respuesta) {
                btn.classList.add('selected');
            }
        });
    }

    if (pregunta.tipo === 'opcion_multiple') {
        const botones = document.querySelectorAll('.onboarding-opcion');
        botones.forEach(btn => {
            if (respuesta.includes(btn.textContent.trim())) {
                btn.classList.add('selected');
            }
        });
    }
}

// ============================================
// OBTENER RESPUESTA ACTUAL
// ============================================

function _obtenerRespuesta() {
    const pregunta = PREGUNTAS[pasoActual];

    if (pregunta.tipo === 'texto' || pregunta.tipo === 'textarea') {
        const input = document.getElementById('onboarding-input');
        return input ? input.value.trim() : '';
    }

    if (pregunta.tipo === 'opcion_unica') {
        const selected = document.querySelector('.onboarding-opcion.selected');
        if (!selected) return '';
    
        const textarea = document.querySelector('#otro-textarea');
        const hayTextoLibre = textarea && textarea.style.display !== 'none' && textarea.value.trim();
    
        return hayTextoLibre
            ? textarea.value.trim()       // si escribió algo, guardamos eso directamente
            : selected.textContent.trim();
    }

    if (pregunta.tipo === 'opcion_multiple') {
        const selected = document.querySelectorAll('.onboarding-opcion.selected');
        return Array.from(selected).map(el => el.textContent.trim());
    }

    return '';
}

// ============================================
// NAVEGACIÓN
// ============================================

function _next() {
    const respuesta = _obtenerRespuesta();

    // Validar que respondió
    if (!respuesta || respuesta.length === 0) {
        _mostrarToast('Por favor respondé esta pregunta para continuar');
        return;
    }

    // Guardar respuesta
    respuestas[pasoActual] = respuesta;

    // Si es el último paso → enviar
    if (pasoActual === PREGUNTAS.length - 1) {
        _enviarOnboarding();
        return;
    }

    // Siguiente pregunta
    pasoActual++;
    _mostrarPaso(pasoActual);
}

function _back() {
    if (pasoActual > 0) {
        // Guardar respuesta actual antes de volver
        const respuesta = _obtenerRespuesta();
        if (respuesta) respuestas[pasoActual] = respuesta;

        pasoActual--;
        _mostrarPaso(pasoActual);
    }
}

// ============================================
// ENVIAR ONBOARDING AL BACKEND
// ============================================

async function _enviarOnboarding() {
    const nextBtn = document.getElementById('onboarding-next');
    nextBtn.textContent = 'Guardando...';
    nextBtn.disabled = true;

    const answers = PREGUNTAS.map((p, i) => ({
        pregunta_numero: p.numero,
        pregunta: p.pregunta,
        respuesta: Array.isArray(respuestas[i])
            ? respuestas[i].join(', ')
            : respuestas[i] || ''
    }));

    try {
    const user = JSON.parse(localStorage.getItem('numa_user'));

    const res = await fetch('/onboarding', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${user.access_token}`
        },
        body: JSON.stringify({
            user_id: user.user_id,
            answers: answers
        })
    });

    if (!res.ok) {
        const errorData = await res.json();
        console.error('Error del servidor:', errorData);
        throw new Error(errorData.detail || 'Error al guardar');
    }

    hideOnboarding();

    const app = document.querySelector('.app');
    if (app) app.style.display = 'flex';    

    const nombre = respuestas[0] || 'vos';
    if (window.agregarMensaje) {
        window.agregarMensaje(
            `Hola ${nombre} 🐼 Gracias por contarme un poco sobre vos. Estoy acá cuando quieras hablar.`,
            "oso"
        );
    }
    mostrarAvisoTesterCada();

} catch (e) {
    console.error('Error completo:', e);
    nextBtn.textContent = 'Empezar 🐼';
    nextBtn.disabled = false;
    _mostrarToast(`Error: ${e.message}`);
}
}

// ============================================
// HELPERS
// ============================================

function _mostrarToast(mensaje) {
    let toast = document.getElementById('onboarding-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'onboarding-toast';
        toast.className = 'onboarding-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = mensaje;
    toast.classList.add('visible');
    setTimeout(() => toast.classList.remove('visible'), 2500);
}

// ============================================
// EXPONER AL WINDOW
// ============================================

window.onboardingNext = _next;
window.onboardingBack = _back;
window.seleccionarOpcion = (btn, otroIndex) => {
    const contenedor = btn.closest('.onboarding-opciones');
    contenedor.querySelectorAll('.onboarding-opcion').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');

    const textarea = contenedor.querySelector('#otro-textarea');
    const esOtro = Number(btn.dataset.index) === otroIndex && otroIndex !== -1;

    if (textarea) {
        textarea.style.display = esOtro ? 'block' : 'none';
        if (!esOtro) textarea.value = '';
    }
};
window.seleccionarOpcionMultiple = (btn) => {
    btn.classList.toggle('selected');
};