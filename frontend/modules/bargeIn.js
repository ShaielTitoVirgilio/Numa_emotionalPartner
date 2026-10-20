// modules/bargeIn.js
// Barge-in: cortar a Numa HABLÁNDOLE ENCIMA, sin tocar la pantalla.
//
// Es la misma idea que DetectorBargeIn de numa-mobile (LlamadaOverlay.tsx),
// con otra fuente de volumen: acá es el RMS del AnalyserNode pasado a dB
// (20·log10), allá el metering de expo-audio. Los dos son dBFS, pero el
// procesamiento del micrófono es distinto (navegador vs. sistema), así que
// los NÚMEROS no se copian de una plataforma a la otra: se afinan con el
// panel de debug de cada una.
//
// El micrófono está abierto toda la llamada, así que mientras Numa habla
// también escucha su eco (atenuado por el echoCancellation del navegador).
// Para no confundirlo con la voz del usuario:
//   1. Calibración: los primeros CALIBRACION_MS en que Numa SUENA se mide el
//      nivel del eco — es cuando con más certeza el micro oye a Numa y no al
//      usuario.
//   2. Umbral = max(eco + margen, piso). El piso cubre el caso de un eco casi
//      nulo (buen AEC), donde cualquier ruido de la sala superaría eco+margen.
//   3. Hay que superar el umbral de forma SOSTENIDA (no un pico), tolerando
//      el bajón corto entre sílabas.
//
// Es lógica pura (sin DOM ni audio) para poder probarla con datos inventados.

export const BARGE_IN_DEFAULTS = {
  calibracionMs: 500,
  muestrasMinimas: 4,      // sin esto, un micro lento fija el umbral con 0 muestras
  calibracionMaxMs: 2000,
  margenDb: 10,
  pisoDb: -26,
  sostenidoMs: 250,
  toleranciaBajoMs: 120,   // bajón permitido entre sílabas sin reiniciar la cuenta
};

/** Volumen RMS (0..1) → dBFS. El silencio absoluto queda en -100. */
export function rmsADb(rms) {
  return rms > 0 ? Math.max(-100, 20 * Math.log10(rms)) : -100;
}

export function crearDetectorBargeIn(cfg = {}) {
  const c = { ...BARGE_IN_DEFAULTS, ...cfg };

  let inicioCalibracion = null;
  let muestrasEco = [];
  let ecoDb = null;          // null = todavía calibrando
  let arribaMs = 0;
  let abajoMs = 0;

  const umbral = () => (ecoDb === null ? null : Math.max(ecoDb + c.margenDb, c.pisoDb));

  return {
    config: c,

    /** Una lectura del micro. `sonando` = Numa está reproduciendo audio en
     *  este instante. Devuelve true cuando hay que cortar a Numa. */
    muestra(db, sonando, ahora, deltaMs) {
      if (ecoDb === null) {
        if (!sonando) return false;          // se calibra solo con Numa sonando
        if (inicioCalibracion === null) inicioCalibracion = ahora;
        muestrasEco.push(db);
        const transcurrido = ahora - inicioCalibracion;
        const listo = (transcurrido >= c.calibracionMs && muestrasEco.length >= c.muestrasMinimas)
          || transcurrido >= c.calibracionMaxMs;
        if (listo) {
          // Promedio de potencia, no de dB: un pico de eco tiene que pesar.
          const pot = muestrasEco.reduce((s, d) => s + 10 ** (d / 10), 0) / muestrasEco.length;
          ecoDb = 10 * Math.log10(pot);
        }
        return false;
      }

      if (db >= umbral()) {
        arribaMs += deltaMs;
        abajoMs = 0;
      } else {
        abajoMs += deltaMs;
        if (abajoMs > c.toleranciaBajoMs) arribaMs = 0;
      }
      return arribaMs >= c.sostenidoMs;
    },

    estado() {
      return { ecoDb, umbralDb: umbral(), arribaMs, calibrando: ecoDb === null };
    },
  };
}
