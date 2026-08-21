"""
¿Cuánto baja el TTFT del modo llamada con el CORE recortado (modo_llamada=True)?

Compara, con el pipeline real (construir_prompt real, modelo de producción,
streaming real), el prompt que arma el modo llamada HOY (con el CORE
recortado, modo_llamada=True) contra el que armaba ANTES de este cambio
(CORE completo, igual al que usa el chat escrito). Ronda robin para que la
varianza del proveedor no le pegue más a uno que al otro.

Ver también scripts/medir_impacto_cache_prompt.py: ese midió que la caché
NO explica la latencia (A/B/D dieron lo mismo); este mide si ACHICAR el
prompt de verdad (no solo cachearlo) sí mueve la aguja.

Uso:
    venv/bin/python scripts/medir_prompt_llamada_recortado.py [muestras]
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
MODELO = config.CHAT_MODEL


def _prompt(modo_llamada: bool) -> str:
    base = construir_prompt(
        perfil={"nombre": "Sofi", "edad": 29},
        memorias=[{"content": "Sofi trabaja en una agencia y viene con mucha carga",
                   "category": "trabajo", "priority": 3}],
        num_interacciones=6,
        patrones=[],
        ultimo_mensaje=MENSAJE,
        mood_actual="stressed",
        router_hints={"ok": False},
        modo_llamada=modo_llamada,
    )
    return base + _INSTRUCCION_FORMATO_STREAMING + _INSTRUCCION_MODO_LLAMADA


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
    info = _extraer_uso(uso)
    return {"ttft_ms": marcas[0], "prompt_tokens": info.get("prompt_tokens")}


def _resumen(nombre: str, corridas: List[Dict[str, Any]]) -> None:
    ok = [r for r in corridas if "error" not in r]
    if not ok:
        print(f"{nombre}: todas fallaron")
        return
    ttfts = sorted(r["ttft_ms"] for r in ok)
    med = statistics.median(ttfts)
    p90 = ttfts[min(len(ttfts) - 1, int(len(ttfts) * 0.9))]
    tok = statistics.median(r["prompt_tokens"] or 0 for r in ok)
    lentas = sum(1 for t in ttfts if t > 2500)
    print(f"{nombre:38s} | TTFT mediana {med:7.0f}ms | p90 {p90:7.0f}ms | min {ttfts[0]:6.0f}ms | "
          f"~{tok:.0f}tok | >2.5s: {lentas}/{len(ok)} | n={len(ok)}")


def main() -> None:
    muestras = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    cliente = get_client("openrouter")

    prompt_completo = _prompt(modo_llamada=False)   # como era ANTES de este cambio
    prompt_recortado = _prompt(modo_llamada=True)    # como queda AHORA en modo llamada

    print(f"modelo: {MODELO}")
    print(f"prompt completo (antes): {len(prompt_completo)} chars")
    print(f"prompt recortado (ahora, modo_llamada=True): {len(prompt_recortado)} chars")
    print(f"{muestras} muestras por condición, ronda robin\n")

    resultados: Dict[str, List[Dict[str, Any]]] = {"completo": [], "recortado": []}
    for vuelta in range(1, muestras + 1):
        # Nonce único por vuelta, en LOS DOS — así ninguno se aprovecha de caché
        # acumulada de corridas anteriores (el prompt "completo" es idéntico al
        # que ya se mandó decenas de veces hoy en otros scripts; sin esto, la
        # comparación queda sesgada a favor del que ya está tibio en caché).
        nonce = f"[ref:{uuid.uuid4()}]\n\n"
        try:
            resultados["completo"].append(_corrida(cliente, nonce + prompt_completo))
        except Exception as e:
            resultados["completo"].append({"error": str(e)[:120]})
        try:
            resultados["recortado"].append(_corrida(cliente, nonce + prompt_recortado))
        except Exception as e:
            resultados["recortado"].append({"error": str(e)[:120]})
        print(f"  vuelta {vuelta}/{muestras} lista", flush=True)

    print("\n" + "=" * 100)
    _resumen("completo (CORE sin recortar, antes)", resultados["completo"])
    _resumen("recortado (modo_llamada=True, ahora)", resultados["recortado"])
    print("=" * 100)

    c = [r["ttft_ms"] for r in resultados["completo"] if "error" not in r]
    r = [r["ttft_ms"] for r in resultados["recortado"] if "error" not in r]
    if c and r:
        print(f"\nDiferencia de mediana: {statistics.median(c) - statistics.median(r):+.0f}ms")
        print(f"Diferencia de p90:     {sorted(c)[int(len(c)*0.9)] - sorted(r)[int(len(r)*0.9)]:+.0f}ms")


if __name__ == "__main__":
    main()
