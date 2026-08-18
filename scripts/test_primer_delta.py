"""
Verifica la instrumentación de latencia percibida (t_primer_delta_ms).

Por qué hace falta un test y no alcanza con "está en el log": el número tiene
que medir el tiempo hasta que sale la PRIMERA oración, no hasta que termina el
stream. Si se midiera mal, la conclusión sería exactamente la contraria a la
real (parecería que el buffer no cuesta nada) y se optimizaría a ciegas.

Se mockea el LLM con un stream de tiempos controlados, así el test no depende
de la red ni de cuánto tarde un modelo real.

Correr con: venv/bin/python scripts/test_primer_delta.py
"""
import os
import sys
import time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import BackgroundTasks

import app.routes.chat_router as cr

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    if ok:
        print(f"✅ {nombre}")
    else:
        fallos += 1
        print(f"❌ {nombre}{chr(10) + '   ' + detalle if detalle else ''}")


# 4 oraciones, 100ms de "generación" cada una. Con retencion=0 la 1ª sale
# apenas cierra; con retencion=2 hay que esperar a que se acumulen 3.
ORACIONES = [
    "Uf, qué semana difícil. ",
    "Tiene mucho sentido que estés así. ",
    "Se nota que venís cargando bastante. ",
    "Acá estoy con vos.",
]
DEMORA_POR_ORACION = 0.1


def _stream_falso(**kwargs):
    for oracion in ORACIONES:
        time.sleep(DEMORA_POR_ORACION)
        yield ("mensaje", oracion)
    yield ("metadata", {
        "mood": "neutral", "suggested_action": None, "memories": [],
        "_llm": {"provider": "test", "model": "test", "fallback": False,
                 "ok": True, "cut": False, "latency_ms": 400.0},
    })


def _turno():
    return {
        "conversation": [cr.Message(role="user", content="hola")],
        "crisis_score": 0.0,
        "ultimo_mensaje": "hola",
        "hoy": cr.date.today(),
        "memorias_vigentes": [],
        "ids_a_desactivar": [],
        "evento_proactivo": None,
        "tema_abierto": None,
        "memoria_ctx_id": None,
        "preguntas_seguidas": 0,
        "ultimo_modulo_critico": False,
        "familia_apertura_previa": None,
        "previo_cierre_presencia": False,
        "system_prompt": "prompt de prueba",
        "_tiempos": {},
        "_router": {},
        "crisis_confirmada": False,
    }


def correr(modo_llamada, t_inicio_request=None):
    """Consume el generador entero y devuelve los kwargs que se loguearon."""
    capturado = {}

    def _log_espia(evento, **kw):
        if evento == "chat_turn":
            capturado.update(kw)

    with patch.object(cr.llm, "generate_response_stream", _stream_falso), \
         patch.object(cr, "log_event", _log_espia), \
         patch.object(cr, "_procesar_memorias_turno", return_value=[]), \
         patch.object(cr, "_disparar_tareas_turno", return_value=None), \
         patch.object(cr, "etiquetar_request", return_value=None):
        gen = cr._stream_chat_respuesta(
            _turno(), "user-test", BackgroundTasks(),
            modo_llamada=modo_llamada, t_inicio_request=t_inicio_request,
        )
        for _ in gen:
            pass
    return capturado


# ── 1. La métrica existe y es coherente ──────────────────────────────────
log_llamada = correr(modo_llamada=True)
pd = log_llamada.get("t_primer_delta_ms")
pt = log_llamada.get("t_llm_primer_token_ms")

check("t_primer_delta_ms se loguea", pd is not None, f"dio {pd}")
check("t_llm_primer_token_ms se loguea", pt is not None, f"dio {pt}")
check(
    "el primer token llega ANTES que el primer delta",
    pd is not None and pt is not None and pt <= pd,
    f"token={pt}ms delta={pd}ms",
)

# ── 2. NO es el stream completo (el bug que se quiere evitar) ────────────
# El stream entero son ~400ms (4 x 100ms). El primer delta en modo llamada
# tiene que salir cerca de la 1ª oración (~100ms), no al final.
total_aprox = len(ORACIONES) * DEMORA_POR_ORACION * 1000
check(
    "t_primer_delta_ms NO mide el stream completo",
    pd is not None and pd < total_aprox * 0.75,
    f"primer delta={pd}ms vs stream completo≈{total_aprox}ms",
)

# ── 3. LO IMPORTANTE: la métrica hace visible lo que cuesta el buffer ────
# Es la razón de ser de todo esto. Si los dos modos dieran igual, el número
# no serviría para decidir nada.
log_escrito = correr(modo_llamada=False)
pd_escrito = log_escrito.get("t_primer_delta_ms")

check(
    "chat escrito (retencion=2) tarda MÁS en el primer delta que llamada (retencion=0)",
    pd is not None and pd_escrito is not None and pd_escrito > pd,
    f"llamada={pd}ms vs escrito={pd_escrito}ms",
)
if pd and pd_escrito:
    print(f"   → el buffer del chat escrito cuesta ~{round(pd_escrito - pd)}ms de silencio extra")

# ── 4. Con t_inicio_request incluye el trabajo previo al LLM ─────────────
# Simula 500ms de _preparar_turno: el número tiene que reflejarlos, porque
# el usuario también los escucha como silencio.
t0 = time.perf_counter() - 0.5
log_con_prep = correr(modo_llamada=True, t_inicio_request=t0)
pd_con_prep = log_con_prep.get("t_primer_delta_ms")
check(
    "t_primer_delta_ms incluye el trabajo previo al LLM (no solo el LLM)",
    pd_con_prep is not None and pd_con_prep >= 500,
    f"dio {pd_con_prep}ms, se esperaba >=500ms (500 de prep + ~100 del LLM)",
)

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
