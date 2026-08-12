"""
Prueba de equivalencia: compara el pipeline de filtros ACTUAL (todo de una,
sobre el mensaje completo, como en chat_endpoint) contra BufferStreamingMensaje
(streaming con cola de retención), para varios mensajes de ejemplo.

Importa el código REAL de la app (no lo reimplementa) — sirve como test de
regresión: si algún día se toca app/text_filters.py o app/streaming_buffer.py
de forma que dejen de dar el mismo resultado, esto lo detecta.

Correr con: venv/bin/python scripts/test_buffer_streaming.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.text_filters import (
    _quitar_che,
    _familia_apertura,
    _aplanar_apertura,
    _cierra_con_presencia,
    _quitar_cierre_presencia,
    _quitar_pregunta_final,
)
from app.streaming_buffer import BufferStreamingMensaje


# ──────────────────────────────────────────────────────────────────
# Pipeline ACTUAL (no-streaming): réplica exacta del orden en chat_endpoint
# (app/routes/chat_router.py, sección de post-procesamiento del mensaje)
# ──────────────────────────────────────────────────────────────────
def filtrar_no_streaming(mensaje, familia_previa, previo_cierre_presencia,
                          preguntas_seguidas, crisis_score, ultimo_modulo_critico):
    m = _quitar_che(mensaje)

    familia_actual = _familia_apertura(m)
    if familia_actual and familia_actual == familia_previa:
        aplanado = _aplanar_apertura(m)
        if aplanado and aplanado != m and len(aplanado) >= 10:
            m = aplanado

    if crisis_score < 0.35 and not ultimo_modulo_critico and _cierra_con_presencia(m):
        if previo_cierre_presencia:
            recortado = _quitar_cierre_presencia(m)
            if recortado and len(recortado) >= 40 and len(recortado) >= 0.4 * len(m):
                m = recortado

    if (preguntas_seguidas >= 2 and crisis_score < 0.35 and not ultimo_modulo_critico
            and m.rstrip().rstrip("\"'” ").endswith("?")):
        recortado = _quitar_pregunta_final(m)
        if recortado and len(recortado) >= 40 and len(recortado) >= 0.35 * len(m):
            m = recortado

    return m


def simular_streaming(mensaje, **kwargs):
    """Parte el mensaje en palabras y las 'feedea' de a poco al buffer real,
    como si fueran deltas del LLM llegando de a pedazos chicos."""
    buf = BufferStreamingMensaje(**kwargs)
    palabras = mensaje.split(" ")
    for i, palabra in enumerate(palabras):
        delta = palabra + (" " if i < len(palabras) - 1 else "")
        buf.feed(delta)
    buf.cerrar()
    return buf.mensaje_completo()


# ──────────────────────────────────────────────────────────────────
# Casos de prueba
# ──────────────────────────────────────────────────────────────────
CASOS = [
    dict(
        nombre="che en el medio + cierre de presencia repetido",
        mensaje="Che, veo que venís con un día pesado. Tiene sentido que te sientas así. Acá estoy, no me voy a ningún lado.",
        familia_previa=None, previo_cierre=True, preguntas_seguidas=0,
        crisis_score=0.1, ultimo_critico=False,
    ),
    dict(
        nombre="apertura repetida (Sentís que...)",
        mensaje="Sentís que todo se te vino encima esta semana. Es una carga grande para sostener sola.",
        familia_previa="sentis_que", previo_cierre=False, preguntas_seguidas=0,
        crisis_score=0.1, ultimo_critico=False,
    ),
    dict(
        nombre="racha de preguntas + pregunta final",
        mensaje="Uf, qué semana. Pasó algo puntual o es una acumulación de varias cosas, ¿me contás un poco más?",
        familia_previa=None, previo_cierre=False, preguntas_seguidas=2,
        crisis_score=0.1, ultimo_critico=False,
    ),
    dict(
        nombre="mensaje corto (2 oraciones, todo cae en la cola)",
        mensaje="Che, tiene sentido. Te leo, sin apuro.",
        familia_previa=None, previo_cierre=True, preguntas_seguidas=0,
        crisis_score=0.1, ultimo_critico=False,
    ),
    dict(
        nombre="mensaje largo con che disperso y cierre repetido",
        mensaje=(
            "Che, entiendo que estés agotada. Veníte acumulando esto hace tiempo, che, y no es poco. "
            "A veces el cuerpo avisa antes que la cabeza. Vale la pena que le prestes atención a eso. "
            "Acá estoy, no me voy a ningún lado."
        ),
        familia_previa=None, previo_cierre=True, preguntas_seguidas=0,
        crisis_score=0.1, ultimo_critico=False,
    ),
    dict(
        nombre="crisis activa (los filtros de cierre no deben tocar nada)",
        mensaje="Che, esto es serio. Acá estoy, no me voy a ningún lado.",
        familia_previa=None, previo_cierre=True, preguntas_seguidas=0,
        crisis_score=0.9, ultimo_critico=True,
    ),
]

ok_total = True
for caso in CASOS:
    kwargs = dict(
        familia_apertura_previa=caso["familia_previa"],
        previo_cierre_presencia=caso["previo_cierre"],
        preguntas_seguidas=caso["preguntas_seguidas"],
        crisis_score=caso["crisis_score"],
        ultimo_modulo_critico=caso["ultimo_critico"],
    )
    esperado = filtrar_no_streaming(
        caso["mensaje"], caso["familia_previa"], caso["previo_cierre"],
        caso["preguntas_seguidas"], caso["crisis_score"], caso["ultimo_critico"],
    )
    obtenido = simular_streaming(caso["mensaje"], **kwargs)

    ok = esperado.strip() == obtenido.strip()
    ok_total &= ok
    print(f"{'✅' if ok else '❌'} {caso['nombre']}")
    if not ok:
        print(f"   esperado : {esperado!r}")
        print(f"   obtenido : {obtenido!r}")

print()
print("TODO OK" if ok_total else "HAY DIFERENCIAS — revisar")
sys.exit(0 if ok_total else 1)
