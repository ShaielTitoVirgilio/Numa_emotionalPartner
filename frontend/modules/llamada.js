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
// El micro NO escucha mientras Numa habla: en parlantes se escucharía a sí
// misma. Para interrumpirla se TOCA LA PANTALLA (igual que en la app).
//
// En producción solo está para las cuentas de LLAMADA_EMAILS (backend): el
// botón aparece si /llamada/estado lo habilita (ver initLlamada).

import { authHeaders } from './utils.js';
import { contextoParaLlamada, registrarTurnoLlamada } from './chat.js';
import {
  hablar, detenerHabla, despertarVoz, alTerminarDeHablar, marcarFinDelStream,
  actualizarVoces, rearmarVoz, vozListaParaLlamada, alFallarVoz,
} from './voz.js';

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
    if (r.ok) habilitada = Boolean((await r.json())?.habilitada);
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

function _escuchar() {
  if (!enLlamada || !stream) return;

  // La llamada sigue: si se interrumpió a Numa, la voz quedó silenciada.
  rearmarVoz();
  _setEstado('escuchando');

  audioChunks = [];
  silencioDesde = null;
  vozAcumuladaMs = 0;
  yaHablo = false;
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

  const datos = new Float32Array(analyserNode.fftSize);
  analyserNode.getFloatTimeDomainData(datos);

  let suma = 0;
  for (let i = 0; i < datos.length; i++) suma += datos[i] * datos[i];
  const rms = Math.sqrt(suma / datos.length);

  _pintarNivel(rms);

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

/** Tocar la pantalla mientras Numa habla: se calla y te toca a vos. Durante
 *  la contención no: ese mensaje tiene que terminar de decirse. */
function _interrumpirTocando(e) {
  if (e?.target?.closest?.('.llamada-salir')) return;
  if (!enLlamada || estado !== 'hablando' || crisisEnCurso) return;
  detenerHabla();
  _escuchar();
}

// ============================================
// CICLO: PENSAR (audio → STT + LLM en un solo request) Y HABLAR
// ============================================

async function _procesarTurno(blob, tipo) {
  _setEstado('pensando');

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
        if (!enLlamada || huboCrisis) return;
        seEncoloAlgo = true;
        if (estado !== 'hablando') _setEstado('hablando');
        hablar(limpio, ev.voz && typeof ev.voz.transcript === 'string' ? ev.voz : undefined);
      } else if (ev.type === 'voz') {
        if (enLlamada && !huboCrisis) actualizarVoces(ev.voces);
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
    if (!enLlamada || e?.name === 'AbortError') return;
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

  if (huboCrisis && textoCrisis) {
    // La contención NO se dice en voz: lleva teléfonos que tienen que poder
    // tocarse. Queda la tarjeta en el chat, Numa avisa y se corta.
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
  hablando:   'Tocá la pantalla para interrumpir',
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
  `;
  overlay.querySelector('.llamada-salir').onclick = cerrarLlamada;
  // Toda la pantalla es tocable para interrumpir, no solo el oso.
  overlay.addEventListener('click', _interrumpirTocando);
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
