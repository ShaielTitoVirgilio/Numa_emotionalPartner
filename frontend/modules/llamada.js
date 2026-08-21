// modules/llamada.js
// Modo llamada: hablás y Numa te contesta hablando, sin botones de por medio.
// El chat desaparece y queda solo Numa grande en el centro de la pantalla.
//
// Ciclo (estrictamente secuencial, nunca escucha y habla a la vez):
//
//   escuchando ──(1s de silencio)──> pensando ──> hablando ──(fin)──> escuchando
//        ↑                                                                │
//        └────────────────────────────────────────────────────────────────┘
//
// El micro está CERRADO mientras Numa habla a propósito: si el usuario está en
// parlantes (no auriculares), el micro escucharía a Numa, lo transcribiría y se
// armaría un loop infinito de Numa hablándose sola.

import { authHeaders } from './utils.js';
import { enviarDesdeLlamada } from './chat.js';
import { hablar, detenerHabla, despertarVoz, alTerminarDeHablar, vozDisponible } from './voz.js';

// ============================================
// AFINADO DE LA DETECCIÓN DE VOZ (VAD)
// Estos son los números para tocar si corta antes de tiempo o tarda de más.
// ============================================

// Volumen RMS por encima del cual consideramos que hay VOZ (no ruido ambiente).
// El chat escrito usa 0.015; acá va más alto a propósito: en una llamada el
// ruido de fondo (ventilador, calle, tele) no tiene que contar como que el
// usuario sigue hablando, si no nunca corta.
const UMBRAL_VOZ = 0.028;

// Cuánto silencio hace falta para dar por terminado el turno del usuario.
// 1 segundo: suficiente para no cortar entre oración y oración, y corto como
// para que la respuesta no se sienta lenta.
const SILENCIO_PARA_CORTAR_MS = 1000;

// Cada cuánto se mide el volumen. Más seguido = corta más al toque.
const INTERVALO_CHEQUEO_MS = 100;

// Voz acumulada mínima para que el turno se mande. Evita que un portazo, una
// tos o un "ajá" disparen una request al LLM.
const MIN_VOZ_ACUMULADA_MS = 400;

// Tope duro de un turno, por si el VAD no corta nunca (micro trabado, ruido
// constante por encima del umbral).
const MAX_TURNO_MS = 25000;

// Frase que Numa dice antes de cortar la llamada cuando se activa la respuesta
// de contención: los teléfonos de ayuda tienen que poder TOCARSE, y eso solo
// pasa en la tarjeta del chat. Se avisa antes de cortar para que no se sienta
// un corte seco en un momento delicado.
const FRASE_PUENTE_CRISIS =
  'Perdoná que corte así la charla, pero esto es importante de verdad. ' +
  'Te dejo algo en pantalla, miralo.';

// ============================================
// ESTADO
// ============================================

let enLlamada = false;
let estado = 'inactivo';   // escuchando | pensando | hablando | inactivo

let stream = null;          // MediaStream del micro, se pide UNA vez por llamada
let mediaRecorder = null;
let audioChunks = [];

let audioContext = null;
let analyserNode = null;
let chequeoInterval = null;
let timeoutTurno = null;

let silencioDesde = null;
let vozAcumuladaMs = 0;
let yaHablo = false;        // el usuario ya dijo algo en este turno
let ultimoChequeo = null;   // timestamp del chequeo anterior (ver _chequearVolumen)

let overlay = null;
let contenedorOsoOriginal = null;
let hermanoOsoOriginal = null;   // ver _desmontarOverlay
let osoEl = null;

// Corta las requests del turno en curso (STT y LLM) cuando se sale de la
// llamada: sin esto el servidor sigue transcribiendo y generando una respuesta
// que ya nadie va a escuchar.
let abortoTurno = null;

// ============================================
// API PÚBLICA
// ============================================

export function estaEnLlamada() {
  return enLlamada;
}

export async function abrirLlamada() {
  if (enLlamada) return;

  if (!navigator.mediaDevices?.getUserMedia) {
    alert('Tu navegador no permite usar el micrófono.');
    return;
  }

  // iOS: el motor de voz solo arranca si el primer speak() ocurre dentro de un
  // gesto del usuario. Este tap es ese gesto.
  despertarVoz();

  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    console.error('No se pudo abrir el micrófono:', e);
    alert('No pude acceder al micrófono. Revisá los permisos del navegador.');
    return;
  }

  enLlamada = true;
  abortoTurno = new AbortController();
  _montarOverlay();
  _prepararAnalizador();

  alTerminarDeHablar(() => {
    // Numa terminó de decir todo → le toca al usuario.
    if (enLlamada) _escuchar();
  });

  _escuchar();
}

export function cerrarLlamada() {
  if (!enLlamada) return;
  enLlamada = false;

  abortoTurno?.abort();
  abortoTurno = null;

  _pararEscucha();
  detenerHabla();
  alTerminarDeHablar(null);

  if (stream) {
    stream.getTracks().forEach(t => t.stop());
    stream = null;
  }
  if (audioContext) {
    audioContext.close().catch(() => {});
    audioContext = null;
  }
  analyserNode = null;

  _desmontarOverlay();
  estado = 'inactivo';
}

// ============================================
// CICLO: ESCUCHAR
// ============================================

function _escuchar() {
  if (!enLlamada || !stream) return;

  _setEstado('escuchando');

  audioChunks = [];
  silencioDesde = null;
  vozAcumuladaMs = 0;
  yaHablo = false;
  ultimoChequeo = null;

  try {
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
  } catch (e) {
    console.error('MediaRecorder no soportado:', e);
    cerrarLlamada();
    return;
  }

  mediaRecorder.ondataavailable = e => {
    if (e.data.size > 0) audioChunks.push(e.data);
  };

  mediaRecorder.onstop = () => {
    clearInterval(chequeoInterval);
    chequeoInterval = null;
    clearTimeout(timeoutTurno);
    timeoutTurno = null;
    if (!enLlamada) return;

    // Se descarta el turno si no hubo voz suficiente (fue ruido o silencio):
    // se vuelve a escuchar sin molestar al usuario ni gastar una llamada al LLM.
    if (vozAcumuladaMs < MIN_VOZ_ACUMULADA_MS) {
      _escuchar();
      return;
    }

    const blob = new Blob(audioChunks, { type: 'audio/webm' });
    _procesarTurno(blob);
  };

  mediaRecorder.start();

  chequeoInterval = setInterval(_chequearVolumen, INTERVALO_CHEQUEO_MS);
  timeoutTurno = setTimeout(() => _cortarTurno(), MAX_TURNO_MS);
}

function _prepararAnalizador() {
  audioContext = new AudioContext();
  const source = audioContext.createMediaStreamSource(stream);
  analyserNode = audioContext.createAnalyser();
  analyserNode.fftSize = 2048;
  source.connect(analyserNode);
}

function _chequearVolumen() {
  if (!analyserNode || !enLlamada) return;

  // Cuánto tiempo REAL pasó desde el chequeo anterior. Importa medirlo con el
  // reloj y no asumir que cada tick son INTERVALO_CHEQUEO_MS: el navegador
  // estrangula los setInterval cuando la pestaña pierde foco (y en móvil
  // también con la pantalla atenuada). Contando ticks, la voz acumulada
  // quedaba corta, el turno se descartaba por "no habló" y Numa parecía sorda.
  // El tope evita que una suspensión larga cuente como 10s de voz de golpe.
  const ahora = Date.now();
  const delta = ultimoChequeo === null
    ? INTERVALO_CHEQUEO_MS
    : Math.min(ahora - ultimoChequeo, INTERVALO_CHEQUEO_MS * 5);
  ultimoChequeo = ahora;

  const datos = new Float32Array(analyserNode.fftSize);
  analyserNode.getFloatTimeDomainData(datos);

  let suma = 0;
  for (let i = 0; i < datos.length; i++) suma += datos[i] * datos[i];
  const rms = Math.sqrt(suma / datos.length);

  _pintarNivel(rms);

  if (rms >= UMBRAL_VOZ) {
    // Hay voz
    yaHablo = true;
    vozAcumuladaMs += delta;
    silencioDesde = null;
    return;
  }

  // Silencio. Ojo: no se corta hasta que el usuario haya dicho ALGO en este
  // turno; si no, cortaría 1 segundo después de abrir el micro con la persona
  // todavía pensando qué decir.
  if (!yaHablo) return;

  if (silencioDesde === null) {
    silencioDesde = Date.now();
  } else if (Date.now() - silencioDesde >= SILENCIO_PARA_CORTAR_MS) {
    _cortarTurno();
  }
}

function _cortarTurno() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    try { mediaRecorder.stop(); } catch { /* noop */ }
  }
}

function _pararEscucha() {
  clearInterval(chequeoInterval);
  chequeoInterval = null;
  clearTimeout(timeoutTurno);
  timeoutTurno = null;
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.onstop = null;   // no encadenar otro turno al cerrar
    try { mediaRecorder.stop(); } catch { /* noop */ }
  }
  mediaRecorder = null;
}

// ============================================
// CICLO: PENSAR (STT + LLM) Y HABLAR
// ============================================

async function _procesarTurno(blob) {
  _setEstado('pensando');

  let texto = '';
  try {
    texto = await _transcribir(blob);
  } catch (e) {
    console.warn('STT falló en la llamada:', e);
  }

  if (!enLlamada) return;

  // Sin transcripción utilizable (ruido, audio corto que el backend rechaza):
  // se vuelve a escuchar en silencio, sin cortar la llamada ni mostrar error.
  if (!texto) {
    _escuchar();
    return;
  }

  let huboCrisis = false;

  try {
    await enviarDesdeLlamada(texto, {
      signal: abortoTurno?.signal,
      onOracion: (oracion) => {
        if (!enLlamada || huboCrisis) return;
        if (estado !== 'hablando') _setEstado('hablando');
        hablar(oracion);
      },
      onCrisis: () => {
        huboCrisis = true;
      },
    });
  } catch (e) {
    // Salir de la llamada aborta el turno a propósito: no es un error real.
    if (!enLlamada || e?.name === 'AbortError') return;
    console.error('Error hablando con Numa:', e);
    _setEstado('hablando');
    hablar('Perdón, se me cortó. ¿Me lo decís de nuevo?');
    return;
  }

  if (!enLlamada) return;

  if (huboCrisis) {
    // La respuesta de contención NO se dice en voz: lleva teléfonos de ayuda
    // que tienen que poder tocarse. Numa avisa que corta y se sale de la
    // llamada; la tarjeta con los links ya quedó agregada al chat.
    _setEstado('hablando');
    detenerHabla();
    alTerminarDeHablar(() => {
      alTerminarDeHablar(null);
      cerrarLlamada();
    });
    // El pequeño delay no es cosmético: cancel() seguido de speak() en el mismo
    // tick hace que varios navegadores descarten la frase nueva, y acá esa
    // frase es justamente el aviso de que se corta la charla. Si aun así no
    // sonara, el fallback de voz.js igual cierra la llamada.
    setTimeout(() => {
      if (enLlamada) hablar(FRASE_PUENTE_CRISIS);
    }, 120);
    return;
  }

  // Si no se encoló nada para decir (respuesta vacía), no esperamos un fin de
  // habla que no va a llegar: volvemos a escuchar directamente.
  if (estado !== 'hablando') _escuchar();
}

async function _transcribir(blob) {
  const formData = new FormData();
  formData.append('file', blob, 'voz.webm');

  const res = await fetch('/speech-to-text', {
    method: 'POST',
    headers: await authHeaders(),
    body: formData,
    signal: abortoTurno?.signal,
  });
  if (!res.ok) throw new Error(await res.text());

  const data = await res.json();
  return (data.text || '').trim();
}

// ============================================
// UI
// ============================================

const TEXTO_ESTADO = {
  escuchando: 'Te escucho…',
  pensando:   'Pensando…',
  hablando:   '',
};

// Estado del oso por estado de la llamada. 'listening' ya existía (el oso
// inclina la cabeza, curioso); 'hablando' se agregó en bear3d.js.
const OSO_POR_ESTADO = {
  escuchando: 'listening',
  pensando:   'thinking',
  hablando:   'hablando',
};

function _setEstado(nuevo) {
  estado = nuevo;
  window.setBearState?.(OSO_POR_ESTADO[nuevo] || 'calm');

  const label = overlay?.querySelector('.llamada-estado');
  if (label) label.textContent = TEXTO_ESTADO[nuevo] ?? '';

  overlay?.classList.toggle('escuchando', nuevo === 'escuchando');
  if (nuevo !== 'escuchando') _pintarNivel(0);
}

/** Halo que crece con el volumen de tu voz, para que se vea que te está
 * escuchando de verdad (y no que se colgó). */
function _pintarNivel(rms) {
  const halo = overlay?.querySelector('.llamada-halo');
  if (!halo) return;
  if (estado !== 'escuchando') {
    halo.style.transform = 'scale(1)';
    halo.style.opacity = '0.25';
    return;
  }
  const intensidad = Math.min(1, rms / (UMBRAL_VOZ * 3));
  halo.style.transform = `scale(${1 + intensidad * 0.35})`;
  halo.style.opacity = `${0.25 + intensidad * 0.45}`;
}

function _montarOverlay() {
  overlay = document.createElement('div');
  overlay.className = 'llamada-overlay';
  overlay.innerHTML = `
    <button class="llamada-salir" aria-label="Salir de la llamada">✕</button>
    <div class="llamada-centro">
      <div class="llamada-halo"></div>
      <div class="llamada-oso"></div>
    </div>
    <p class="llamada-estado"></p>
  `;
  overlay.querySelector('.llamada-salir').onclick = cerrarLlamada;
  document.body.appendChild(overlay);

  // Se MUEVE el canvas del oso (no se crea otro): mover el elemento en el DOM
  // conserva el contexto WebGL, así que sigue animando sin reinicializar nada.
  osoEl = document.getElementById('bear-container');
  if (osoEl) {
    contenedorOsoOriginal = osoEl.parentElement;
    // Hay que guardar TAMBIÉN el hermano siguiente: el oso va arriba del chat,
    // no al final de la vista. Devolverlo con appendChild lo dejaba abajo de
    // todo (debajo del input), que es el bug de "el oso queda abajo".
    hermanoOsoOriginal = osoEl.nextSibling;
    overlay.querySelector('.llamada-oso').appendChild(osoEl);
    osoEl.classList.add('en-llamada');
    window.setBearSize?.(_tamanoOso());
  }
}

function _tamanoOso() {
  // Grande pero sin comerse la pantalla ni tapar el botón de salir.
  return Math.round(Math.min(window.innerWidth * 0.72, window.innerHeight * 0.42, 420));
}

function _desmontarOverlay() {
  if (osoEl && contenedorOsoOriginal) {
    osoEl.classList.remove('en-llamada');
    // insertBefore con el hermano guardado lo devuelve a su lugar exacto
    // (arriba del chat). Si el hermano ya no existe, appendChild es el
    // comportamiento correcto de insertBefore(el, null).
    contenedorOsoOriginal.insertBefore(osoEl, hermanoOsoOriginal);
    window.setBearSize?.(window.BEAR_SIZE_DEFAULT || 220);
    window.setBearState?.('calm');
  }
  osoEl = null;
  contenedorOsoOriginal = null;
  hermanoOsoOriginal = null;

  overlay?.remove();
  overlay = null;
}
