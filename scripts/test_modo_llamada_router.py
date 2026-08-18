"""
Verifica cómo entra el context_router en modo llamada (paralelo, no bloqueante).

Este archivo cubre el ARMADO DEL TURNO: que el router se lance sin que el
turno lo espere, que el camino paralelo esté acotado EXACTAMENTE al modo
llamada, y que nada de esto se haya llevado puesta la detección de crisis por
keywords, que frena los casos críticos y sigue igual en los dos modos.

Lo que pasa DESPUÉS (consultar el resultado durante el stream y cortar la
llamada si hay riesgo explícito) se prueba en scripts/test_router_paralelo.py.

Se mockea clasificar_contexto (para contar si se llamó o no) y todo lo que
pega contra Supabase/LLM, así corre sin red ni credenciales.

Correr con: venv/bin/python scripts/test_modo_llamada_router.py
"""
import os
import sys
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


def _body(texto, modo_llamada):
    return cr.ChatRequest(
        conversation=[cr.Message(role="user", content=texto)],
        perfil={},                 # perfil provisto = no pega a Supabase
        modo_llamada=modo_llamada,
    )


def correr(texto, modo_llamada):
    """Corre _preparar_turno con todo el I/O externo mockeado.
    Devuelve (turno, veces_que_se_llamo_al_router)."""
    llamadas = {"n": 0}

    def _router_espia(conversation):
        llamadas["n"] += 1
        # Señal de riesgo implícito: si el router estuviera prendido, esto
        # escalaría el crisis_score. Sirve para probar que en llamada NO pasa.
        return {"ok": True, "estado_emocional": "triste_vacio",
                "senal_riesgo": "implicita", "pide_ejercicio": False,
                "pregunta_app": False, "pregunta_capacidades": False}

    with patch.object(cr, "clasificar_contexto", _router_espia), \
         patch.object(cr, "get_recent_memories", return_value=([], [])), \
         patch.object(cr, "get_topic_patterns_cached", return_value=[]), \
         patch.object(cr, "get_checkin_hoy_cached", return_value=None), \
         patch.object(cr, "get_dias_inactivo", return_value=0), \
         patch.object(cr, "get_proactive_memories", return_value=[]), \
         patch.object(cr, "get_resource_memories", return_value=[]), \
         patch.object(cr, "get_open_topics", return_value=[]), \
         patch.object(cr.feedback_repo, "hay_crisis_reciente", return_value=False), \
         patch.object(cr.feedback_repo, "save_crisis_log", return_value=None), \
         patch.object(cr, "confirmar_riesgo_real", return_value=True):
        turno = cr._preparar_turno(_body(texto, modo_llamada), "user-test", BackgroundTasks())
    return turno, llamadas["n"]


NEUTRO = "Hoy estuve ordenando la casa y salió el sol un rato."

# ── 1. El apagado está acotado al modo llamada ───────────────────────────
turno_chat, n_chat = correr(NEUTRO, modo_llamada=False)
turno_call, n_call = correr(NEUTRO, modo_llamada=True)

check("chat escrito: el router SÍ se llama (sin cambios)", n_chat == 1, f"se llamó {n_chat} veces")
# En llamada TAMBIÉN se llama, pero en paralelo: se lanza y no se espera. Que
# se llame es justamente lo que devolvió la cobertura de riesgo implícito que
# el apagado había sacado — ver scripts/test_router_paralelo.py.
check("modo llamada: el router SÍ se llama (en paralelo)", n_call == 1, f"se llamó {n_call} veces")
check("modo llamada: deja el future para consultarlo durante el stream",
      turno_call.get("_fut_router_paralelo") is not None)
check("chat escrito: NO usa el camino paralelo",
      turno_chat.get("_fut_router_paralelo") is None)

# ── 2. El tiempo reportado distingue "salteado" de "tardó poco" ──────────
check(
    "modo llamada: t_context_router_ms = 0 (no se ESPERÓ acá)",
    turno_call["_tiempos"].get("t_context_router_ms") == 0.0,
    f"dio {turno_call['_tiempos'].get('t_context_router_ms')}",
)

# ── 3. Al armar el prompt, el router todavía no contestó ────────────────
check(
    "chat escrito: la señal implícita del router escala el score",
    turno_chat["crisis_score"] >= 0.35,
    f"score={turno_chat['crisis_score']}",
)
# En el momento de armar el prompt el router todavía no contestó, así que el
# score arranca en 0: eso NO cambió y es el precio de no bloquear. La
# diferencia es que ahora el resultado llega igual, durante el stream, y ahí
# se decide si cortar (test_router_paralelo.py cubre esa parte).
check(
    "modo llamada: al armar el prompt el score todavía no tiene al router",
    turno_call["crisis_score"] < 0.35,
    f"score={turno_call['crisis_score']}",
)

# ── 4. LO QUE NO SE PUEDE ROMPER: las keywords siguen frenando la crisis ─
# Esto es lo único que separa un mensaje crítico de una respuesta normal del
# LLM en modo llamada. Si algún día esto falla, el apagado se volvió inseguro.
CRITICOS_POR_KEYWORD = [
    "me quiero matar",          # SUICIDAL_IDEATION
    "me voy a suicidar",        # SUICIDAL_IDEATION
    "como me mato",             # SUICIDE_METHOD
    "quiero cortarme",          # SELF_HARM
]
for texto in CRITICOS_POR_KEYWORD:
    t_call, _ = correr(texto, modo_llamada=True)
    check(
        f"modo llamada: crisis por keywords SIGUE frenando → {texto[:34]!r}",
        t_call.get("crisis_confirmada") is True,
        f"crisis_confirmada={t_call.get('crisis_confirmada')}, score={t_call.get('crisis_score')}",
    )
    t_chat, _ = correr(texto, modo_llamada=False)
    check(
        f"chat escrito: mismo mensaje, mismo freno → {texto[:34]!r}",
        t_chat.get("crisis_confirmada") is True,
        f"crisis_confirmada={t_chat.get('crisis_confirmada')}",
    )

# ── 5. EL AGUJERO QUE ESTE CAMBIO YA NO DEJA ABIERTO ────────────────────
# (histórico) Cuando el router estaba APAGADO en llamada, estas frases
# quedaban en score 0.0 y sin ningún módulo de crisis. Hoy el router corre en
# paralelo y las cubre cortando el turno — ver test_router_paralelo.py. Lo que
# sigue verificando este bloque es que el prompt SE ARMA sin esa señal (el
# router todavía no contestó), que es distinto de quedarse sin cobertura.
# Frases con MÉTODO o PLAN explícito que el detector por keywords NO matchea
# (verificado: detectar_crisis les da score 0.0). Las agarra ÚNICAMENTE el
# context_router, clasificándolas "explicita" → 0.6.
#
# Ojo con las dos últimas: son variantes de FRASEO de cosas que la lista de
# keywords sí tiene ("cortarme las venas", "no quiero seguir viviendo"), pero
# dichas como las diría una persona de verdad. Que se escapen muestra que la
# capa de keywords es más frágil de lo que aparenta, y que el router venía
# tapando esos huecos sin que se notara.
SOLO_LOS_AGARRA_EL_ROUTER = [
    "tengo pastillas y me las voy a tomar todas",
    "guardé todo lo que necesito para terminar con esto",
    "me quiero cortar las venas",
    "no quiero vivir más",
]
print()
print("-- método/plan sin keyword: el prompt arranca sin la señal (llega durante el stream) --")
for texto in SOLO_LOS_AGARRA_EL_ROUTER:
    t_call, _ = correr(texto, modo_llamada=True)
    t_chat, _ = correr(texto, modo_llamada=False)
    check(
        f"chat escrito: el router lo escala → {texto[:34]!r}",
        t_chat["crisis_score"] >= 0.35,
        f"score={t_chat['crisis_score']}",
    )
    check(
        f"modo llamada: el prompt se arma sin la señal del router → {texto[:34]!r}",
        t_call["crisis_score"] == 0.0,
        f"score={t_call['crisis_score']} — la cobertura llega después, durante el stream",
    )

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
