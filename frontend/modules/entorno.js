// modules/entorno.js
// Cartel de "entorno de pruebas".
//
// Cuando existan dos instalaciones de Numa en el mismo celular (la real y
// NumaDev), tiene que ser IMPOSIBLE confundirlas: el peor error posible es
// creer que estás probando y en realidad estar escribiéndole a la base de
// usuarios reales. Además del nombre distinto en el ícono (ver serve_manifest
// en app/main.py), acá se pinta una franja permanente en pantalla.
//
// En producción no hace nada: ni cartel, ni pedido extra visible al usuario.

export async function marcarEntornoDePruebas() {
  try {
    const res = await fetch('/api/entorno');
    if (!res.ok) return;

    const { entorno, es_produccion } = await res.json();
    if (es_produccion) return;

    document.documentElement.classList.add('entorno-pruebas');

    const franja = document.createElement('div');
    franja.className = 'entorno-franja';
    franja.textContent = `⚠︎ ${String(entorno).toUpperCase()} — datos de prueba`;
    document.body.appendChild(franja);
  } catch {
    // Si falla, no pasa nada: es solo un cartel informativo.
  }
}
