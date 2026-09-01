"""
Verifica /chat/stream/voz: el endpoint que fusiona STT + chat en streaming en
un solo viaje de red (antes eran dos requests secuenciales: /speech-to-text y
recién después /chat/stream — ver el docstring del endpoint en
chat_router.py).

Qué se verifica, y por qué cada uno importa:

  1. Camino feliz: sube audio, transcribe (mockeado), arma el turno con el
     texto transcripto como ÚLTIMO mensaje de la conversación, y streamea
     igual que /chat/stream — un solo request de principio a fin.
  2. Transcripción vacía (silencio/ruido): NO se llama a _preparar_turno ni al
     LLM — se corta ahí con el evento {"type": "vacio"}, sin gastar un turno.
  3. Audio demasiado corto / demasiado largo: 400 / 413, igual que
     /speech-to-text, sin llegar a transcribir.
  4. STT cae (Groq): 503, sin intentar armar el turno.
  5. payload mal formado (no es JSON válido): 400.
  6. Crisis confirmada por keywords: el audio transcribe a un mensaje de
     riesgo, se corta ANTES del LLM con la respuesta hardcodeada — mismo
     camino que ya tenía /chat/stream, no algo nuevo de este endpoint.
  7. modo_llamada queda en True SIEMPRE (no lo manda el cliente): es el punto
     entero del endpoint, a diferencia de /chat/stream donde sí lo manda el
     caller.
  8. El historial previo (conversation del payload) se preserva y el texto
     transcripto se agrega DESPUÉS, no lo reemplaza.

Correr con: venv/bin/python scripts/test_chat_stream_voz.py
"""
import io
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

AUDIO_OK = b"\x00" * 6000  # > 5000 bytes, el mínimo que exige el endpoint
AUDIO_CORTO = b"\x00" * 100
AUDIO_LARGO = b"\x00" * (11 * 1024 * 1024)  # > MAX_AUDIO_BYTES (10MB)


def _payload(conversation=None, perfil=None):
    return json.dumps({
        "conversation": conversation or [],
        "perfil": perfil if perfil is not None else {},
        "ubicacion": None,
        "ultimo_mood": "neutral",
    })


def _mock_llm_stream(mensaje="hola, ¿cómo estás?", mood="neutral"):
    def _fake(*, conversation, system_prompt, modo_llamada=False):
        yield ("mensaje", mensaje)
        yield ("metadata", {
            "mood": mood, "suggested_action": None, "memories": [],
            "_llm": {"provider": "test", "model": "test", "latency_ms": 1},
        })
    return _fake


def _parches_preparar_turno():
    """Los mismos mocks que test_router_paralelo_chat.py usa para que
    _preparar_turno no le pegue a Supabase de verdad, más los de
    _disparar_tareas_turno: a diferencia de aquel script, acá se pega con un
    TestClient real de punta a punta y las background tasks SÍ corren dentro
    del mismo request (a diferencia de un servidor real) — sin estos mocks
    conversation_repo.save() intentaría un insert real con user_id="test-user-id",
    que ni siquiera es un UUID válido."""
    return [
        patch.object(cr, "get_recent_memories", return_value=([], [])),
        # modo_llamada=True (siempre, en este endpoint) usa la variante
        # cacheada, no get_recent_memories — ver _tarea_memorias en
        # chat_router.py.
        patch.object(cr, "get_recent_memories_cached", return_value=([], [])),
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


# ── 1. Camino feliz ───────────────────────────────────────────────────
parches = _entrar(_parches_preparar_turno())
try:
    with patch.object(cr, "speech_to_text", return_value="hola numa, ¿cómo estás?"), \
         patch.object(cr.llm, "generate_response_stream", side_effect=_mock_llm_stream()):
        r = client.post(
            "/chat/stream/voz",
            files={"audio": ("audio.m4a", io.BytesIO(AUDIO_OK), "audio/m4a")},
            data={"payload": _payload()},
        )
    check("responde 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    lineas = [json.loads(l) for l in r.text.strip().split("\n") if l.strip()]
    tipos = [l["type"] for l in lineas]
    check("emite al menos un delta y un final", "delta" in tipos and "final" in tipos, f"tipos={tipos}")
    delta = next((l for l in lineas if l["type"] == "delta"), None)
    check("el delta trae el mensaje mockeado", delta and "cómo estás" in delta["text"], f"delta={delta}")
    check("la PRIMERA línea es 'texto_usuario' (el cliente ya no transcribe)",
          lineas and lineas[0] == {"type": "texto_usuario", "text": "hola numa, ¿cómo estás?"},
          f"primera_linea={lineas[0] if lineas else None}")
finally:
    _salir(parches)

# ── 2. Transcripción vacía: no gasta turno de LLM ───────────────────────
parches = _entrar(_parches_preparar_turno())
try:
    llamadas_llm = {"n": 0}

    def _llm_no_deberia_llamarse(**kw):
        llamadas_llm["n"] += 1
        yield ("mensaje", "no debería llegar acá")

    with patch.object(cr, "speech_to_text", return_value="   "), \
         patch.object(cr.llm, "generate_response_stream", side_effect=_llm_no_deberia_llamarse):
        r = client.post(
            "/chat/stream/voz",
            files={"audio": ("audio.m4a", io.BytesIO(AUDIO_OK), "audio/m4a")},
            data={"payload": _payload()},
        )
    check("transcripción vacía responde 200 igual", r.status_code == 200)
    lineas = [json.loads(l) for l in r.text.strip().split("\n") if l.strip()]
    check("emite solo el evento 'vacio'", [l["type"] for l in lineas] == ["vacio"], f"lineas={lineas}")
    check("NO se llamó al LLM (no se gastó un turno)", llamadas_llm["n"] == 0)
finally:
    _salir(parches)

# ── 3. Audio demasiado corto / demasiado largo ──────────────────────────
r = client.post(
    "/chat/stream/voz",
    files={"audio": ("audio.m4a", io.BytesIO(AUDIO_CORTO), "audio/m4a")},
    data={"payload": _payload()},
)
check("audio demasiado corto -> 400", r.status_code == 400, f"status={r.status_code}")

r = client.post(
    "/chat/stream/voz",
    files={"audio": ("audio.m4a", io.BytesIO(AUDIO_LARGO), "audio/m4a")},
    data={"payload": _payload()},
)
check("audio demasiado largo -> 413", r.status_code == 413, f"status={r.status_code}")

# ── 4. STT cae ────────────────────────────────────────────────────────
with patch.object(cr, "speech_to_text", side_effect=RuntimeError("groq caído")):
    r = client.post(
        "/chat/stream/voz",
        files={"audio": ("audio.m4a", io.BytesIO(AUDIO_OK), "audio/m4a")},
        data={"payload": _payload()},
    )
check("STT caído -> 503", r.status_code == 503, f"status={r.status_code}")

# ── 5. payload mal formado ────────────────────────────────────────────
r = client.post(
    "/chat/stream/voz",
    files={"audio": ("audio.m4a", io.BytesIO(AUDIO_OK), "audio/m4a")},
    data={"payload": "esto no es json"},
)
check("payload inválido -> 400", r.status_code == 400, f"status={r.status_code}")

# ── 6. Crisis confirmada por keywords ────────────────────────────────
parches = _entrar(_parches_preparar_turno())
try:
    with patch.object(cr, "speech_to_text", return_value="me quiero matar"), \
         patch.object(cr, "confirmar_riesgo_real", return_value=True), \
         patch.object(cr.feedback_repo, "save_crisis_log", lambda *a, **k: None):
        r = client.post(
            "/chat/stream/voz",
            files={"audio": ("audio.m4a", io.BytesIO(AUDIO_OK), "audio/m4a")},
            data={"payload": _payload()},
        )
    check("crisis confirmada responde 200", r.status_code == 200)
    lineas = [json.loads(l) for l in r.text.strip().split("\n") if l.strip()]
    check("primer evento es 'texto_usuario' incluso en crisis (el cliente lo necesita igual)",
          lineas and lineas[0] == {"type": "texto_usuario", "text": "me quiero matar"}, f"lineas={lineas}")
    check("segundo evento es 'crisis'", len(lineas) > 1 and lineas[1]["type"] == "crisis", f"lineas={lineas}")
    check("la contención lleva los teléfonos de ayuda",
          len(lineas) > 1 and "135" in lineas[1].get("text", ""), f"lineas={lineas}")
finally:
    _salir(parches)

# ── 7 y 8. modo_llamada=True siempre, y el historial previo se conserva ─
parches = _entrar(_parches_preparar_turno())
try:
    capturado = {}
    _preparar_turno_real = cr._preparar_turno

    def _preparar_turno_espia(body, user_id, background_tasks):
        capturado["conversation"] = [m.content for m in body.conversation]
        capturado["modo_llamada"] = body.modo_llamada
        return _preparar_turno_real(body, user_id, background_tasks)

    with patch.object(cr, "speech_to_text", return_value="che numa, ¿seguís ahí?"), \
         patch.object(cr, "_preparar_turno", side_effect=_preparar_turno_espia), \
         patch.object(cr.llm, "generate_response_stream", side_effect=_mock_llm_stream()):
        r = client.post(
            "/chat/stream/voz",
            files={"audio": ("audio.m4a", io.BytesIO(AUDIO_OK), "audio/m4a")},
            data={"payload": _payload(conversation=[
                {"role": "user", "content": "hola"},
                {"role": "assistant", "content": "hola, ¿cómo estás?"},
            ])},
        )
    check("responde 200", r.status_code == 200)
    check("modo_llamada quedó en True", capturado.get("modo_llamada") is True, f"capturado={capturado}")
    check(
        "el historial previo se conserva y el texto transcripto se agrega al final",
        capturado.get("conversation") == ["hola", "hola, ¿cómo estás?", "che numa, ¿seguís ahí?"],
        f"conversation={capturado.get('conversation')}",
    )
finally:
    _salir(parches)

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
