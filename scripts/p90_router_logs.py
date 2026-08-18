"""
Calcula el p90 REAL del context router a partir de los logs de Railway.

Contexto: context_router.py pasa timeout=4 a la llamada, pero ese timeout es
POR INTENTO y el cliente de OpenAI trae max_retries=2 — así que una
clasificación puede tardar ~12s sin disparar el fail-safe. Este script busca
esa firma en los datos reales en vez de suponerla.

Los dos números NO son intercambiables y por eso se reportan por separado:

  t_context_router_ms   → CHAT ESCRITO. El turno BLOQUEA acá (chat_router.py,
                          fut_router.result()). Cada ms es espera del usuario.
  t_router_paralelo_ms  → MODO LLAMADA. El turno NO espera. Un valor alto no
                          es latencia: es la señal de riesgo llegando tarde,
                          y lo que se mira ahí es router_corte (si llegó a
                          tiempo de cortar el turno).

REINTENTOS INFERIDOS: una clasificación EXITOSA por encima de 4000ms implica
un reintento — un intento suelto que pasa los 4s muere con APITimeoutError.
Por eso se cuentan aparte: son latencia que ningún log marca como timeout.

Uso:
    venv/bin/python scripts/p90_router_logs.py railway.log
    pbpaste | venv/bin/python scripts/p90_router_logs.py
"""
from __future__ import annotations

import json
import statistics
import sys
from typing import Any

TIMEOUT_MS = 4000  # context_router._TIMEOUT_SECONDS


def _percentil(datos: list[float], p: float) -> float:
    if not datos:
        return 0.0
    orden = sorted(datos)
    return orden[min(len(orden) - 1, int(len(orden) * p))]


def _resumen(nombre: str, vals: list[float], total_turnos: int) -> None:
    if not vals:
        print(f"\n{nombre}: sin datos")
        return
    sobre = [v for v in vals if v > TIMEOUT_MS]
    print(f"\n{nombre}  (n={len(vals)} de {total_turnos} turnos)")
    print(f"  mediana : {statistics.median(vals):8.0f} ms")
    print(f"  p90     : {_percentil(vals, 0.90):8.0f} ms")
    print(f"  p99     : {_percentil(vals, 0.99):8.0f} ms")
    print(f"  máximo  : {max(vals):8.0f} ms")
    print(f"  > {TIMEOUT_MS}ms : {len(sobre):5d} ({len(sobre)/len(vals)*100:.1f}%)  "
          f"← reintentos inferidos: exitosos pasando el timeout nominal")


def main() -> None:
    fuente = open(sys.argv[1], encoding="utf-8") if len(sys.argv) > 1 else sys.stdin

    turnos: list[dict[str, Any]] = []
    lineas = descartadas = 0
    for linea in fuente:
        lineas += 1
        linea = linea.strip()
        # Railway prefija timestamp/servicio: se busca el primer '{' de la línea.
        i = linea.find("{")
        if i == -1:
            descartadas += 1
            continue
        try:
            d = json.loads(linea[i:])
        except json.JSONDecodeError:
            descartadas += 1
            continue
        if isinstance(d, dict) and d.get("evento") == "chat_turn":
            turnos.append(d)

    if not turnos:
        sys.exit(f"No se encontró ningún evento chat_turn en {lineas} líneas leídas.\n"
                 "¿El export es de logs de la app (stdout), y del rango correcto?")

    def _num(t: dict, campo: str) -> float | None:
        v = t.get(campo)
        return float(v) if isinstance(v, (int, float)) and v > 0 else None

    escrito = [t for t in turnos if not t.get("modo_llamada")]
    llamada = [t for t in turnos if t.get("modo_llamada")]

    print("=" * 68)
    print(f"chat_turn: {len(turnos)} turnos  "
          f"({len(escrito)} chat escrito · {len(llamada)} modo llamada)")
    print(f"líneas leídas: {lineas} · sin JSON o de otro evento: {descartadas}")
    print("=" * 68)

    v_escrito = [x for x in (_num(t, "t_context_router_ms") for t in escrito) if x]
    _resumen("CHAT ESCRITO — t_context_router_ms (BLOQUEA el turno)", v_escrito, len(escrito))

    v_llamada = [x for x in (_num(t, "t_router_paralelo_ms") for t in llamada) if x]
    _resumen("MODO LLAMADA — t_router_paralelo_ms (NO bloquea)", v_llamada, len(llamada))

    if llamada:
        consultados = [t for t in llamada if t.get("t_router_paralelo_ms") is not None]
        cortes = sum(1 for t in llamada if t.get("router_corte"))
        print(f"\n  router_corte (llegó a tiempo de cortar por riesgo): {cortes}")
        print(f"  turnos donde el router llegó a consultarse         : {len(consultados)}/{len(llamada)}")
        print("  ↑ si este segundo número es bajo, la señal de riesgo del router")
        print("    está llegando después de que el turno terminó.")

    print("\nCÓMO LEERLO")
    print(f"  Si el p90 del chat escrito está cómodo debajo de {TIMEOUT_MS}ms y '>{TIMEOUT_MS}ms'")
    print("  es ~0%, los reintentos casi no ocurren y el arreglo puede esperar.")
    print("  Si hay un 5-10% por encima, son turnos donde el usuario esperó de más")
    print("  sin que ningún log lo marque como timeout.")


if __name__ == "__main__":
    main()
