"""
Misma pregunta que scripts/test_reasoning_effort.py pero para el modo
streaming (modo llamada / voz, staging) en vez del chat escrito sin
streaming (main): ¿bajar reasoning.effort a enabled=false ayuda acá también,
y sigue devolviendo el formato correcto ("texto plano PRIMERO, línea en
blanco, JSON compacto DESPUÉS" — ver _INSTRUCCION_FORMATO_STREAMING en
llm_client.py) sin romperse?

En streaming la métrica que más importa es distinta de /chat: no es el
tiempo a la respuesta completa, es el tiempo al PRIMER CHUNK de texto
hablable (t_primer_delta_ms en la jerga de chat_router.py/llamada.js) — es
el silencio que el usuario escucha antes de que Numa arranque a hablar. Si
el modelo genera razonamiento en un canal oculto antes de emitir cualquier
contenido visible (como pasa en la llamada sin streaming), ese silencio
debería bajar con enabled=false igual que bajó la latencia total en /chat.

Compara, contra el modelo real de producción, en modo llamada
(_INSTRUCCION_MODO_LLAMADA sumada, igual que hace /chat/stream con
modo_llamada=True):
  A) reasoning.effort="low"   (lo que tiene staging hoy)
  B) reasoning.enabled=false  (la variante a validar)

Para cada corrida mide: ms al primer chunk de texto, ms totales hasta que
cierra el stream, y si el output separó bien texto/JSON (nada de '{' antes
de la línea en blanco, JSON final parseable con mood/suggested_action).

Correr con: venv/bin/python scripts/test_reasoning_effort_streaming.py
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
    print(f"⚠️ CHAT_PROVIDER es '{PROVEEDOR}', no 'openrouter'. Abortando.")
    sys.exit(1)

cliente = get_client(PROVEEDOR).with_options(timeout=30.0)

# Mismas instrucciones que llm_client.generate_response_stream le suma al
# prompt en modo streaming + modo llamada (copiadas tal cual de staging).
_INSTRUCCION_FORMATO_STREAMING = """

FORMATO DE RESPUESTA (modo streaming — reemplaza el formato JSON de arriba):
Escribí PRIMERO el mensaje para la persona, en texto plano y natural, tal cual se lo dirías en voz alta. Sin comillas, sin llaves, sin JSON, sin markdown.
Cuando termines el mensaje, dejá una línea en blanco y escribí SOLO un JSON compacto de una línea con esta forma exacta:
{"mood": "...", "suggested_action": ..., "memories": [...]}
Usá los mismos valores posibles de mood/suggested_action/memories ya explicados arriba. No repitas el mensaje adentro de ese JSON — ahí van solo mood, suggested_action y memories.
"""

_INSTRUCCION_MODO_LLAMADA = """

MODO LLAMADA (estás hablando por voz, en vivo, no escribiendo):

Contestá como se contesta hablando: UNA idea por turno, en una o dos oraciones.
Eso es lo normal, no la excepción — la enorme mayoría de tus turnos van así.
Si podés decirlo en una línea, decilo en una línea.

Solo si te piden explícitamente que expliques o cuentes algo en detalle
("explicame", "contame bien", "dame ejemplos") podés estirarte un poco más, y
aun ahí decí lo esencial y frenás. Preguntar "¿querés que siga?" siempre es
mejor que soltar un monólogo.

Nunca encadenes varias ideas en un mismo turno por las dudas. En una charla
hablada el otro necesita poder meter bocado: un turno largo cuando alcanzaba
con una línea se siente robótico, por más que el contenido esté bien.
"""

system_prompt = construir_prompt(
    perfil={"nombre": "Usuario de prueba", "edad": 28, "ocupacion": "diseñador"},
    memorias=[
        {"content": "Le cuesta dormir bien entre semana por el trabajo.", "category": "salud", "priority": 3},
        {"content": "Está estudiando un curso de UX los fines de semana.", "category": "estudios", "priority": 2},
    ],
    num_interacciones=5, patrones=[], mood_actual="neutral",
    historial_reciente=[
        {"role": "user", "content": "hoy fue un día largo"},
        {"role": "assistant", "content": "¿Qué fue lo que más pesó del día?"},
    ],
    ultimo_mensaje="La verdad que bastante cansado, pero bien. Mañana tengo que entregar un proyecto.",
) + _INSTRUCCION_FORMATO_STREAMING + _INSTRUCCION_MODO_LLAMADA

mensajes = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": "La verdad que bastante cansado, pero bien. Mañana tengo que entregar un proyecto."},
]

VARIANTES = {
    "A) effort=low (actual en staging)": {"reasoning": {"effort": "low"}, "provider": {"only": ["openai"]}},
    "B) enabled=false":                  {"reasoning": {"enabled": False}, "provider": {"only": ["openai"]}},
}


def _una_corrida(extra_body):
    t0 = time.perf_counter()
    t_primer_chunk = None
    texto = ""
    try:
        stream = cliente.chat.completions.create(
            model=MODELO,
            temperature=0.7,
            max_tokens=1600,
            stream=True,
            messages=mensajes,
            extra_body=extra_body,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content or ""
            if delta:
                if t_primer_chunk is None:
                    t_primer_chunk = round((time.perf_counter() - t0) * 1000, 1)
                texto += delta
        ms_total = round((time.perf_counter() - t0) * 1000, 1)

        # Validar formato: nada de '{' antes de la línea en blanco que separa
        # mensaje de metadata (si hay '{' pegado al texto sin separación, el
        # parser real de BufferStreamingMensaje lo tomaría mal).
        idx_json = texto.find("{")
        mensaje_parte = texto[:idx_json].strip() if idx_json != -1 else texto.strip()
        json_parte = texto[idx_json:].strip() if idx_json != -1 else ""
        json_ok = False
        if json_parte:
            try:
                parsed = json.loads(json_parte)
                json_ok = "mood" in parsed
            except json.JSONDecodeError:
                json_ok = False

        return {
            "ok": True, "t_primer_chunk_ms": t_primer_chunk, "ms_total": ms_total,
            "mensaje_parte": mensaje_parte, "json_ok": json_ok, "tiene_json": idx_json != -1,
        }
    except Exception as e:
        return {"ok": False, "ms_total": round((time.perf_counter() - t0) * 1000, 1), "error": str(e)[:200]}


resultados = {}
for nombre, extra_body in VARIANTES.items():
    print(f"\n── {nombre} ──")
    corridas = []
    for i in range(N_CORRIDAS):
        r = _una_corrida(extra_body)
        corridas.append(r)
        if r["ok"]:
            print(
                f"  {i+1}/{N_CORRIDAS}: primer_chunk={r['t_primer_chunk_ms']}ms  total={r['ms_total']}ms  "
                f"json_ok={r['json_ok']}  tiene_json={r['tiene_json']}"
            )
        else:
            print(f"  {i+1}/{N_CORRIDAS}: ERROR ({r['ms_total']}ms) — {r['error']}")
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
    primeros = [r["t_primer_chunk_ms"] for r in oks if r["t_primer_chunk_ms"] is not None]
    totales = [r["ms_total"] for r in oks]
    json_oks = sum(1 for r in oks if r["json_ok"])
    print(
        f"{nombre}: {len(oks)}/{len(corridas)} ok, {json_oks}/{len(oks)} JSON de metadata válido\n"
        f"   primer chunk: mediana={statistics.median(primeros):.0f}ms  min={min(primeros):.0f}ms  max={max(primeros):.0f}ms\n"
        f"   total:        mediana={statistics.median(totales):.0f}ms  min={min(totales):.0f}ms  max={max(totales):.0f}ms"
        + (f"\n   {fallos} fallo(s)" if fallos else "")
    )

# Muestra de texto para revisar calidad a mano.
print("\n" + "=" * 70)
print("MUESTRA DE TEXTO (primera corrida ok de cada variante)")
print("=" * 70)
for nombre, corridas in resultados.items():
    primera_ok = next((r for r in corridas if r["ok"]), None)
    if primera_ok:
        print(f"\n--- {nombre} ---")
        print(primera_ok["mensaje_parte"])
