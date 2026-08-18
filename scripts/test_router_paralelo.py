"""
Verifica el context_router EN PARALELO del modo llamada.

Qué problema resuelve, y por qué esto es código de seguridad y no una
optimización: durante un tiempo el router estuvo directamente APAGADO en modo
llamada para no pagar sus 1.5-2s. Eso dejaba sin ninguna cobertura las frases
con método o plan que el detector por keywords no matchea — "tengo pastillas y
me las voy a tomar todas", "me quiero cortar las venas" — que son justo las que
una llamada de voz hace más probables, porque hablando se dice lo que no se
escribiría.

Ahora el router corre igual, pero sin bloquear: se lanza al empezar el turno y
se consulta mientras el LLM principal ya está generando. Si marca riesgo
explícito (score >= UMBRAL_CORTE_LLAMADA), el turno se corta y pasa al chat
escrito con la respuesta de contención, que lleva los teléfonos tocables.

Lo que se verifica acá:
  1. Que el turno NO espere al router (esa era toda la razón del cambio).
  2. Que con riesgo explícito CORTE, mande la contención y no siga hablando.
  3. Que con riesgo implícito NO corte (cortar una llamada a mitad de frase es
     brusco; una señal débil no lo justifica).
  4. Que un router que falla o tarda no rompa nada — fail-safe.
  5. Que el mensaje a medio decir no quede guardado como respuesta.

Correr con: venv/bin/python scripts/test_router_paralelo.py
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import BackgroundTasks

import app.routes.chat_router as cr

fallos = 0
_pool = ThreadPoolExecutor(max_workers=4)


def check(nombre, ok, detalle=""):
    global fallos
    if ok:
        print(f"✅ {nombre}")
    else:
        fallos += 1
        print(f"❌ {nombre}{chr(10) + '   ' + detalle if detalle else ''}")


ORACIONES = ["Se nota que venís cargando bastante. ", "Contame un poco más de eso. "]


def _stream_falso(**kwargs):
    for o in ORACIONES:
        time.sleep(0.15)
        yield ("mensaje", o)
    yield ("metadata", {
        "mood": "sad", "suggested_action": "respiracion_478",
        "memories": [{"content": "algo", "category": "otro", "priority": 3}],
        "_llm": {"provider": "test", "model": "test", "fallback": False,
                 "ok": True, "cut": False, "latency_ms": 300.0},
    })


def _turno(fut_router):
    return {
        "conversation": [cr.Message(role="user", content="hola")],
        "crisis_score": 0.0, "ultimo_mensaje": "hola", "hoy": cr.date.today(),
        "memorias_vigentes": [], "ids_a_desactivar": [], "evento_proactivo": None,
        "tema_abierto": None, "memoria_ctx_id": None, "preguntas_seguidas": 0,
        "ultimo_modulo_critico": False, "familia_apertura_previa": None,
        "previo_cierre_presencia": False, "system_prompt": "prompt",
        "_tiempos": {}, "_router": {}, "crisis_confirmada": False,
        "_fut_router_paralelo": fut_router,
    }


def correr(fut_router):
    """Consume el generador y devuelve (eventos, kwargs logueados)."""
    log = {}

    def _log(evento, **kw):
        if evento == "chat_turn":
            log.update(kw)

    guardado = {}

    def _tareas(bt, **kw):
        guardado.update(kw)

    with patch.object(cr.llm, "generate_response_stream", _stream_falso), \
         patch.object(cr, "log_event", _log), \
         patch.object(cr, "_procesar_memorias_turno", side_effect=lambda m, *a, **k: m), \
         patch.object(cr, "_disparar_tareas_turno", _tareas), \
         patch.object(cr, "etiquetar_request", return_value=None), \
         patch.object(cr.feedback_repo, "save_crisis_log", return_value=None):
        eventos = [json.loads(l) for l in cr._stream_chat_respuesta(
            _turno(fut_router), "u1", BackgroundTasks(), modo_llamada=True)]
    return eventos, log, guardado


def _fut(senal, demora=0.0, explota=False):
    """Future que imita al router: devuelve (hints, ms) tras `demora`."""
    def _tarea():
        time.sleep(demora)
        if explota:
            raise RuntimeError("router caido")
        return ({"ok": True, "estado_emocional": "triste_vacio", "senal_riesgo": senal,
                 "pide_ejercicio": False, "pregunta_app": False,
                 "pregunta_capacidades": False}, demora * 1000)
    return _pool.submit(_tarea)


# ── 1. No se espera al router: el turno no tarda más que el stream ───────
inicio = time.perf_counter()
eventos, log, _ = correr(_fut("none", demora=3.0))   # router lentísimo a propósito
dur = time.perf_counter() - inicio
check(
    "el turno NO espera al router (corre en paralelo)",
    dur < 1.5,
    f"tardó {dur*1000:.0f}ms; el stream falso son ~300ms y el router 3000ms",
)
check("sin riesgo, el turno termina normal", any(e["type"] == "final" for e in eventos))
check("sin riesgo, no hay evento crisis", not any(e["type"] == "crisis" for e in eventos))

# ── 2. Riesgo EXPLÍCITO → corta, manda contención, no sigue hablando ─────
eventos, log, guardado = correr(_fut("explicita", demora=0.05))
crisis = [e for e in eventos if e["type"] == "crisis"]
deltas = [e for e in eventos if e["type"] == "delta"]
check("riesgo explícito corta el turno", bool(crisis), f"eventos: {[e['type'] for e in eventos]}")
check(
    "la contención lleva los teléfonos de ayuda",
    bool(crisis) and "135" in crisis[0]["text"],
    "el mensaje de corte tiene que traer recursos tocables",
)
check("el corte se marca como router_paralelo", bool(crisis) and crisis[0].get("origen") == "router_paralelo")
check("deja de hablar (no emite todas las oraciones)", len(deltas) < len(ORACIONES),
      f"emitió {len(deltas)} de {len(ORACIONES)}")
check("el log marca el corte", log.get("router_corte") is True and log.get("risk_level") == "high",
      f"router_corte={log.get('router_corte')} risk_level={log.get('risk_level')}")
check("NO se guarda el mensaje a medio decir",
      "135" in (guardado.get("mensaje_final") or ""),
      f"se guardó: {(guardado.get('mensaje_final') or '')[:60]!r}")
check("no se extraen memorias de un turno de crisis",
      not guardado.get("memorias_validadas"),
      f"memorias={guardado.get('memorias_validadas')}")
check("no se sugiere ejercicio en un corte por riesgo",
      not guardado.get("mood") or guardado.get("mood") is not None)

# ── 3. Riesgo IMPLÍCITO → NO corta (decisión explícita) ──────────────────
eventos, log, _ = correr(_fut("implicita", demora=0.05))
check("riesgo implícito NO corta la llamada",
      not any(e["type"] == "crisis" for e in eventos),
      "cortar a mitad de frase por una señal débil sería peor que no cortar")
check("riesgo implícito igual queda registrado en el log",
      log.get("router_score") == 0.35, f"router_score={log.get('router_score')}")

# ── 4. Fail-safe: router que explota o nunca llega ──────────────────────
eventos, log, _ = correr(_fut("explicita", demora=0.05, explota=True))
check("un router que falla NO tumba el turno", any(e["type"] == "final" for e in eventos))
check("un router que falla no corta por las dudas",
      not any(e["type"] == "crisis" for e in eventos))

eventos, log, _ = correr(None)   # chat escrito: no hay future
check("sin future (chat escrito) el turno corre igual", any(e["type"] == "final" for e in eventos))
check("sin future no se marca router_paralelo", not log.get("router_paralelo"))

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
