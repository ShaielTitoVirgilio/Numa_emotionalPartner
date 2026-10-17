// modules/voz.js
// Texto → voz para el modo llamada, con Cartesia (sonic-3.6). Es el puerto
// web de numa-mobile/src/services/voz.ts: misma interfaz (hablar /
// detenerHabla / alTerminarDeHablar / marcarFinDelStream) y mismas reglas, así
// que modules/llamada.js no se entera de qué motor hay detrás.
//
// El navegador NO lleva la API key: pide a /tts/token un token de Cartesia de
// una hora, solo con permiso de TTS, y con ese token le pega directo a
// Cartesia (que acepta CORS desde cualquier origen). Así el audio no pasa por
// nuestro servidor.
//
// SIN FALLBACK A LA VOZ DEL NAVEGADOR, igual que en la app: una voz robótica
// rompe la premisa de Numa. Si Cartesia no está disponible antes de abrir la
// llamada, no se abre; si se cae en el medio, la llamada se cierra.
//
// Se reproduce con Web Audio (AudioContext + decodeAudioData) y no con
// <audio>: el contexto se desbloquea UNA vez en el tap que abre la llamada y
// después puede sonar sin más gestos del usuario (iOS Safari), y cortar a
// mitad de una oración es inmediato.
//
// Cartesia tarda ~0.3-0.6s en devolver cada audio: por eso se pide la oración
// siguiente mientras suena la actual, y el costo real queda solo en la primera.

import { authHeaders } from './utils.js';

// ── Catálogo de voces ────────────────────────────────────────────────
// Las mismas dos de la app (numa-mobile/src/services/vocesNuma.ts). La
// preferencia vive solo en este navegador: es comodidad, no un dato de perfil.
export const VOCES = [
  {
    id: '5c5ad5e7-1020-476b-8b91-fdcbe9cc313c',
    nombre: 'Daniela',
    descripcion: 'Calma y confianza',
    genero: 'femenina',
  },
  // La voz de Shaiel, clonada en Cartesia (es-AR). Las voces clonadas con
  // acento propio van con `locale`; el resto con `language` (Cartesia
  // rechaza los dos juntos).
  {
    id: 'ca26e167-e4e5-4212-b486-a22d9f0539cc',
    nombre: 'Shaiel',
    descripcion: 'Rioplatense y cercana',
    genero: 'masculina',
    locale: 'es-AR',
  },
];
export const VOZ_POR_DEFECTO = VOCES[0];
const CLAVE_VOZ = 'numa_voz_id';

export function vozPorId(id) {
  return VOCES.find(v => v.id === id) || VOZ_POR_DEFECTO;
}

export function leerVozElegida() {
  try { return vozPorId(localStorage.getItem(CLAVE_VOZ)); } catch { return VOZ_POR_DEFECTO; }
}

let vozActiva = leerVozElegida();

/** La elige la tarjeta "Voz de Numa" del perfil. Aplica a la próxima frase. */
export function elegirVoz(id) {
  vozActiva = vozPorId(id);
  try { localStorage.setItem(CLAVE_VOZ, vozActiva.id); } catch { /* sin storage: queda en memoria */ }
}

// ── Contexto de audio ────────────────────────────────────────────────
let ctx = null;

/** Crea/desbloquea el AudioContext. Llamarla DENTRO de un gesto del usuario
 *  (el tap que abre la llamada o el ▶ de una muestra). */
export function despertarVoz() {
  try {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === 'suspended') ctx.resume().catch(() => {});
  } catch { /* sin Web Audio no hay voz: _sintetizar fallará y se avisa */ }
}

// ── Estado del habla ─────────────────────────────────────────────────
// `pendientes` cuenta oraciones YA LLEGADAS sin terminar de decir. No alcanza
// para saber que Numa terminó: si la primera oración es corta, termina de
// sonar antes de que la segunda llegue por la red. Por eso además hace falta
// `streamTerminado`, que marca quien llama (marcarFinDelStream) cuando el
// stream del turno ya se leyó entero. Recién con los dos se reabre el micro.
let pendientes = 0;
let streamTerminado = true;
let cbFinDeHabla = null;
let timerFallback = null;

// Red de seguridad: si el fin de una oración nunca llega, la llamada quedaría
// muda para siempre. Se estima la duración por largo de texto.
const MS_POR_CARACTER = 75;
const MARGEN_FALLBACK_MS = 3000;

// Silenciado hasta nuevo aviso: lo prende detenerHabla() y lo apaga
// rearmarVoz(). Evita que una oración que llega tarde del stream vuelva a
// hablar después de salir de la llamada.
let silenciado = false;
// 401/403 (sesión) o 402/429 (sin créditos): reintentar no lo arregla.
let fatalDetectado = false;

let cbFalloVoz = null;
/** Se avisa acá cuando la voz se cae EN MEDIO de una llamada. */
export function alFallarVoz(cb) { cbFalloVoz = cb; }

export function alTerminarDeHablar(cb) { cbFinDeHabla = cb; }

/** Vuelve a habilitar el habla después de un detenerHabla(). Lo llaman la
 *  apertura de la llamada y cada vuelta a escuchar: interrumpir también pasa
 *  por detenerHabla(), y sin rearmar la llamada quedaría muda. */
export function rearmarVoz() {
  silenciado = false;
  fatalDetectado = false;
}

/** Ya no va a llegar ninguna oración más en este turno. */
export function marcarFinDelStream() {
  streamTerminado = true;
  if (pendientes === 0) {
    clearTimeout(timerFallback);
    timerFallback = null;
    cbFinDeHabla?.();
  }
}

function _reprogramarFallback(largo) {
  clearTimeout(timerFallback);
  const estimadoMs = largo * MS_POR_CARACTER * Math.max(1, pendientes) + MARGEN_FALLBACK_MS;
  timerFallback = setTimeout(() => {
    if (pendientes > 0) {
      console.warn('voz: el fin de habla no llegó, se fuerza (fallback)');
      pendientes = 0;
      _vaciarCola();
      if (streamTerminado) cbFinDeHabla?.();
    }
  }, estimadoMs);
}

function _terminoUno() {
  pendientes = Math.max(0, pendientes - 1);
  if (pendientes === 0 && streamTerminado) {
    clearTimeout(timerFallback);
    timerFallback = null;
    cbFinDeHabla?.();
  }
}

// ── Token de Cartesia ────────────────────────────────────────────────
let token = null;
let tokenVence = 0;
let tokenEnVuelo = null;

async function _token() {
  if (token && Date.now() < tokenVence) return token;
  if (tokenEnVuelo) return tokenEnVuelo;
  tokenEnVuelo = (async () => {
    try {
      const r = await fetch('/tts/token', { headers: await authHeaders() });
      if (!r.ok) return null;
      const d = await r.json();
      if (!d?.habilitado || !d?.token) return null;
      token = d.token;
      tokenVence = Date.now() + (d.expira_en_s ?? 3000) * 1000;
      return token;
    } catch {
      return null;
    } finally {
      tokenEnVuelo = null;
    }
  })();
  return tokenEnVuelo;
}

/** Chequeo previo a abrir la llamada. Además precalienta el token, así la
 *  primera oración no paga ese pedido. */
export async function vozListaParaLlamada() {
  const ok = (await _token()) !== null;
  if (ok) rearmarVoz();
  return ok;
}

/** Al cerrar sesión: el token siguiente se pide con la sesión nueva. */
export function olvidarTokenVoz() {
  token = null;
  tokenVence = 0;
}

/** Reporta el fallo al backend (que lo manda a Sentry). Solo el motivo y el
 *  código HTTP, nunca texto de la charla. */
async function _reportarFallo(motivo, status) {
  try {
    await fetch('/tts/fallo', {
      method: 'POST',
      headers: await authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ motivo: String(motivo).slice(0, 60), status: status ?? null }),
    });
  } catch { /* si ni el reporte sale, no hay nada más que hacer */ }
}

// ── Síntesis ─────────────────────────────────────────────────────────
// Límites que acepta Cartesia: afuera del rango falla el pedido entero.
const VELOCIDAD_MIN = 0.6;
const VELOCIDAD_MAX = 1.5;

/** `voz` es lo que arma el backend por oración (app/voz_tono.py): transcript
 *  con [laughter]/<break/>, emotion y speed. Sin `voz` (la muestra del
 *  perfil, las frases fijas), sale con el tono por defecto. */
function _cuerpoTTS(texto, voz, vozNuma) {
  const config = { volume: 2.0 };
  if (voz && Number.isFinite(voz.speed)) {
    config.speed = Math.min(VELOCIDAD_MAX, Math.max(VELOCIDAD_MIN, voz.speed));
  }
  if (voz?.emotion) config.emotion = voz.emotion;
  return {
    model_id: 'sonic-3.6',
    transcript: (voz?.transcript || '').trim() || texto,
    voice: { mode: 'id', id: vozNuma.id },
    output_format: { container: 'mp3', sample_rate: 44100, bit_rate: 128000 },
    ...(vozNuma.locale ? { locale: vozNuma.locale } : { language: 'es' }),
    // 2.0 es el máximo de Cartesia: en altavoz o con ruido, mejor pasarse.
    generation_config: config,
  };
}

async function _sintetizarUnaVez(texto, voz, vozNuma) {
  const t = await _token();
  if (!t) { fatalDetectado = true; return null; }
  let r;
  try {
    r = await fetch('https://api.cartesia.ai/tts/bytes', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${t}`,
        'Cartesia-Version': '2026-08-14',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(_cuerpoTTS(texto, voz, vozNuma)),
    });
  } catch (e) {
    _reportarFallo(`red: ${e?.message || e}`);
    return null;   // transitorio: _sintetizar reintenta
  }
  if (!r.ok) {
    if (r.status === 401 || r.status === 403) { token = null; tokenVence = 0; }
    if ([401, 403, 402, 429].includes(r.status)) fatalDetectado = true;
    _reportarFallo('tts_http', r.status);
    return null;
  }
  try {
    const bytes = await r.arrayBuffer();
    if (!bytes.byteLength) { _reportarFallo('respuesta_vacia'); return null; }
    despertarVoz();
    return await ctx.decodeAudioData(bytes);
  } catch (e) {
    _reportarFallo(`decode: ${e?.message || e}`);
    return null;
  }
}

async function _sintetizar(texto, voz, vozNuma = vozActiva) {
  const primera = await _sintetizarUnaVez(texto, voz, vozNuma);
  if (primera || fatalDetectado) return primera;
  // Un solo reintento corto: si fue un tropiezo de red se resuelve acá; si
  // no, mejor saltear la oración que dejar al usuario en silencio.
  await new Promise(res => setTimeout(res, 250));
  return _sintetizarUnaVez(texto, voz, vozNuma);
}

// ── Cola de reproducción ─────────────────────────────────────────────
const cola = [];          // { texto, voz, audio: Promise<AudioBuffer|null> | undefined }
let reproduciendo = false;
let fuenteActual = null;
let abortarReproduccion = null;

function _vaciarCola() {
  cola.length = 0;
  if (fuenteActual) {
    fuenteActual.onended = null;
    try { fuenteActual.stop(); } catch { /* ya terminó */ }
    fuenteActual = null;
  }
  // Destrabar el await de _reproducir: si no, `reproduciendo` quedaría en
  // true para siempre y la llamada se quedaría muda después de interrumpir.
  const abortar = abortarReproduccion;
  abortarReproduccion = null;
  reproduciendo = false;
  abortar?.();
}

async function _procesarCola() {
  if (reproduciendo) return;
  reproduciendo = true;
  try {
    while (cola.length && !silenciado) {
      const item = cola[0];
      if (!item.audio) item.audio = _sintetizar(item.texto, item.voz);
      // Precarga de la siguiente mientras suena esta.
      if (cola[1] && !cola[1].audio) cola[1].audio = _sintetizar(cola[1].texto, cola[1].voz);

      const buffer = await item.audio;
      cola.shift();
      if (silenciado) break;

      if (!buffer) {
        _terminoUno();
        if (fatalDetectado) {
          _reportarFallo('voz_no_disponible');
          cbFalloVoz?.();
          break;
        }
        // Tropiezo puntual: se saltea esta oración y la llamada sigue.
        _reportarFallo('oracion_salteada');
        continue;
      }
      await _reproducir(buffer);
    }
  } finally {
    reproduciendo = false;
  }
}

function _reproducir(buffer) {
  return new Promise(resolve => {
    let listo = false;
    const terminar = () => {
      if (listo) return;
      listo = true;
      abortarReproduccion = null;
      fuenteActual = null;
      _terminoUno();
      resolve();
    };
    // Corte desde afuera (interrumpir/salir): NO cuenta como fin de habla.
    abortarReproduccion = () => {
      if (listo) return;
      listo = true;
      resolve();
    };
    try {
      const fuente = ctx.createBufferSource();
      fuente.buffer = buffer;
      fuente.connect(ctx.destination);
      fuente.onended = terminar;
      fuenteActual = fuente;
      fuente.start();
    } catch {
      terminar();
    }
  });
}

/** Encola una oración. `voz` es el pedido a Cartesia que arma el backend. */
export function hablar(texto, voz) {
  const limpio = (texto || '').trim();
  if (!limpio || silenciado) return;
  pendientes++;
  streamTerminado = false;
  _reprogramarFallback(limpio.length);
  // Se piden ya la primera y la segunda de la tanda; las demás las va
  // pidiendo _procesarCola de a una, y así pueden tomar el tono tardío.
  const item = { texto: limpio, voz, audio: undefined };
  if (cola.length <= 1) item.audio = _sintetizar(limpio, voz);
  cola.push(item);
  _procesarCola();
}

/** Tono tardío del router: reemplaza la voz de las oraciones que todavía no
 *  se le pidieron a Cartesia (se emparejan por `indice`). */
export function actualizarVoces(voces) {
  const porIndice = new Map();
  for (const v of voces || []) {
    if (v && typeof v.indice === 'number' && typeof v.transcript === 'string') porIndice.set(v.indice, v);
  }
  for (const item of cola) {
    if (item.audio !== undefined || item.voz?.indice == null) continue;
    const nueva = porIndice.get(item.voz.indice);
    if (nueva) item.voz = nueva;
  }
}

/** Corta lo que Numa esté diciendo y vacía la cola. NO dispara el fin de
 *  habla: quien corta (interrumpir, salir) decide qué sigue. */
export function detenerHabla() {
  silenciado = true;
  clearTimeout(timerFallback);
  timerFallback = null;
  pendientes = 0;
  streamTerminado = true;
  _vaciarCola();
}

export function estaHablando() {
  return pendientes > 0;
}

// ── Muestra para elegir voz ──────────────────────────────────────────
let fuenteMuestra = null;

/** Reproduce una frase con una voz, por fuera de la cola de la llamada.
 *  Devuelve true si sonó. Llamarla desde un tap (desbloquea el audio). */
export async function reproducirMuestra(voz, texto) {
  despertarVoz();
  fatalDetectado = false;
  const buffer = await _sintetizar(texto, undefined, voz);
  if (!buffer) return false;
  try {
    if (fuenteMuestra) { try { fuenteMuestra.stop(); } catch { /* ya terminó */ } }
    fuenteMuestra = ctx.createBufferSource();
    fuenteMuestra.buffer = buffer;
    fuenteMuestra.connect(ctx.destination);
    fuenteMuestra.start();
    return true;
  } catch {
    return false;
  }
}
