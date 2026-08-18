"""
Diagnóstico: ¿por qué el LLM tarda ~2.6s en emitir el PRIMER token y después
manda el mensaje entero en 50ms?

Medido en producción (logs 2026-08-18, modo llamada):
    t_llm_primer_token_ms = 2605-2641    llm_latency_ms = 2667-2689
O sea 2.6s de silencio y todo el texto en los últimos ~50ms. Con stream=True
puesto y los chunks consumiéndose bien, eso apunta al bloque de reasoning:
esos tokens no viajan en delta.content, así que del lado nuestro se ven como
silencio.

Esto lo COMPRUEBA en vez de suponerlo: hace llamadas reales variando solo el
reasoning.effort y mide time-to-first-token contra tiempo total.

Si TTFT baja fuerte al bajar el effort  → es el reasoning, y se puede atacar.
Si TTFT no se mueve                     → es buffering en la ruta (OpenRouter
                                          o el proveedor), y el reasoning no
                                          tiene nada que ver.

Hace llamadas REALES (gasta tokens, poco). Correr a mano:
    venv/bin/python scripts/diag_ttft_streaming.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.llm import get_client
from app.core.config import config

PROMPT_SISTEMA = (
    "Sos Numa, una compañera emocional en español rioplatense. "
    "Respondé en 2 o 3 oraciones, cálida y concreta, sin listas."
)
MENSAJE = "Uf, hoy fue un día durísimo en el trabajo. Estoy agotada."

# El de producción, más variantes de effort. "minimal" es el que la familia
# GPT-5 acepta para razonar lo mínimo posible.
VARIANTES = [
    ("effort=low (PRODUCCIÓN HOY)", {"reasoning": {"effort": "low"}}),
    ("effort=minimal", {"reasoning": {"effort": "minimal"}}),
    ("sin bloque reasoning", {}),
]


def medir(nombre: str, extra: dict, modelo: str, cliente) -> None:
    body = dict(extra)
    if modelo.startswith("openai/"):
        # Mismo pin de provider que producción, si no se compara contra otra
        # ruta y el número no es representativo (ver extra_body_for).
        body["provider"] = {"only": ["openai"]}

    inicio = time.perf_counter()
    ttft = None
    chunks = 0
    texto = []
    try:
        stream = cliente.chat.completions.create(
            model=modelo,
            temperature=0.7,
            max_tokens=400,
            stream=True,
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": MENSAJE},
            ],
            extra_body=body,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content or ""
            if not delta:
                continue
            if ttft is None:
                ttft = (time.perf_counter() - inicio) * 1000
            chunks += 1
            texto.append(delta)
    except Exception as e:
        print(f"  {nombre:<30} ERROR: {type(e).__name__}: {str(e)[:120]}")
        return

    total = (time.perf_counter() - inicio) * 1000
    if ttft is None:
        print(f"  {nombre:<30} sin texto en la respuesta")
        return

    cola = total - ttft
    print(f"  {nombre:<30} TTFT {ttft:7.0f}ms | total {total:7.0f}ms | "
          f"post-TTFT {cola:6.0f}ms | {chunks:3d} chunks | {len(''.join(texto)):4d} chars")


def main() -> None:
    modelo = config.CHAT_MODEL
    proveedor = config.CHAT_PROVIDER
    print(f"proveedor={proveedor}  modelo={modelo}\n")
    cliente = get_client(proveedor)

    # 2 vueltas: la primera puede pagar conexión TLS fría y ensuciar el número.
    for vuelta in (1, 2):
        print(f"--- vuelta {vuelta} ---")
        for nombre, extra in VARIANTES:
            medir(nombre, extra, modelo, cliente)
        print()

    print("Cómo leerlo:")
    print("  post-TTFT chico (~50ms) = el modelo NO streamea de a poco, dumpea al final.")
    print("  Si TTFT baja al bajar el effort, el silencio es reasoning y es atacable.")
    print("  Si TTFT no se mueve, el cuello está en la ruta, no en el razonamiento.")


if __name__ == "__main__":
    main()
