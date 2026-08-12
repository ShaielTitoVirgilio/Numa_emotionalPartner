// modules/voz.js
// Texto → voz con la Web Speech API del navegador (gratis, corre en el
// dispositivo, sin backend ni costo por request). Es la capa que usa el modo
// llamada (modules/llamada.js) para que Numa hable.
//
// Cuando exista la app React Native, esta es la ÚNICA pieza que se reemplaza:
// el equivalente es expo-speech (AVSpeechSynthesizer en iOS, TextToSpeech en
// Android) con la misma forma de uso — hablar(oracion) y un aviso de "terminó".
// El resto de la arquitectura de la llamada no cambia.

let vozElegida = null;
let vozDespierta = false;   // iOS: hace falta un speak() dentro de un gesto de usuario

// Cuántas frases quedan sin terminar de decir. Cuando llega a 0, la cola se
// vació → el modo llamada reabre el micro. Sin este contador no hay forma de
// saber cuándo le toca hablar al usuario.
let pendientes = 0;
let cbFinDeHabla = null;
let timerFallback = null;

const VOZ_LANG_PREFERIDA = ['es-AR', 'es-419', 'es-MX', 'es-US', 'es-ES'];

// Red de seguridad: en algunos navegadores 'onend' no dispara nunca (bug
// conocido de speechSynthesis, sobre todo si la pestaña pierde foco). Si eso
// pasa, el micro no se reabriría más y la llamada quedaría muerta. Estimamos
// la duración por largo de texto y forzamos el cierre con margen.
const MS_POR_CARACTER = 75;     // ~13 caracteres/segundo hablando en español
const MARGEN_FALLBACK_MS = 3000;

function _elegirVoz() {
  if (!vozDisponible()) return;
  const voces = window.speechSynthesis.getVoices();
  if (!voces.length) return;   // en varios navegadores tardan (evento voiceschanged)
  for (const lang of VOZ_LANG_PREFERIDA) {
    const encontrada = voces.find(v => v.lang === lang || v.lang === lang.replace('-', '_'));
    if (encontrada) { vozElegida = encontrada; return; }
  }
  vozElegida = voces.find(v => (v.lang || '').toLowerCase().startsWith('es')) || null;
}

if ('speechSynthesis' in window) {
  _elegirVoz();
  window.speechSynthesis.onvoiceschanged = _elegirVoz;
}

export function vozDisponible() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

/** Nombre de la voz que se está usando (para debug / mostrar en la UI). */
export function vozActual() {
  return vozElegida ? `${vozElegida.name} (${vozElegida.lang})` : 'default del sistema';
}

/** Desbloquea el motor de voz. Hay que llamarla dentro de un gesto real del
 * usuario (el tap que abre la llamada) — en iOS Safari, si no, el primer
 * speak() no suena. */
export function despertarVoz() {
  if (vozDespierta || !vozDisponible()) return;
  const u = new SpeechSynthesisUtterance(' ');
  u.volume = 0;
  window.speechSynthesis.speak(u);
  vozDespierta = true;
}

/** Registra a quién avisar cuando Numa termine de decir TODO lo encolado. */
export function alTerminarDeHablar(cb) {
  cbFinDeHabla = cb;
}

function _terminoUno() {
  pendientes = Math.max(0, pendientes - 1);
  if (pendientes === 0) {
    clearTimeout(timerFallback);
    timerFallback = null;
    const cb = cbFinDeHabla;
    if (cb) cb();
  }
}

/** Encola una oración para que Numa la diga. Llamadas sucesivas se encolan
 * solas en el motor del navegador: no hay que esperar a que termine una para
 * mandar la siguiente. */
export function hablar(texto) {
  const limpio = (texto || '').trim();
  if (!limpio || !vozDisponible()) return;

  const u = new SpeechSynthesisUtterance(limpio);
  u.lang = (vozElegida && vozElegida.lang) || 'es-AR';
  if (vozElegida) u.voice = vozElegida;
  u.rate = 1;
  u.onend = _terminoUno;
  u.onerror = _terminoUno;   // si falla una frase, no dejar la llamada colgada

  pendientes++;

  // Reprogramar el fallback con el total pendiente estimado.
  clearTimeout(timerFallback);
  const estimadoMs = limpio.length * MS_POR_CARACTER * Math.max(1, pendientes) + MARGEN_FALLBACK_MS;
  timerFallback = setTimeout(() => {
    if (pendientes > 0) {
      console.warn('voz: onend no disparó, forzando fin de habla (fallback)');
      pendientes = 0;
      const cb = cbFinDeHabla;
      if (cb) cb();
    }
  }, estimadoMs);

  window.speechSynthesis.speak(u);
}

/** Corta lo que Numa esté diciendo y vacía la cola. NO dispara el callback de
 * fin: se usa cuando el que corta es el usuario (salir de la llamada,
 * interrumpir), y ahí quien llama decide qué sigue. */
export function detenerHabla() {
  clearTimeout(timerFallback);
  timerFallback = null;
  pendientes = 0;
  if (vozDisponible()) window.speechSynthesis.cancel();
}

export function estaHablando() {
  return pendientes > 0 || (vozDisponible() && window.speechSynthesis.speaking);
}
