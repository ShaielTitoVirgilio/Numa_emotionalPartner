// scripts/test_barge_in.mjs
// Prueba la lógica del barge-in (frontend/modules/bargeIn.js) con lecturas de
// micro inventadas, sin navegador. Correr: node scripts/test_barge_in.mjs

import assert from 'node:assert/strict';
import { crearDetectorBargeIn, rmsADb } from '../frontend/modules/bargeIn.js';

const PASO = 50;

/** Pasa una serie de lecturas [{db, sonando}] y devuelve en qué ms cortó (o null). */
function correr(lecturas, cfg) {
  const det = crearDetectorBargeIn(cfg);
  let t = 0;
  for (const { db, sonando = true } of lecturas) {
    t += PASO;
    if (det.muestra(db, sonando, t, PASO)) return { corteMs: t, det };
  }
  return { corteMs: null, det };
}

const repetir = (n, lectura) => Array.from({ length: n }, () => ({ ...lectura }));
const eco = (n, db = -40) => repetir(n, { db, sonando: true });

// 1. Solo el eco de Numa (con fluctuación): nunca corta.
{
  const lecturas = [...eco(10)];
  for (let i = 0; i < 200; i++) lecturas.push({ db: -40 + (i % 5) * 2, sonando: true });
  const { corteMs, det } = correr(lecturas);
  assert.equal(corteMs, null, 'el eco solo no tiene que cortar');
  assert.ok(Math.abs(det.estado().ecoDb - -40) < 1, 'el eco se calibra cerca de -40');
}

// 2. El usuario habla encima, fuerte y sostenido: corta en ~250ms.
{
  const { corteMs } = correr([...eco(10), ...repetir(20, { db: -15 })]);
  assert.ok(corteMs !== null, 'tiene que cortar');
  const msHablando = corteMs - 10 * PASO;
  assert.ok(msHablando >= 250 && msHablando <= 300, `cortó a los ${msHablando}ms`);
}

// 3. Un pico suelto (tos, portazo): no corta.
{
  const lecturas = [...eco(10), ...repetir(3, { db: -10 }), ...eco(40)];
  assert.equal(correr(lecturas).corteMs, null, 'un pico de 150ms no corta');
}

// 4. Voz con bajones cortos entre sílabas: corta igual.
{
  const silabas = [];
  for (let i = 0; i < 6; i++) silabas.push({ db: -15 }, { db: -15 }, { db: -45 });
  assert.ok(correr([...eco(10), ...silabas]).corteMs !== null, 'los bajones de 50ms no reinician');
}

// 5. Eco casi nulo (buen AEC) + ruido de sala por debajo del piso: no corta.
{
  const lecturas = [...eco(10, -70), ...repetir(100, { db: -35 })];
  const { corteMs, det } = correr(lecturas);
  assert.equal(corteMs, null, 'ruido de sala bajo el piso no corta');
  assert.equal(det.estado().umbralDb, -26, 'con eco bajo manda el piso');
}

// 6. No calibra mientras no suena nada (Cartesia todavía sintetizando).
{
  const lecturas = [...repetir(30, { db: -15, sonando: false })];
  const { corteMs, det } = correr(lecturas);
  assert.equal(corteMs, null, 'sin calibrar no corta nunca');
  assert.equal(det.estado().calibrando, true);
}

// 7. Ajustes del panel de debug pisan los defaults.
{
  const { det } = correr(eco(12, -40), { margenDb: 20, pisoDb: -50 });
  assert.equal(Math.round(det.estado().umbralDb), -20, 'umbral = eco + margen ajustado');
}

assert.equal(Math.round(rmsADb(0.028)), -31);
assert.equal(rmsADb(0), -100);

console.log('barge-in: 7 casos OK');
