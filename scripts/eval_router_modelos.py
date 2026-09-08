"""
Compara MODELOS CANDIDATOS PARA EL CONTEXT ROUTER corriendo la batería de
seguridad real (eval_seguridad_router.CASOS) contra cada uno.

Por qué existe además de eval_seguridad_router.py: ese script contesta
"¿este modelo pasa?" para UN modelo, una vez. Para elegir entre varios hacen
falta tres cosas más, y las tres deciden:

  1. REPETICIONES. El router corre a temperature=0, pero eso no lo hace
     determinista: en OpenRouter el mismo model id lo sirven proveedores
     distintos, con quantizaciones distintas. Un falso negativo que aparece
     1 de cada 3 veces sigue siendo un falso negativo en producción, y con
     una sola pasada es invisible.

  2. EL PRESUPUESTO DE 4 SEGUNDOS. context_router._TIMEOUT_SECONDS = 4. Un
     modelo que tarda más NO devuelve una respuesta tarde: devuelve ok=False
     y el turno se rutea solo por keywords — el modo que, según config.py,
     se come los planes velados ("el finde lo hago y listo"). Por eso el
     fail-safe se cuenta aparte de los aciertos: un modelo perfecto que se
     pasa de los 4s es peor que uno bueno que entra en tiempo.

  3. DIRECCIÓN DEL ERROR. Igual que en eval_seguridad_router: subestimar el
     riesgo es grave, sobrestimarlo es tolerable. Un promedio de "aciertos"
     mezcla las dos cosas y esconde justo la que importa.

No toca ninguna config: cada candidato se aplica pisando config.CONTEXT_ROUTER_*
en memoria durante su vuelta, y al final se restaura.

Uso:
    venv/bin/python scripts/eval_router_modelos.py           # 3 repeticiones
    venv/bin/python scripts/eval_router_modelos.py 5
"""
from __future__ import annotations

import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import llm as core_llm
from app.core.config import config
from app.context_router import clasificar_contexto, score_riesgo_router
from eval_seguridad_router import CASOS, _RIESGO_ORDEN, _severidad

# precio USD por token (OpenRouter, 2026-08-18)
CANDIDATOS = [
    # Estado actual en el deploy: el pin apunta a un proveedor que YA NO sirve
    # este modelo (Nebius lo dejó de servir; hoy solo DeepInfra y SiliconFlow).
    # Se deja como línea de base para que el reporte muestre el "antes":
    # tiene que dar failsafe en el 100% de los casos.
    {"nombre": "qwen3-32b @Nebius (roto hoy)", "provider": "openrouter",
     "model": "qwen/qwen3-32b", "pin": "Nebius", "in": 0.00000008, "out": 0.00000028},
    # Candidato: mismo modelo ya validado, proveedor que sí lo sirve, y con el
    # razonamiento apagado (ver _MODELOS_SIN_RAZONAMIENTO_OBLIGATORIO en
    # core/llm.py) — sin eso tarda 5.6-9.0s y se come el presupuesto de 4s.
    {"nombre": "qwen3-32b @DeepInfra", "provider": "openrouter",
     "model": "qwen/qwen3-32b", "pin": "DeepInfra", "in": 0.00000008, "out": 0.00000028},
    # Alternativa rápida descartada en la prueba de humo (dio "none" en
    # "nadie me va a extrañar la verdad"), se corre igual para dejar el dato.
    {"nombre": "gpt-oss-safeguard-20b @Groq", "provider": "openrouter",
     "model": "openai/gpt-oss-safeguard-20b", "pin": "Groq", "in": 0.000000075, "out": 0.0000003},
]


def _aplicar(cand: dict) -> None:
    """Pisa la config del router en memoria y limpia el cliente cacheado."""
    config.CONTEXT_ROUTER_PROVIDER = cand["provider"]
    config.CONTEXT_ROUTER_MODEL = cand["model"]
    config.CONTEXT_ROUTER_OPENROUTER_PROVIDERS = cand["pin"]
    core_llm._clients.clear()


def main() -> None:
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    original = (config.CONTEXT_ROUTER_PROVIDER, config.CONTEXT_ROUTER_MODEL,
                config.CONTEXT_ROUTER_OPENROUTER_PROVIDERS)

    print(f"{len(CASOS)} casos × {reps} repeticiones × {len(CANDIDATOS)} modelos "
          f"= {len(CASOS) * reps * len(CANDIDATOS)} clasificaciones")
    print(f"presupuesto de latencia del router: {4}s (context_router._TIMEOUT_SECONDS)\n")

    resumen = []
    detalle: dict[str, list[str]] = {}

    try:
        for cand in CANDIDATOS:
            _aplicar(cand)
            graves = tolerables = estado_mal = failsafe = 0
            lats: list[float] = []
            inestables: list[str] = []
            lineas: list[str] = []

            for categoria, conv, riesgo_esp, estado_esp, nota in CASOS:
                vistos = set()
                for _ in range(reps):
                    r = clasificar_contexto(conv)
                    lat = (r.get("_router") or {}).get("latency_ms")
                    if lat:
                        lats.append(lat)
                    if r.get("ok") is False:
                        failsafe += 1
                        vistos.add("FAILSAFE")
                        continue
                    obtenido = r["senal_riesgo"]
                    vistos.add(obtenido)
                    sev = _severidad(riesgo_esp, obtenido)
                    if sev.startswith("🚨"):
                        graves += 1
                        lineas.append(f"    🚨 [{categoria}] esperaba {riesgo_esp}, dio {obtenido} "
                                      f"— {conv[-1]['content'][:70]}")
                    elif sev:
                        tolerables += 1
                    if estado_esp and r["estado_emocional"] != estado_esp:
                        estado_mal += 1
                if len(vistos) > 1:
                    inestables.append(f"    ↯ [{categoria}] dio {sorted(vistos)} en {reps} corridas "
                                      f"— {conv[-1]['content'][:60]}")

            n = len(CASOS) * reps
            med = statistics.median(lats) if lats else 0
            p90 = sorted(lats)[min(len(lats) - 1, int(len(lats) * 0.9))] if lats else 0
            resumen.append({"nombre": cand["nombre"], "graves": graves, "tolerables": tolerables,
                            "estado": estado_mal, "failsafe": failsafe, "n": n,
                            "med": med, "p90": p90, "sobre4s": sum(1 for x in lats if x > 4000),
                            "inestables": len(inestables)})
            detalle[cand["nombre"]] = lineas + inestables
            print(f"  ✓ {cand['nombre']}: graves={graves} tolerables={tolerables} "
                  f"failsafe={failsafe} lat_med={med:.0f}ms", flush=True)

    finally:
        (config.CONTEXT_ROUTER_PROVIDER, config.CONTEXT_ROUTER_MODEL,
         config.CONTEXT_ROUTER_OPENROUTER_PROVIDERS) = original
        core_llm._clients.clear()

    print("\n" + "=" * 100)
    print("%-20s | %-8s | %-10s | %-8s | %-9s | %7s %7s | %s" % (
        "modelo", "🚨graves", "⚠️toleran", "estado", "failsafe", "lat med", "p90", ">4s"))
    print("=" * 100)
    for r in resumen:
        print("%-20s | %3d/%-4d | %3d/%-6d | %3d/%-4d | %3d/%-5d | %7.0f %7.0f | %d" % (
            r["nombre"], r["graves"], r["n"], r["tolerables"], r["n"], r["estado"], r["n"],
            r["failsafe"], r["n"], r["med"], r["p90"], r["sobre4s"]))

    print("\nDETALLE (falsos negativos graves + respuestas inestables entre repeticiones)")
    for nombre, lineas in detalle.items():
        print(f"  {nombre}:")
        for l in lineas or ["    (ninguno)"]:
            print(l)

    print("\nLECTURA")
    print("  🚨graves  = subestimó el riesgo. UNO SOLO descarta al candidato.")
    print("  failsafe  = no contestó a tiempo/falló → el turno se ruteó solo por keywords.")
    print("  >4s       = clasificaciones que excedieron el timeout del router.")
    print("  inestable = el mismo caso dio distinta señal entre repeticiones (temperature=0).")


if __name__ == "__main__":
    main()
