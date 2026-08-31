"""
Mide si reasoning.effort="low" (el valor actual de producción para el chat
principal en OpenRouter, ver core/llm.py extra_body_for) puede bajarse sin
romper nada, y cuánto tiempo ahorraría.

Motivación: la migración Railway→Render confirmó una ganancia grande de TTFT
(tiempo al primer token, medido en modo streaming), pero /chat usa una
llamada SIN streaming (generate_response en llm_client.py) — ahí lo que
importa es el tiempo hasta la respuesta COMPLETA, que incluye generar los
tokens de razonamiento antes del JSON final. Ese tiempo no lo toca el
hosting. Si el modelo de producción (CHAT_MODEL) acepta bajar/apagar el
razonamiento, esto sí lo reduciría — pero el propio código advierte que
algunos modelos en OpenRouter (GPT-5.6 Pro, Grok, Claude Fable) tienen
razonamiento OBLIGATORIO y devuelven 400 si se manda reasoning.enabled=false.
Por eso se prueba contra el modelo REAL de producción antes de tocar nada.

Compara 3 variantes de extra_body, contra un prompt real (construir_prompt
con datos mínimos, igual de largo que uno de producción) y el mismo mensaje
de usuario, 8 corridas cada una:
  A) reasoning.effort="low"   (la actual)
  B) reasoning.enabled=false  (apagado explícito — puede dar 400)
  C) sin bloque "reasoning" en absoluto (deja el default del modelo)

Para cada variante: latencia (media/mediana), tasa de éxito, y si el JSON
resultante sigue teniendo message/mood válidos (que no se rompió el output
por apagar el razonamiento).

Correr con: venv/bin/python scripts/test_reasoning_effort.py
Necesita OPENROUTER_API_KEY y CHAT_MODEL en el .env (usa el modelo real de
producción a propósito, no uno de prueba).
"""
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import config
from app.core.llm import get_client
from app.numa_prompt import construir_prompt

MODELO = config.CHAT_MODEL
PROVEEDOR = config.CHAT_PROVIDER
N_CORRIDAS = 8

if PROVEEDOR != "openrouter":
    print(f"⚠️ CHAT_PROVIDER es '{PROVEEDOR}', no 'openrouter' — este script asume OpenRouter. Abortando.")
    sys.exit(1)

cliente = get_client(PROVEEDOR).with_options(timeout=30.0)

# Prompt realista: mismo tamaño/estructura que uno de producción real (perfil
# con algo de contenido, un par de memorias, sin crisis).
system_prompt = construir_prompt(
    perfil={"nombre": "Usuario de prueba", "edad": 28, "ocupacion": "diseñador"},
    memorias=[
        {"content": "Le cuesta dormir bien entre semana por el trabajo.", "category": "salud", "priority": 3},
        {"content": "Está estudiando un curso de UX los fines de semana.", "category": "estudios", "priority": 2},
    ],
    num_interacciones=5,
    patrones=[],
    mood_actual="neutral",
    historial_reciente=[
        {"role": "user", "content": "hoy fue un día largo"},
        {"role": "assistant", "content": "¿Qué fue lo que más pesó del día?"},
    ],
    ultimo_mensaje="La verdad que bastante cansado, pero bien. Mañana tengo que entregar un proyecto.",
)
mensajes = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": "La verdad que bastante cansado, pero bien. Mañana tengo que entregar un proyecto."},
]

VARIANTES = {
    "A) effort=low (actual)": {"reasoning": {"effort": "low"}, "provider": {"only": ["openai"]}},
    "B) enabled=false":       {"reasoning": {"enabled": False}, "provider": {"only": ["openai"]}},
    "C) sin bloque reasoning": {"provider": {"only": ["openai"]}},
}


def _una_corrida(extra_body):
    t0 = time.perf_counter()
    try:
        completion = cliente.chat.completions.create(
            model=MODELO,
            temperature=0.7,
            max_tokens=1600,
            response_format={"type": "json_object"},
            messages=mensajes,
            extra_body=extra_body,
        )
        ms = round((time.perf_counter() - t0) * 1000, 1)
        raw = completion.choices[0].message.content or ""
        try:
            parsed = json.loads(raw.strip())
            valido = "message" in parsed and "mood" in parsed and bool(parsed.get("message"))
        except json.JSONDecodeError:
            valido = False
        return {"ok": True, "ms": ms, "valido": valido, "len_msg": len(raw)}
    except Exception as e:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return {"ok": False, "ms": ms, "error": str(e)[:200]}


resultados = {}
for nombre, extra_body in VARIANTES.items():
    print(f"\n── {nombre} — extra_body={extra_body} ──")
    corridas = []
    for i in range(N_CORRIDAS):
        r = _una_corrida(extra_body)
        corridas.append(r)
        if r["ok"]:
            print(f"  {i+1}/{N_CORRIDAS}: {r['ms']:.0f}ms  json_valido={r['valido']}")
        else:
            print(f"  {i+1}/{N_CORRIDAS}: ERROR ({r['ms']:.0f}ms) — {r['error']}")
    resultados[nombre] = corridas

print("\n" + "=" * 70)
print(f"RESUMEN — modelo real de producción: {MODELO}")
print("=" * 70)
for nombre, corridas in resultados.items():
    oks = [r for r in corridas if r["ok"]]
    fallos = len(corridas) - len(oks)
    if not oks:
        print(f"{nombre}: TODAS fallaron ({fallos}/{len(corridas)})")
        continue
    tiempos = [r["ms"] for r in oks]
    validos = sum(1 for r in oks if r["valido"])
    print(
        f"{nombre}: {len(oks)}/{len(corridas)} ok, {validos}/{len(oks)} JSON válido | "
        f"mediana={statistics.median(tiempos):.0f}ms  media={statistics.mean(tiempos):.0f}ms  "
        f"min={min(tiempos):.0f}ms  max={max(tiempos):.0f}ms"
        + (f"  | {fallos} fallo(s)" if fallos else "")
    )
