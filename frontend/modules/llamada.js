// modules/llamada.js
// Modo llamada: hablás y Numa te contesta hablando, sin botones de por medio.
// El chat desaparece y queda solo Numa grande en el centro de la pantalla.
// Es el puerto web de numa-mobile/src/components/LlamadaOverlay.tsx.
//
// Ciclo (estrictamente secuencial, nunca escucha y habla a la vez):
//
//   escuchando ──(silencio)──> pensando ──> hablando ──(fin)──> escuchando
//        ↑                                                          │
//        └──────────────────────────────────────────────────────────┘
//
// Un turno es UN request: el audio va a /chat/stream/voz, el servidor lo
// transcribe y devuelve la respuesta en streaming (NDJSON), cada oración con
// su pedido a Cartesia ya armado (emoción, velocidad, risa). Numa empieza a
// hablar apenas llega la primera.
//
// Para interrumpirla se le HABLA ENCIMA (barge-in, ver bargeIn.js): el micro
// sigue abierto mientras Numa habla, pero esa escucha NO graba — solo mide el
// volumen para distinguir la voz del usuario del eco de Numa. Al detectarla,
// Numa se calla y arranca un turno de escucha normal. Tocar la pantalla
// también la corta (queda de respaldo).
//
// En producción solo está para las cuentas de LLAMADA_EMAILS (backend): el
// botón aparece si /llamada/estado lo habilita (ver initLlamada).

import { authHeaders } from './utils.js';
import { contextoParaLlamada, registrarTurnoLlamada } from './chat.js';
import {
  hablar, detenerHabla, despertarVoz, alTerminarDeHablar, marcarFinDelStream,
  actualizarVoces, rearmarVoz, vozListaParaLlamada, alFallarVoz, sonandoAhora,
} from './voz.js';
import { crearDetectorBargeIn, rmsADb, BARGE_IN_DEFAULTS } from './bargeIn.js';

// ============================================
// AFINADO DE LA DETECCIÓN DE VOZ (VAD)
// ============================================

// Volumen RMS por encima del cual hay VOZ (no ruido ambiente). Más alto que
// el del dictado (0.015): en una llamada el ruido de fondo no tiene que
// contar como que el usuario sigue hablando, si no nunca corta.
const UMBRAL_VOZ = 0.028;

// Silencio que da por terminado el turno del usuario. 1.5s, el mismo que la
// app tras probarla en teléfonos: con 1s cortaba entre oración y oración.
const SILENCIO_PARA_CORTAR_MS = 1500;

const INTERVALO_CHEQUEO_MS = 100;

// Voz acumulada mínima para mandar el turno: una tos o un portazo no gastan
// una request.
const MIN_VOZ_ACUMULADA_MS = 400;

// Tope duro de un turno, por si el VAD no corta nunca.
const MAX_TURNO_MS = 25000;

// Lo que Numa dice antes de cortar cuando la respuesta es la de contención:
// los teléfonos de ayuda tienen que poder TOCARSE, y eso solo pasa en la
// tarjeta del chat.
const FRASE_PUENTE_CRISIS =
  'Perdoná que corte así la charla, pero esto es importante de verdad. ' +
  'Te dejo algo en pantalla, miralo.';
const VOZ_PUENTE_CRISIS = { transcript: FRASE_PUENTE_CRISIS, emotion: 'sympathetic', speed: 0.9 };

// ============================================
// ESTADO
// ============================================

let habilitada = false;     // la cuenta tiene el modo llamada (ver initLlamada)
let enLlamada = false;
let estado = 'inactivo';    // escuchando | pensando | hablando | inactivo

let stream = null;          // MediaStream del micro, se pide UNA vez por llamada
let mediaRecorder = null;
let audioChunks = [];
let mimeGrabacion = '';

let audioContext = null;
let analyserNode = null;
let chequeoInterval = null;
let timeoutTurno = null;

let silencioDesde = null;
let vozAcumuladaMs = 0;
let yaHablo = false;
let ultimoChequeo = null;

// Barge-in (ver bargeIn.js). Un detector nuevo por cada vez que Numa habla:
// el eco se recalibra en cada respuesta (el volumen pudo cambiar).
const INTERVALO_BARGE_IN_MS = 50;
let detectorBargeIn = null;
let chequeoBargeIn = null;
let ultimoChequeoBargeIn = null;

// Cada turno tiene un número; interrumpir lo avanza. Las oraciones que siguen
// llegando del turno interrumpido se ignoran: si no, Numa volvía a hablar
// encima de lo que el usuario está diciendo y le cortaba la grabación.
let turnoActual = 0;

// Panel con los dB en vivo para afinar el barge-in en el teléfono. Solo para
// las cuentas que /llamada/estado marca con debug (ver config.py).
let debugVoz = false;
let ultimoCorte = null;     // { db, umbralDb, ecoDb } del último barge-in
const CLAVE_AJUSTES = 'numa_barge_in_ajustes';

let tonoVozPrevio = null;   // el tono_voz del "final" anterior (ver app/voz_tono.py)
let crisisEnCurso = false;  // durante la contención no se puede interrumpir

let overlay = null;
let contenedorOsoOriginal = null;
let hermanoOsoOriginal = null;
let osoEl = null;

// Corta el request del turno en curso al salir de la llamada: si no, el
// servidor sigue generando una respuesta que nadie va a escuchar.
let abortoTurno = null;

// ============================================
// API PÚBLICA
// ============================================

/** Pregunta al backend si esta cuenta tiene el modo llamada y muestra (o no)
 *  el botón y la tarjeta de voces. Se llama al iniciar el chat. */
export async function initLlamada() {
  habilitada = false;
  try {
    const r = await fetch('/llamada/estado', { headers: await authHeaders() });
    if (r.ok) {
      const datos = await r.json();
      habilitada = Boolean(datos?.habilitada);
      debugVoz = habilitada && Boolean(datos?.debug);
    }
  } catch { /* sin respuesta: queda oculto */ }
  document.getElementById('llamada-btn')?.classList.toggle('hidden', !habilitada);
  return habilitada;
}

export function llamadaHabilitada() {
  return habilitada;
}

export function estaEnLlamada() {
  return enLlamada;
}

export async function abrirLlamada() {
  if (enLlamada || !habilitada) return;

  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    alert('Tu navegador no permite usar el micrófono.');
    return;
  }

  // Dentro del tap, antes de cualquier await: desbloquea el audio (iOS).
  despertarVoz();

  // Sin la voz de Numa no se abre (decisión de producto: nada de voz robótica).
  if (!(await vozListaParaLlamada())) {
    alert('La voz de Numa no está disponible en este momento. Probá de nuevo en un rato.');
    return;
  }

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (e) {
    console.error('No se pudo abrir el micrófono:', e);
    alert('No pude acceder al micrófono. Revisá los permisos del navegador.');
    return;
  }

  mimeGrabacion = _elegirMime();
  enLlamada = true;
  crisisEnCurso = false;
  tonoVozPrevio = null;
  abortoTurno = new AbortController();
  _montarOverlay();
  _prepararAnalizador();

  alTerminarDeHablar(() => {
    // Numa terminó de decir todo → le toca al usuario.
    if (enLlamada) _escuchar();
  });
  alFallarVoz(() => {
    // Sin créditos, sesión vencida o Cartesia caída a mitad de la llamada.
    if (!enLlamada) return;
    cerrarLlamada();
    alert('Se cortó la voz de Numa. Seguimos por el chat.');
  });

  _escuchar();
}

export function cerrarLlamada() {
  if (!enLlamada) return;
  enLlamada = false;

  abortoTurno?.abort();
  abortoTurno = null;

  _pararEscucha();
  _pararBargeIn();
  detenerHabla();
  alTerminarDeHablar(null);
  alFallarVoz(null);
  crisisEnCurso = false;

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

// Cambiar de pestaña, bloquear el teléfono o minimizar: se cuelga. Una
// llamada que "sigue" sin que el usuario la vea es peor que una que se corta.
document.addEventListener('visibilitychange', () => {
  if (document.hidden && enLlamada) cerrarLlamada();
});

// ============================================
// CICLO: ESCUCHAR
// ============================================

function _elegirMime() {
  // Safari no graba webm; Chrome/Firefox sí. El backend (Whisper) acepta los dos.
  for (const m of ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']) {
    if (MediaRecorder.isTypeSupported?.(m)) return m;
  }
  return '';
}

/** `porBargeIn`: el usuario ya está hablando (se lo detectó encima de Numa),
 *  así que el turno arranca con su voz ya contada — si no, una frase corta
 *  dicha justo al interrumpir no llegaba a MIN_VOZ_ACUMULADA_MS y se perdía. */
function _escuchar(porBargeIn = false) {
  if (!enLlamada || !stream) return;

  // La llamada sigue: si se interrumpió a Numa, la voz quedó silenciada.
  rearmarVoz();
  _setEstado('escuchando');

  audioChunks = [];
  silencioDesde = null;
  vozAcumuladaMs = porBargeIn ? MIN_VOZ_ACUMULADA_MS : 0;
  yaHablo = porBargeIn;
  ultimoChequeo = null;

  try {
    mediaRecorder = mimeGrabacion
      ? new MediaRecorder(stream, { mimeType: mimeGrabacion })
      : new MediaRecorder(stream);
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

    // Sin voz suficiente (ruido, silencio): se vuelve a escuchar sin gastar
    // una request.
    if (vozAcumuladaMs < MIN_VOZ_ACUMULADA_MS) {
      _escuchar();
      return;
    }

    const tipo = mediaRecorder?.mimeType || mimeGrabacion || 'audio/webm';
    _procesarTurno(new Blob(audioChunks, { type: tipo }), tipo);
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

  // Tiempo REAL desde el chequeo anterior: el navegador estrangula los
  // setInterval con la pestaña en segundo plano, y contando ticks la voz
  // acumulada quedaba corta. El tope evita que una suspensión cuente de golpe.
  const ahora = Date.now();
  const delta = ultimoChequeo === null
    ? INTERVALO_CHEQUEO_MS
    : Math.min(ahora - ultimoChequeo, INTERVALO_CHEQUEO_MS * 5);
  ultimoChequeo = ahora;

  const rms = _rmsActual();
  _pintarNivel(rms);
  if (debugVoz) _pintarDebug(rmsADb(rms));

  if (rms >= UMBRAL_VOZ) {
    yaHablo = true;
    vozAcumuladaMs += delta;
    silencioDesde = null;
    return;
  }

  // No se corta hasta que el usuario haya dicho ALGO en este turno.
  if (!yaHablo) return;

  if (silencioDesde === null) {
    silencioDesde = ahora;
  } else if (ahora - silencioDesde >= SILENCIO_PARA_CORTAR_MS) {
    _cortarTurno();
  }
}

function _rmsActual() {
  const datos = new Float32Array(analyserNode.fftSize);
  analyserNode.getFloatTimeDomainData(datos);
  let suma = 0;
  for (let i = 0; i < datos.length; i++) suma += datos[i] * datos[i];
  return Math.sqrt(suma / datos.length);
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

/** Numa se calla y te toca a vos. Durante la contención no: ese mensaje
 *  tiene que terminar de decirse. */
function _interrumpir(porBargeIn) {
  if (!enLlamada || estado !== 'hablando' || crisisEnCurso) return;
  turnoActual++;   // lo que siga llegando del turno cortado ya no se dice
  _pararBargeIn();
  detenerHabla();
  _escuchar(porBargeIn);
}

/** Tocar la pantalla mientras Numa habla (respaldo del barge-in). */
function _interrumpirTocando(e) {
  if (e?.target?.closest?.('.llamada-salir, .llamada-debug')) return;
  _interrumpir(false);
}

// ============================================
// BARGE-IN: hablarle encima a Numa
// ============================================

function _empezarBargeIn() {
  if (chequeoBargeIn || !analyserNode) return;
  detectorBargeIn = crearDetectorBargeIn(_leerAjustes());
  ultimoChequeoBargeIn = null;
  chequeoBargeIn = setInterval(_chequearBargeIn, INTERVALO_BARGE_IN_MS);
}

function _pararBargeIn() {
  clearInterval(chequeoBargeIn);
  chequeoBargeIn = null;
  detectorBargeIn = null;
}

function _chequearBargeIn() {
  if (!enLlamada || !analyserNode || !detectorBargeIn || estado !== 'hablando' || crisisEnCurso) return;

  // Mismo motivo que en _chequearVolumen: tiempo real, no ticks.
  const ahora = Date.now();
  const delta = ultimoChequeoBargeIn === null
    ? INTERVALO_BARGE_IN_MS
    : Math.min(ahora - ultimoChequeoBargeIn, INTERVALO_BARGE_IN_MS * 4);
  ultimoChequeoBargeIn = ahora;

  const db = rmsADb(_rmsActual());
  const cortar = detectorBargeIn.muestra(db, sonandoAhora(), ahora, delta);
  _pintarDebug(db);

  if (cortar) {
    const { umbralDb, ecoDb } = detectorBargeIn.estado();
    ultimoCorte = { db, umbralDb, ecoDb };
    _interrumpir(true);
  }
}

// ============================================
// CICLO: PENSAR (audio → STT + LLM en un solo request) Y HABLAR
// ============================================

async function _procesarTurno(blob, tipo) {
  _setEstado('pensando');
  const miTurno = ++turnoActual;
  // false = el usuario interrumpió este turno (o salió de la llamada).
  const vigente = () => enLlamada && miTurno === turnoActual;

  let huboCrisis = false;
  let textoCrisis = null;
  let seEncoloAlgo = false;
  let textoUsuario = '';
  let mensaje = '';
  let final = null;
  let vacio = false;

  try {
    const ctxChat = contextoParaLlamada();
    const extension = tipo.includes('mp4') ? 'm4a' : 'webm';
    const form = new FormData();
    form.append('audio', blob, `voz.${extension}`);
    form.append('payload', JSON.stringify({
      conversation: ctxChat.conversation,
      perfil: ctxChat.perfil,
      ultimo_mood: ctxChat.ultimo_mood,
      tono_voz_previo: tonoVozPrevio,
    }));

    const res = await fetch('/chat/stream/voz', {
      method: 'POST',
      headers: await authHeaders(),
      body: form,
      signal: abortoTurno?.signal,
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

    // Lectura incremental del NDJSON (EventSource no deja mandar Authorization).
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    const procesarLinea = (linea) => {
      if (!linea.trim()) return;
      let ev;
      try { ev = JSON.parse(linea); } catch { return; }

      if (ev.type === 'texto_usuario') {
        textoUsuario = ev.text || '';
      } else if (ev.type === 'vacio') {
        vacio = true;
      } else if (ev.type === 'delta') {
        const limpio = (ev.text || '').replace(/\[EJERCICIO:\s*\w+\]/, '').trim();
        if (!limpio) return;
        mensaje = mensaje ? `${mensaje} ${limpio}` : limpio;
        if (!vigente() || huboCrisis) return;
        seEncoloAlgo = true;
        if (estado !== 'hablando') _setEstado('hablando');
        hablar(limpio, ev.voz && typeof ev.voz.transcript === 'string' ? ev.voz : undefined);
      } else if (ev.type === 'voz') {
        if (vigente() && !huboCrisis) actualizarVoces(ev.voces);
      } else if (ev.type === 'crisis') {
        huboCrisis = true;
        textoCrisis = ev.text || '';
      } else if (ev.type === 'final') {
        final = ev;
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buffer.indexOf('\n')) >= 0) {
        procesarLinea(buffer.slice(0, nl));
        buffer = buffer.slice(nl + 1);
      }
    }
    procesarLinea(buffer);
  } catch (e) {
    if (!vigente() || e?.name === 'AbortError') return;
    console.error('Error hablando con Numa:', e);
    _setEstado('hablando');
    hablar('Perdón, se me cortó. ¿Me lo decís de nuevo?');
    // Si algo ya se había encolado, se espera a que termine de sonar igual.
    marcarFinDelStream();
    return;
  }

  if (!enLlamada) return;

  if (vacio) {
    // No se entendió nada (silencio, ruido): el servidor ni gastó un turno.
    _escuchar();
    return;
  }

  // La crisis se atiende AUNQUE el usuario haya interrumpido este turno: el
  // router puede cortar la respuesta a mitad de camino (ver /chat/stream), y
  // para entonces el usuario ya pudo haberle hablado encima a Numa. Lo que se
  // esté grabando se descarta.
  if (huboCrisis && textoCrisis) {
    // La contención NO se dice en voz: lleva teléfonos que tienen que poder
    // tocarse. Queda la tarjeta en el chat, Numa avisa y se corta.
    turnoActual++;
    _pararEscucha();
    _pararBargeIn();
    registrarTurnoLlamada(textoUsuario, { message: textoCrisis, mood: 'sad', risk_level: 'high' });
    crisisEnCurso = true;
    _setEstado('hablando');
    detenerHabla();
    alTerminarDeHablar(() => {
      alTerminarDeHablar(null);
      cerrarLlamada();
    });
    setTimeout(() => {
      if (!enLlamada) return;
      rearmarVoz();
      hablar(FRASE_PUENTE_CRISIS, VOZ_PUENTE_CRISIS);
      marcarFinDelStream();
    }, 120);
    return;
  }

  if (final) {
    tonoVozPrevio = final.tono_voz ?? null;
    if (textoUsuario && mensaje) {
      registrarTurnoLlamada(textoUsuario, {
        message: mensaje,
        mood: final.mood,
        risk_level: final.risk_level,
        suggested_action: final.suggested_action,
        nuevas_memorias: final.nuevas_memorias,
      });
    }
  }

  // Interrumpido: el turno nuevo (el que el usuario está diciendo ahora)
  // maneja el micro. Este no reabre la escucha, ni cierra la llamada por un
  // ejercicio que Numa no llegó a ofrecer en voz.
  if (!vigente()) return;

  if (final) {
    // Ejercicio sugerido: un ejercicio necesita pantalla, así que Numa
    // termina de decir la frase con la que lo ofrece y se vuelve al chat,
    // donde ya quedó el botón para empezarlo. El aviso de fin se cambia
    // ANTES de marcar el fin del stream: si Numa ya terminó de hablar,
    // marcarFinDelStream() lo dispara en el acto.
    if (final.suggested_action && final.suggested_action !== 'none') {
      alTerminarDeHablar(() => {
        alTerminarDeHablar(null);
        cerrarLlamada();
      });
    }
  }

  // Nada para decir (respuesta vacía): no hay fin de habla que esperar.
  if (!seEncoloAlgo) {
    if (final?.suggested_action && final.suggested_action !== 'none') cerrarLlamada();
    else _escuchar();
    return;
  }

  // El stream ya se leyó entero: no llega ninguna oración más en este turno.
  // Cuando Numa termine de decir lo encolado, el aviso de fin reabre el
  // micrófono (o cierra la llamada, si sugirió un ejercicio). Va después de
  // la crisis a propósito: ahí no hay que reabrir el micrófono.
  marcarFinDelStream();
}

// ============================================
// UI
// ============================================

const TEXTO_ESTADO = {
  escuchando: 'Te escucho…',
  pensando:   'Pensando…',
  hablando:   'Hablale encima para interrumpir',
};

const OSO_POR_ESTADO = {
  escuchando: 'listening',
  pensando:   'thinking',
  hablando:   'hablando',
};

function _setEstado(nuevo) {
  estado = nuevo;
  window.setBearState?.(OSO_POR_ESTADO[nuevo] || 'calm');

  const label = overlay?.querySelector('.llamada-estado');
  if (label) label.textContent = (nuevo === 'hablando' && crisisEnCurso) ? '' : (TEXTO_ESTADO[nuevo] ?? '');

  overlay?.classList.toggle('escuchando', nuevo === 'escuchando');
  if (nuevo !== 'escuchando') _pintarNivel(0);

  if (nuevo === 'hablando' && !crisisEnCurso) _empezarBargeIn();
  else _pararBargeIn();
  if (debugVoz) _pintarDebug(null);
}

/** Halo que crece con el volumen de tu voz, para que se vea que te escucha. */
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
    ${debugVoz ? _htmlDebug() : ''}
  `;
  overlay.querySelector('.llamada-salir').onclick = cerrarLlamada;
  // Toda la pantalla es tocable para interrumpir, no solo el oso.
  overlay.addEventListener('click', _interrumpirTocando);
  if (debugVoz) _conectarDebug();
  document.body.appendChild(overlay);

  // Se MUEVE el canvas del oso (no se crea otro): conserva el contexto WebGL.
  osoEl = document.getElementById('bear-container');
  if (osoEl) {
    contenedorOsoOriginal = osoEl.parentElement;
    hermanoOsoOriginal = osoEl.nextSibling;
    overlay.querySelector('.llamada-oso').appendChild(osoEl);
    osoEl.classList.add('en-llamada');
    window.setBearSize?.(_tamanoOso());
  }
}

function _tamanoOso() {
  return Math.round(Math.min(window.innerWidth * 0.72, window.innerHeight * 0.42, 420));
}

function _desmontarOverlay() {
  if (osoEl && contenedorOsoOriginal) {
    osoEl.classList.remove('en-llamada');
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

// ============================================
// DEBUG DEL BARGE-IN (solo cuentas con debug)
// ============================================
//
// Muestra en vivo lo que mide el micro y deja ajustar los tres números que
// importan sin hacer un deploy. Los ajustes quedan guardados en ESTE
// navegador (localStorage); "Reset" vuelve a los de bargeIn.js. Cuando unos
// valores anden bien, se pasan a BARGE_IN_DEFAULTS y se suben.

const AJUSTABLES = [
  { clave: 'pisoDb',      nombre: 'Piso',      paso: 2,  unidad: 'dB' },
  { clave: 'margenDb',    nombre: 'Margen',    paso: 1,  unidad: 'dB' },
  { clave: 'sostenidoMs', nombre: 'Sostenido', paso: 50, unidad: 'ms' },
];

function _leerAjustes() {
  try {
    const guardado = JSON.parse(localStorage.getItem(CLAVE_AJUSTES) || '{}');
    const ajustes = {};
    for (const { clave } of AJUSTABLES) {
      if (typeof guardado[clave] === 'number') ajustes[clave] = guardado[clave];
    }
    return ajustes;
  } catch {
    return {};
  }
}

function _guardarAjustes(ajustes) {
  try { localStorage.setItem(CLAVE_AJUSTES, JSON.stringify(ajustes)); } catch { /* noop */ }
}

function _htmlDebug() {
  const filas = AJUSTABLES.map(({ clave, nombre }) => `
    <div class="llamada-debug-fila">
      <span>${nombre}</span>
      <button data-ajuste="${clave}" data-signo="-1">−</button>
      <b data-valor="${clave}"></b>
      <button data-ajuste="${clave}" data-signo="1">+</button>
    </div>`).join('');
  return `
    <div class="llamada-debug">
      <div data-debug="vivo"></div>
      <div data-debug="corte"></div>
      ${filas}
      <button class="llamada-debug-reset" data-reset="1">Reset</button>
    </div>`;
}

function _conectarDebug() {
  const panel = overlay.querySelector('.llamada-debug');
  // Tocar el panel NO interrumpe a Numa (ver _interrumpirTocando).
  panel.addEventListener('click', (e) => {
    const boton = e.target.closest('button');
    if (!boton) return;
    let ajustes = _leerAjustes();
    if (boton.dataset.reset) {
      ajustes = {};
    } else {
      const { clave, paso } = AJUSTABLES.find(a => a.clave === boton.dataset.ajuste);
      const actual = ajustes[clave] ?? BARGE_IN_DEFAULTS[clave];
      ajustes[clave] = actual + paso * Number(boton.dataset.signo);
      if (clave === 'sostenidoMs') ajustes[clave] = Math.max(50, ajustes[clave]);
    }
    _guardarAjustes(ajustes);
    // Rige desde la próxima vez que Numa hable (el detector se arma ahí).
    _pintarDebug(null);
  });
  _pintarDebug(null);
}

function _fmt(db) {
  return db === null || db === undefined ? '—' : `${Math.round(db)}`;
}

function _pintarDebug(db) {
  if (!debugVoz || !overlay) return;
  const panel = overlay.querySelector('.llamada-debug');
  if (!panel) return;

  const ajustes = { ...BARGE_IN_DEFAULTS, ..._leerAjustes() };
  for (const { clave, unidad } of AJUSTABLES) {
    const el = panel.querySelector(`[data-valor="${clave}"]`);
    if (el) el.textContent = `${ajustes[clave]}${unidad}`;
  }

  const vivo = panel.querySelector('[data-debug="vivo"]');
  if (vivo) {
    let linea = `${estado} · mic ${_fmt(db)}dB`;
    if (estado === 'hablando' && detectorBargeIn) {
      const st = detectorBargeIn.estado();
      linea += st.calibrando
        ? ` · calibrando eco${sonandoAhora() ? '' : ' (esperando audio)'}`
        : ` · eco ${_fmt(st.ecoDb)} · umbral ${_fmt(st.umbralDb)} · arriba ${Math.round(st.arribaMs)}ms`;
    } else if (estado === 'escuchando') {
      linea += ` · VAD ${_fmt(rmsADb(UMBRAL_VOZ))}`;
    }
    vivo.textContent = linea;
  }

  const corte = panel.querySelector('[data-debug="corte"]');
  if (corte) {
    corte.textContent = ultimoCorte
      ? `último corte: ${_fmt(ultimoCorte.db)}dB (umbral ${_fmt(ultimoCorte.umbralDb)}, eco ${_fmt(ultimoCorte.ecoDb)})`
      : 'último corte: —';
  }
}
