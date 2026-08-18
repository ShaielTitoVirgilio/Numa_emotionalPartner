"""
Benchmark de TTFT para elegir el modelo del modo llamada.

POR QUÉ ASÍ Y NO MÁS SIMPLE
El 2026-08-18 se midió que el TTFT del modelo actual (openai/gpt-5.6-luna) es
intrínsecamente variable: 18 corridas IDÉNTICAS dieron de 705ms a 2946ms,
mediana ~1086ms y 28% por encima de 2000ms. Con esa dispersión, comparar
modelos con 1 o 2 muestras no dice nada — el ruido es más grande que la
diferencia que se busca.

Por eso:
  - N muestras por modelo (default 8), y se reporta MEDIANA y P90, no promedio:
    el promedio lo domina un outlier y la mediana es lo que el usuario siente
    en la mayoría de los turnos. El p90 es el "peor caso habitual".
  - RONDA ROBIN: se alterna modelo por modelo en cada vuelta en vez de correr
    uno entero y después el otro. Si la red o el proveedor tienen un bache de
    30s, con el orden secuencial se lo come un solo modelo y queda descartado
    injustamente.
  - Se mide también ms_por_chunk: un modelo puede tener buen TTFT pero mandar
    todo en lote, y para el modo llamada eso importa tanto como el TTFT.
  - Se usa el prompt REAL (construir_prompt, ~38k chars) y generate_response_
    stream REAL, con las instrucciones de formato JSON incluidas: un benchmark
    con un prompt de juguete no predice nada del comportamiento en producción.

QUÉ NO MIDE
La CALIDAD de la respuesta. Un modelo rapidísimo que conteste mal no sirve.
Antes de mover CHAT_MODEL hay que pasar eval_multimodelo.py, y si se toca el
router, eval_seguridad_router.py (falso negativo en riesgo = inaceptable).

Uso:
    venv/bin/python scripts/bench_modelos_ttft.py            # shortlist, 8 muestras
    venv/bin/python scripts/bench_modelos_ttft.py 5 modelo-a,modelo-b
"""
import json
import os
import statistics
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.llm import get_client, extra_body_for, max_tokens_for_provider
from app.llm_client import _INSTRUCCION_FORMATO_STREAMING, _INSTRUCCION_MODO_LLAMADA
from app.numa_prompt import construir_prompt

MENSAJE = "Uf, hoy fue un día durísimo en el trabajo. Estoy agotada."

# Shortlist: modelos "flash/mini/nano" (los que suelen tener TTFT bajo) más el
# actual como baseline. Se eligieron de la lista de OpenRouter priorizando
# familias rápidas y de contexto grande (el prompt son ~11k tokens).
SHORTLIST = [
    "openai/gpt-5.6-luna",            # el de producción hoy — baseline
    "google/gemini-3.7-flash",
    "google/gemini-3.5-flash-lite",
    "google/gemini-3-flash-preview",  # el fallback actual
    "openai/gpt-5.4-nano",
    "qwen/qwen3.7-flash",
    "z-ai/glm-4.7-flash",
    "deepseek/deepseek-v4-flash",
]


def _prompt_real() -> str:
    base = construir_prompt(
        perfil={"nombre": "Sofi", "edad": 29},
        memorias=[{"content": "Sofi trabaja en una agencia y viene con mucha carga",
                   "category": "trabajo", "priority": 3}],
        num_interacciones=6,
        patrones=[],
        ultimo_mensaje=MENSAJE,
        mood_actual="stressed",
        router_hints={"ok": False},
    )
    # Igual que el modo llamada: formato de streaming + techo de largo para voz.
    return base + _INSTRUCCION_FORMATO_STREAMING + _INSTRUCCION_MODO_LLAMADA


def _una_corrida(cliente, modelo: str, system_prompt: str) -> Dict[str, Any]:
    inicio = time.perf_counter()
    marcas: List[float] = []
    texto: List[str] = []
    uso = None
    stream = cliente.chat.completions.create(
        model=modelo,
        temperature=0.7,
        max_tokens=max_tokens_for_provider(600, "openrouter", modelo),
        stream=True,
        stream_options={"include_usage": True},
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": MENSAJE}],
        extra_body=extra_body_for("openrouter", modelo),
    )
    for chunk in stream:
        if getattr(chunk, "usage", None):
            uso = chunk.usage
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content or ""
        if not delta:
            continue
        marcas.append((time.perf_counter() - inicio) * 1000)
        texto.append(delta)

    total = (time.perf_counter() - inicio) * 1000
    if not marcas:
        return {"error": "sin texto", "total_ms": total}

    crudo = "".join(texto)
    # El mensaje va antes del primer '{' (contrato de _INSTRUCCION_FORMATO_STREAMING).
    idx = crudo.find("{")
    mensaje = (crudo[:idx] if idx != -1 else crudo).strip()
    return {
        "ttft_ms": marcas[0],
        "total_ms": total,
        "chunks": len(marcas),
        "ms_por_chunk": (marcas[-1] - marcas[0]) / max(1, len(marcas) - 1),
        "mensaje_chars": len(mensaje),
        "trajo_json": idx != -1,   # ¿respetó el contrato de metadata?
        "completion_tokens": getattr(uso, "completion_tokens", None) if uso else None,
    }


def main() -> None:
    muestras = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    modelos = sys.argv[2].split(",") if len(sys.argv) > 2 else SHORTLIST

    system_prompt = _prompt_real()
    cliente = get_client("openrouter")
    print(f"prompt real: {len(system_prompt)} chars | {muestras} muestras por modelo | "
          f"{len(modelos)} modelos | ronda robin\n")

    datos: Dict[str, List[Dict[str, Any]]] = {m: [] for m in modelos}
    caidos: Dict[str, str] = {}

    for vuelta in range(1, muestras + 1):
        for modelo in modelos:
            if modelo in caidos:
                continue
            try:
                r = _una_corrida(cliente, modelo, system_prompt)
                if "error" in r:
                    caidos[modelo] = r["error"]
                else:
                    datos[modelo].append(r)
            except Exception as e:
                caidos[modelo] = f"{type(e).__name__}: {str(e)[:110]}"
        print(f"  vuelta {vuelta}/{muestras} lista", flush=True)

    print("\n" + "=" * 108)
    print("%-34s | %7s %7s | %7s | %8s | %6s | %5s | %s" % (
        "modelo", "TTFTmed", "TTFTp90", "min", "ms/chunk", "chars", "json", "n"))
    print("=" * 108)

    filas = []
    for modelo in modelos:
        rs = datos[modelo]
        if not rs:
            print("%-34s | CAÍDO: %s" % (modelo[:34], caidos.get(modelo, "sin datos")))
            continue
        ttfts = sorted(r["ttft_ms"] for r in rs)
        med = statistics.median(ttfts)
        p90 = ttfts[min(len(ttfts) - 1, int(len(ttfts) * 0.9))]
        mpc = statistics.median(r["ms_por_chunk"] for r in rs)
        chars = statistics.median(r["mensaje_chars"] for r in rs)
        json_ok = sum(1 for r in rs if r["trajo_json"])
        filas.append((med, modelo, p90, ttfts[0], mpc, chars, json_ok, len(rs)))

    for med, modelo, p90, mn, mpc, chars, json_ok, n in sorted(filas):
        print("%-34s | %7.0f %7.0f | %7.0f | %8.1f | %6.0f | %2d/%-2d | %d" % (
            modelo[:34], med, p90, mn, mpc, chars, json_ok, n, n))

    print("\nCómo leerlo:")
    print("  TTFTmed  = lo que se siente en la mayoría de los turnos (lo que más importa)")
    print("  TTFTp90  = el peor caso habitual; un p90 alto se nota como 'a veces tarda un montón'")
    print("  ms/chunk = <3 significa que mandó el texto en lote (malo para voz)")
    print("  json     = cuántas corridas respetaron el contrato de metadata; si falla, no sirve")
    print("\n⚠️  Esto NO mide calidad. Antes de mover CHAT_MODEL: eval_multimodelo.py.")

    salida = os.path.join(os.path.dirname(__file__), "..", "bench_modelos_ttft_resultados.json")
    with open(salida, "w") as f:
        json.dump({"muestras": muestras, "datos": datos, "caidos": caidos}, f, indent=2)
    print(f"\ncrudo guardado en {os.path.normpath(salida)}")


if __name__ == "__main__":
    main()
