"""
Verifica el apagado del context_router en modo llamada.

Lo que importa acá NO es la latencia (eso se mide en los logs), es que el
apagado esté acotado EXACTAMENTE al modo llamada y que no se haya llevado
puesta la detección de crisis por keywords, que es la que frena los casos
críticos/altos y sigue activa en los dos modos.

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
check("modo llamada: el router NO se llama", n_call == 0, f"se llamó {n_call} veces")

# ── 2. El tiempo reportado distingue "salteado" de "tardó poco" ──────────
check(
    "modo llamada: t_context_router_ms = 0 (salteado)",
    turno_call["_tiempos"].get("t_context_router_ms") == 0.0,
    f"dio {turno_call['_tiempos'].get('t_context_router_ms')}",
)

# ── 3. Sin router, la señal implícita ya NO escala el riesgo ─────────────
# Es el trade-off aceptado a propósito: en llamada solo escalan las keywords.
check(
    "chat escrito: la señal implícita del router escala el score",
    turno_chat["crisis_score"] >= 0.35,
    f"score={turno_chat['crisis_score']}",
)
check(
    "modo llamada: la señal implícita ya no escala (trade-off aceptado)",
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

# ── 5. EL AGUJERO QUE ABRE ESTE CAMBIO (documentado, no es un bug) ───────
# Frases con MÉTODO o PLAN explícito que el detector por keywords NO matchea
# (verificado: detectar_crisis les da score 0.0). Hoy las agarra ÚNICAMENTE
# el context_router, que las clasifica "explicita" → 0.6 → activa los módulos
# de crisis en el prompt.
#
# Con el router apagado, en modo llamada estas frases pasan como un mensaje
# cualquiera: score 0.0, CERO módulos de crisis. Y es justo el escenario que
# una llamada de voz hace MÁS probable, porque en voz la gente dice cosas que
# no escribiría.
#
# Este bloque NO falla el test a propósito: deja constancia ejecutable del
# alcance real del trade-off. Si algún día se tapa (keywords nuevas, router
# rápido, chequeo en paralelo), estos asserts se dan vuelta y hay que
# actualizarlos — que es exactamente cuando uno quiere enterarse.
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
print("-- agujero conocido: método/plan sin keyword --")
for texto in SOLO_LOS_AGARRA_EL_ROUTER:
    t_call, _ = correr(texto, modo_llamada=True)
    t_chat, _ = correr(texto, modo_llamada=False)
    check(
        f"chat escrito: el router lo escala → {texto[:34]!r}",
        t_chat["crisis_score"] >= 0.35,
        f"score={t_chat['crisis_score']}",
    )
    check(
        f"modo llamada: queda SIN cobertura (score 0) → {texto[:34]!r}",
        t_call["crisis_score"] == 0.0,
        f"score={t_call['crisis_score']} (si ya no es 0, se tapó el agujero: actualizar este test)",
    )

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
