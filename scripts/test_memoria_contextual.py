"""
Verifica que Numa pueda volver a traer por su cuenta algo que el usuario contó
OTRO DÍA (2026-09-07).

Dos cosas que estaban rotas y este test fija:

1. elegir_memoria_contextual() solo elegía tema abierto o recurso con
   router_ok=True. Desde que el context_router corre en paralelo con el LLM,
   router_hints al armar el prompt es SIEMPRE ok=False → M32/M33 eran código
   muerto. Ahora el estado sale del mood del turno anterior cuando el router no
   está.
2. Ninguna fuente filtraba por antigüedad: podía traer algo dicho hoy, incluso
   minutos antes en la misma charla. Eso rompe justamente el efecto buscado
   (que se note que se acordó, no que repite lo que acaba de leer).

Correr con: venv/bin/python scripts/test_memoria_contextual.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.memory_service import (
    elegir_memoria_contextual,
    elegir_memoria_respaldo,
    es_de_dias_anteriores,
)
from app.numa_prompt import _antiguedad_relativa, construir_prompt
from app.routes.chat_router import _estado_desde_mood

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    if ok:
        print(f"✅ {nombre}")
    else:
        fallos += 1
        print(f"❌ {nombre}{chr(10) + '   ' + detalle if detalle else ''}")


AHORA = datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)


def iso(dias_atras=0, horas=12):
    return (AHORA - timedelta(days=dias_atras)).replace(hour=horas).isoformat()


def mem(dias_atras, priority=4, content="corre los martes", **extra):
    return {
        "id": f"m{dias_atras}",
        "content": content,
        "priority": priority,
        "created_at": iso(dias_atras),
        **extra,
    }


# ── 1. Antigüedad ────────────────────────────────────────────────────────
check("hoy NO es de días anteriores", not es_de_dias_anteriores(iso(0), AHORA))
check("ayer SÍ es de días anteriores", es_de_dias_anteriores(iso(1), AHORA))
check("hace una semana SÍ", es_de_dias_anteriores(iso(7), AHORA))
check("sin fecha → False (nunca asume)", not es_de_dias_anteriores(None, AHORA))
check("fecha basura → False (nunca asume)", not es_de_dias_anteriores("ayer nomás", AHORA))
check(
    "medianoche UTC es el corte",
    es_de_dias_anteriores("2026-09-06T23:59:00+00:00", AHORA)
    and not es_de_dias_anteriores("2026-09-07T00:01:00+00:00", AHORA),
)

# ── 2. Selector de respaldo ──────────────────────────────────────────────
check("respaldo: nada si no hay memorias", elegir_memoria_respaldo([], AHORA) is None)
check(
    "respaldo: descarta lo guardado hoy",
    elegir_memoria_respaldo([mem(0)], AHORA) is None,
)
check(
    "respaldo: descarta prioridad baja",
    elegir_memoria_respaldo([mem(3, priority=2)], AHORA) is None,
)
check(
    "respaldo: elige una de días anteriores con prioridad alta",
    (elegir_memoria_respaldo([mem(3)], AHORA) or {}).get("id") == "m3",
)
check(
    "respaldo: prefiere la de mayor prioridad",
    (elegir_memoria_respaldo([mem(3, priority=4), mem(5, priority=5)], AHORA) or {}).get("id") == "m5",
)
check(
    "respaldo: respeta el cooldown proactivo de 20h",
    elegir_memoria_respaldo(
        [mem(3, last_proactive_at=(AHORA - timedelta(hours=2)).isoformat())], AHORA
    ) is None,
)
check(
    "respaldo: descarta contenido vacío",
    elegir_memoria_respaldo([mem(3, content="   ")], AHORA) is None,
)

# ── 3. Mood → estado (reemplazo local del router) ────────────────────────
check("mood sad → triste_vacio", _estado_desde_mood("sad") == "triste_vacio")
check("mood anxious → ansioso", _estado_desde_mood("anxious") == "ansioso")
check("mood calm → neutral", _estado_desde_mood("calm") == "neutral")
check("mood desconocido → None", _estado_desde_mood("pensativo") is None)
check("sin mood → None", _estado_desde_mood(None) is None)

# ── 4. elegir_memoria_contextual con estado local ────────────────────────
recurso = mem(4, content="salir a correr le despejó la cabeza")
tema = mem(6, content="quedó pendiente hablar con su jefe")

check(
    "REGRESIÓN: sin estado (router caído) sigue eligiendo solo eventos",
    elegir_memoria_contextual(
        estado_emocional=None, router_ok=False, riesgo_score=0.0,
        evento=None, temas_abiertos=[tema], recursos=[recurso],
    ) is None,
)
eleccion_rec = elegir_memoria_contextual(
    estado_emocional="triste_vacio", router_ok=True, riesgo_score=0.0,
    evento=None, temas_abiertos=[], recursos=[recurso],
)
check(
    "con estado local triste_vacio elige el recurso",
    (eleccion_rec or {}).get("tipo") == "recurso",
)
eleccion_tema = elegir_memoria_contextual(
    estado_emocional="neutral", router_ok=True, riesgo_score=0.0,
    evento=None, temas_abiertos=[tema], recursos=[],
)
check(
    "con estado local neutral elige el tema abierto",
    (eleccion_tema or {}).get("tipo") == "tema_abierto",
)
check(
    "en riesgo no elige nada (la seguridad no compite)",
    elegir_memoria_contextual(
        estado_emocional="triste_vacio", router_ok=True, riesgo_score=0.5,
        evento=None, temas_abiertos=[tema], recursos=[recurso],
    ) is None,
)

# ── 5. Antigüedad en texto ───────────────────────────────────────────────
hoy_d = AHORA.date()
check("antigüedad: 1 día → 'ayer'", _antiguedad_relativa(iso(1), hoy_d) == "ayer")
check("antigüedad: 3 días", _antiguedad_relativa(iso(3), hoy_d) == "hace 3 días")
check("antigüedad: 9 días → semana pasada", _antiguedad_relativa(iso(9), hoy_d) == "la semana pasada")
check("antigüedad: hoy → vacío (no inventa)", _antiguedad_relativa(iso(0), hoy_d) == "")
check("antigüedad: basura → vacío", _antiguedad_relativa("cualquier cosa", hoy_d) == "")

# ── 6. Composición del prompt ────────────────────────────────────────────
base = dict(ultimo_mensaje="dale, gracias", num_interacciones=6)

p_resp = construir_prompt(memoria_para_retomar=mem(3, content="rindió Análisis II"), **base)
check("prompt: aparece el bloque de respaldo", "ALGO QUE TE CONTÓ OTRO DÍA" in p_resp)
check("prompt: el respaldo lleva la antigüedad", "hace 3 días" in p_resp)
check("prompt: el CUÁNDO lo decide el modelo", "lo decidís vos" in p_resp)
check("prompt: le pide no forzarlo si la charla está viva", "NO lo fuerces" in p_resp)

p_dup = construir_prompt(
    memoria_para_retomar=mem(3),
    evento_proactivo={"content": "charla con el decano", "event_title": "charla", "bucket": "hoy"},
    **base,
)
check(
    "prompt: el respaldo NO compite con un evento",
    "ALGO QUE TE CONTÓ OTRO DÍA" not in p_dup,
)
p_crisis = construir_prompt(memoria_para_retomar=mem(3), crisis_score=0.6, **base)
check("prompt: sin respaldo en crisis", "ALGO QUE TE CONTÓ OTRO DÍA" not in p_crisis)

# ── 7. Integración: _preparar_turno de punta a punta ─────────────────────
# Las piezas sueltas pueden estar bien y el cableado roto igual (es literalmente
# lo que pasó antes: elegir_memoria_contextual andaba perfecto y nunca se lo
# llamaba con un estado usable). Esto arma un turno real con la base mockeada.
from unittest.mock import patch  # noqa: E402
from fastapi import BackgroundTasks  # noqa: E402
import app.routes.chat_router as cr  # noqa: E402

_hace3 = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
_memorias = [{
    "content": "rindió Análisis II y le fue bien", "priority": 5,
    "category": "estudios", "id": "m1", "created_at": _hace3,
    "last_proactive_at": None,
}]

# Charla que se apaga: Numa viene 3 turnos sin preguntar y el usuario contesta
# corto, sin traer nada nuevo.
_body = cr.ChatRequest(
    conversation=[
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "Hola. Te leo."},
        {"role": "user", "content": "todo bien"},
        {"role": "assistant", "content": "Me alegra."},
        {"role": "user", "content": "si"},
        {"role": "assistant", "content": "Tranquilo entonces."},
        {"role": "user", "content": "dale gracias"},
    ],
    ultimo_mood="calm",
)

_parches = [
    patch.object(cr, "get_recent_memories", return_value=(_memorias, [])),
    patch.object(cr, "get_topic_patterns_cached", return_value=[]),
    patch.object(cr, "get_dias_inactivo", return_value=0),
    patch.object(cr, "get_checkin_hoy_cached", return_value=None),
    patch.object(cr, "get_proactive_memories", return_value=[]),
    patch.object(cr, "get_open_topics", return_value=[]),
    patch.object(cr, "get_resource_memories", return_value=[]),
    patch.object(cr.feedback_repo, "hay_crisis_reciente", return_value=False),
    patch.object(cr, "clasificar_contexto", return_value=dict(cr.resultado_vacio())),
]
for _p in _parches:
    _p.start()
try:
    _turno = cr._preparar_turno(_body, "u1", BackgroundTasks())
    _sp = _turno["system_prompt"]
    check("integración: llega la habilitación de preguntas", "RITMO DE PREGUNTAS" in _sp)
    check("integración: llega la memoria de días anteriores", "ALGO QUE TE CONTÓ OTRO DÍA" in _sp)
    check("integración: con su antigüedad", "hace 3 días" in _sp)
    check(
        "integración: queda marcada para el cooldown",
        _turno["memoria_ctx_id"] == "m1",
    )
    check(
        "integración: las consultas nuevas van en el bloque paralelo",
        "t_mem_contextuales_ms" in _turno["_tiempos"],
    )
finally:
    for _p in _parches:
        _p.stop()

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
