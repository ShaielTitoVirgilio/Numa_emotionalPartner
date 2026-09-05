"""
Verifica /chat/stream en main (agregado 2026-09-04: faltaba, causó el bug
real reportado en numa-mobile — "POST /chat/stream 404" apenas se subió el
typewriter del chat escrito a producción sin este endpoint en el backend).

A diferencia de staging, acá NO hay modo_llamada: ChatRequest no tiene ese
campo, así que este test solo cubre el camino de chat escrito.

Correr con: venv/bin/python scripts/test_chat_stream_main.py
"""
import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

import app.routes.chat_router as cr
from app.core.auth import get_current_user_id
from app.main import app

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    if ok:
        print(f"✅ {nombre}")
    else:
        fallos += 1
        print(f"❌ {nombre}{chr(10) + '   ' + detalle if detalle else ''}")


app.dependency_overrides[get_current_user_id] = lambda: "test-user-id"
client = TestClient(app)


def _parches_preparar_turno():
    return [
        patch.object(cr, "get_recent_memories", return_value=([], [])),
        patch.object(cr, "get_topic_patterns_cached", return_value=[]),
        patch.object(cr, "get_dias_inactivo", return_value=0),
        patch.object(cr, "get_checkin_hoy_cached", return_value=None),
        patch.object(cr, "get_proactive_memories", return_value=[]),
        patch.object(cr.feedback_repo, "hay_crisis_reciente", return_value=False),
        patch.object(cr, "clasificar_contexto", return_value=dict(cr.resultado_vacio())),
        patch.object(cr.conversation_repo, "save", lambda *a, **k: None),
        patch.object(cr.conversation_repo, "deactivate_memories", lambda *a, **k: None),
        patch.object(cr, "marcar_evento_followup", lambda *a, **k: None),
        patch.object(cr, "cerrar_temas_abiertos", lambda *a, **k: None),
        patch.object(cr, "marcar_proactivo_insertado", lambda *a, **k: None),
        patch.object(cr, "invalidate_patterns_cache", lambda *a, **k: None),
    ]


def _entrar(parches):
    for p in parches:
        p.start()
    return parches


def _salir(parches):
    for p in parches:
        p.stop()


def _mock_llm_stream(mensaje="hola, ¿cómo estás?", mood="neutral"):
    def _fake(*, conversation, system_prompt):
        yield ("mensaje", mensaje)
        yield ("metadata", {
            "mood": mood, "suggested_action": None, "memories": [],
            "_llm": {"provider": "test", "model": "test", "latency_ms": 1},
        })
    return _fake


def _payload(conversation=None):
    return {
        "conversation": conversation or [{"role": "user", "content": "hola, ¿cómo estás?"}],
        "perfil": {},
        "ubicacion": None,
        "ultimo_mood": "neutral",
    }


# ── 1. Camino feliz ───────────────────────────────────────────────────
parches = _entrar(_parches_preparar_turno())
try:
    with patch.object(cr.llm, "generate_response_stream", side_effect=_mock_llm_stream()):
        r = client.post("/chat/stream", json=_payload())
    check("responde 200 (no 404)", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    lineas = [json.loads(l) for l in r.text.strip().split("\n") if l.strip()]
    tipos = [l["type"] for l in lineas]
    check("emite al menos un delta y un final", "delta" in tipos and "final" in tipos, f"tipos={tipos}")
    delta = next((l for l in lineas if l["type"] == "delta"), None)
    check("el delta trae el mensaje mockeado", delta and "cómo estás" in delta["text"], f"delta={delta}")
    final = next((l for l in lineas if l["type"] == "final"), None)
    check("el final trae mood/risk_level", final and final.get("mood") == "neutral" and final.get("risk_level") == "none", f"final={final}")
finally:
    _salir(parches)

# ── 2. Crisis confirmada por keywords: corta ANTES del LLM ──────────────
parches = _entrar(_parches_preparar_turno())
try:
    llamadas_llm = {"n": 0}

    def _llm_no_deberia_llamarse(**kw):
        llamadas_llm["n"] += 1
        yield ("mensaje", "no debería llegar acá")

    with patch.object(cr, "confirmar_riesgo_real", return_value=True), \
         patch.object(cr.feedback_repo, "save_crisis_log", lambda *a, **k: None), \
         patch.object(cr.llm, "generate_response_stream", side_effect=_llm_no_deberia_llamarse):
        r = client.post("/chat/stream", json=_payload([{"role": "user", "content": "me quiero matar"}]))
    check("crisis responde 200", r.status_code == 200)
    lineas = [json.loads(l) for l in r.text.strip().split("\n") if l.strip()]
    check("primer evento es 'crisis'", lineas and lineas[0]["type"] == "crisis", f"lineas={lineas}")
    check("la contención lleva los teléfonos de ayuda", lineas and "135" in lineas[0].get("text", ""), f"lineas={lineas}")
    check("NO se llamó al LLM", llamadas_llm["n"] == 0)
finally:
    _salir(parches)

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
