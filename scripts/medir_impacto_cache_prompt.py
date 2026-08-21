"""
¿La caché de OpenRouter/OpenAI ahorra TIEMPO de procesamiento, o solo plata?

POR QUÉ ESTE SCRIPT
El comentario en llm_client.py (_extraer_uso) ya sostenía la hipótesis de que
pegar en caché ahorra "segundos de TTFT", pero lo dice como algo "inferido de
mediciones con demasiada varianza" — nunca se aisló la caché como variable
única, controlando el resto. bench_modelos_ttft.py mide modelos, no esto.

Este script hace 3 corridas ronda-robin, mismo modelo (CHAT_MODEL de
producción), mismo `construir_prompt` real, para responder tres preguntas
distintas con evidencia, no inferencia:

  A) PROMPT REAL, caché caliente (se pre-calienta antes de medir)
     → el caso de HOY en producción.
  B) PROMPT REAL + nonce al principio → misma longitud, mismo contenido,
     pero garantiza cache miss (la caché matchea por PREFIJO exacto desde el
     token 0: un nonce al inicio invalida todo lo que viene después, aunque
     sea idéntico). Aísla el efecto de la caché sola, a igual tamaño.
  C) SOLO el contexto dinámico (perfil/memorias/patrones/fecha/checkin), SIN
     ninguno de los ~29 módulos estáticos de instrucciones → simula el techo
     de lo que ganaría sacarse de encima el prompt estático vía fine-tuning
     (la parte dinámica no se puede fine-tunear: cambia por usuario/turno).

A - B  = cuánto ahorra la caché HOY (con el prompt tal cual está).
A - C  = techo teórico de lo que ganaría fine-tuning MÁS ALLÁ de lo que la
         caché ya da (si el prompt estático desapareciera del todo).

Uso:
    venv/bin/python scripts/medir_impacto_cache_prompt.py [muestras]
"""
import os
import statistics
import sys
import time
import uuid
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.llm import get_client, extra_body_for, max_tokens_for_provider
from app.core.config import config
from app.llm_client import _INSTRUCCION_FORMATO_STREAMING, _INSTRUCCION_MODO_LLAMADA, _extraer_uso
from app.numa_prompt import construir_prompt

MENSAJE = "Uf, hoy fue un día durísimo en el trabajo. Estoy agotada."
MODELO = config.CHAT_MODEL  # el real de producción, no un candidato


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
    return base + _INSTRUCCION_FORMATO_STREAMING + _INSTRUCCION_MODO_LLAMADA


def _solo_contexto_dinamico() -> str:
    """Simula lo que quedaría del prompt si los ~29 módulos estáticos de
    instrucciones se reemplazaran por comportamiento fine-tuneado en el
    modelo: nada de M01..M33, solo el contexto que SÍ tiene que viajar en
    cada request porque es dato, no instrucción (no se puede fine-tunear
    "la memoria de este usuario particular" en los pesos)."""
    return (
        "Datos del usuario para esta respuesta (formato de referencia, sin "
        "instrucciones de comportamiento):\n\n"
        "FECHA DE HOY: jueves 20 de agosto de 2026\n\n"
        "Perfil: Sofi, 29 años.\n\n"
        "Memoria: Sofi trabaja en una agencia y viene con mucha carga (trabajo, prioridad 3).\n\n"
        "Interacción número 6 de la sesión.\n\n"
        "Mood actual: stressed.\n"
    ) + _INSTRUCCION_FORMATO_STREAMING + _INSTRUCCION_MODO_LLAMADA


def _corrida(cliente, system_prompt: str) -> Dict[str, Any]:
    inicio = time.perf_counter()
    marcas: List[float] = []
    uso = None
    stream = cliente.chat.completions.create(
        model=MODELO,
        temperature=0.7,
        max_tokens=max_tokens_for_provider(600, "openrouter", MODELO),
        stream=True,
        stream_options={"include_usage": True},
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": MENSAJE}],
        extra_body=extra_body_for("openrouter", MODELO),
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

    if not marcas:
        return {"error": "sin texto"}

    info_uso = _extraer_uso(uso)
    return {
        "ttft_ms": marcas[0],
        "prompt_tokens": info_uso.get("prompt_tokens"),
        "cached_tokens": info_uso.get("cached_tokens") or 0,
    }


def _resumen(nombre: str, corridas: List[Dict[str, Any]]) -> None:
    ok = [r for r in corridas if "error" not in r]
    if not ok:
        print(f"{nombre}: todas las corridas fallaron")
        return
    ttfts = sorted(r["ttft_ms"] for r in ok)
    med = statistics.median(ttfts)
    p90 = ttfts[min(len(ttfts) - 1, int(len(ttfts) * 0.9))]
    cached_pct = [
        (r["cached_tokens"] / r["prompt_tokens"] * 100) if r.get("prompt_tokens") else 0
        for r in ok
    ]
    print(f"{nombre:32s} | TTFT mediana {med:7.0f}ms | p90 {p90:7.0f}ms | "
          f"min {ttfts[0]:6.0f}ms | prompt~{statistics.median(r['prompt_tokens'] or 0 for r in ok):.0f}tok "
          f"| cacheado med {statistics.median(cached_pct):5.1f}% | n={len(ok)}")


def main() -> None:
    muestras = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    cliente = get_client("openrouter")

    prompt_real = _prompt_real()
    prompt_dinamico = _solo_contexto_dinamico()

    print(f"modelo: {MODELO}")
    print(f"prompt real: {len(prompt_real)} chars | prompt solo-dinámico: {len(prompt_dinamico)} chars")
    print(f"{muestras} muestras por condición, ronda robin\n")

    # Pre-calentar la caché del prompt real: la primera vez SIEMPRE es miss.
    print("precalentando caché del prompt real...")
    for _ in range(2):
        _corrida(cliente, prompt_real)
    print("listo.\n")

    resultados: Dict[str, List[Dict[str, Any]]] = {"A_real_cache": [], "B_real_nomiss": [], "C_solo_dinamico": []}

    for vuelta in range(1, muestras + 1):
        # A: prompt real tal cual — debería pegar en caché (caliente).
        try:
            resultados["A_real_cache"].append(_corrida(cliente, prompt_real))
        except Exception as e:
            resultados["A_real_cache"].append({"error": str(e)[:120]})

        # B: mismo prompt real + nonce único al PRINCIPIO → garantiza cache miss,
        # mismo tamaño/contenido que A.
        nonce = f"[ref:{uuid.uuid4()}]\n\n"
        try:
            resultados["B_real_nomiss"].append(_corrida(cliente, nonce + prompt_real))
        except Exception as e:
            resultados["B_real_nomiss"].append({"error": str(e)[:120]})

        # C: solo el contexto dinámico, sin los módulos estáticos.
        try:
            resultados["C_solo_dinamico"].append(_corrida(cliente, prompt_dinamico))
        except Exception as e:
            resultados["C_solo_dinamico"].append({"error": str(e)[:120]})

        print(f"  vuelta {vuelta}/{muestras} lista", flush=True)

    print("\n" + "=" * 100)
    _resumen("A) real, caché caliente (HOY)", resultados["A_real_cache"])
    _resumen("B) real, cache-miss forzado", resultados["B_real_nomiss"])
    _resumen("C) solo contexto dinámico", resultados["C_solo_dinamico"])
    print("=" * 100)

    for nombre, corridas in resultados.items():
        crudos = sorted(round(r["ttft_ms"]) for r in corridas if "error" not in r)
        print(f"{nombre} crudo ({len(crudos)}): {crudos}")

    a = [r["ttft_ms"] for r in resultados["A_real_cache"] if "error" not in r]
    b = [r["ttft_ms"] for r in resultados["B_real_nomiss"] if "error" not in r]
    c = [r["ttft_ms"] for r in resultados["C_solo_dinamico"] if "error" not in r]
    if a and b:
        print(f"\nA-B (lo que ahorra la caché HOY):        {statistics.median(b) - statistics.median(a):+.0f}ms mediana")
    if a and c:
        print(f"A-C (techo extra de sacar el prompt estático, más allá de la caché): {statistics.median(a) - statistics.median(c):+.0f}ms mediana")


if __name__ == "__main__":
    main()
