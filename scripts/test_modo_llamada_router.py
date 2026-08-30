"""
Verifica cómo entra el context_router en _preparar_turno — chat escrito y
modo llamada por igual.

Hasta 2026-08-30 esto probaba una ASIMETRÍA a propósito: modo llamada
lanzaba el router en paralelo sin esperarlo; chat escrito lo esperaba antes
de armar el prompt (pagando sus 1.5-2s enteros). Ese día se unificó: los DOS
modos arman el prompt SIN esperar al router (router_hints ok=False, solo
keywords) y dejan el future para resolverlo después — ver
scripts/test_router_paralelo.py (modo llamada, se consulta SIN bloquear
mientras el LLM principal ya está generando, puede cortar el stream) y
scripts/test_router_paralelo_chat.py (chat escrito, se BLOQUEA después del
LLM principal — no hay nada que "deshacer" todavía — y puede cortar o
regenerar la respuesta).

Este archivo se queda con lo que sigue siendo cierto en los dos modos: que el
router se lanza sin bloquear el armado del turno, y sobre todo, que nada de
esto se llevó puesta la detección de crisis por KEYWORDS, que sigue frenando
los casos críticos igual en los dos modos (eso NUNCA depende del router).

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
        # Señal de riesgo implícito: sirve para confirmar que, aunque el
        # router SÍ corrió, su resultado no llegó a tiempo para el prompt.
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

# ── 1. El router se lanza en los DOS modos, sin bloquear a ninguno ───────
turno_chat, n_chat = correr(NEUTRO, modo_llamada=False)
turno_call, n_call = correr(NEUTRO, modo_llamada=True)

check("chat escrito: el router SÍ se llama", n_chat == 1, f"se llamó {n_chat} veces")
check("modo llamada: el router SÍ se llama", n_call == 1, f"se llamó {n_call} veces")
check("chat escrito: deja el future para resolverlo después del LLM principal",
      turno_chat.get("_fut_router_paralelo") is not None)
check("modo llamada: deja el future para consultarlo durante el stream",
      turno_call.get("_fut_router_paralelo") is not None)

# ── 2. El tiempo reportado distingue "salteado" de "tardó poco" ──────────
check(
    "chat escrito: t_context_router_ms = 0 (no se ESPERÓ acá)",
    turno_chat["_tiempos"].get("t_context_router_ms") == 0.0,
    f"dio {turno_chat['_tiempos'].get('t_context_router_ms')}",
)
check(
    "modo llamada: t_context_router_ms = 0 (no se ESPERÓ acá)",
    turno_call["_tiempos"].get("t_context_router_ms") == 0.0,
    f"dio {turno_call['_tiempos'].get('t_context_router_ms')}",
)

# ── 3. Al armar el prompt, el router todavía no contestó — en NINGÚN modo ─
# Antes esto distinguía los dos modos (chat escrito esperaba, así que acá ya
# tenía el score); ahora es igual en los dos: el resultado llega DESPUÉS,
# y quién lo resuelve y qué hace con él es justo lo que prueban
# test_router_paralelo.py (llamada) y test_router_paralelo_chat.py (chat).
check(
    "chat escrito: al armar el prompt el score todavía no tiene al router",
    turno_chat["crisis_score"] < 0.35,
    f"score={turno_chat['crisis_score']}",
)
check(
    "modo llamada: al armar el prompt el score todavía no tiene al router",
    turno_call["crisis_score"] < 0.35,
    f"score={turno_call['crisis_score']}",
)

# ── 4. LO QUE NO SE PUEDE ROMPER: las keywords siguen frenando la crisis ─
# Esto es lo único que separa un mensaje crítico de una respuesta normal del
# LLM, en los dos modos. Si algún día esto falla, algo se volvió inseguro.
# Nunca pasó por el router — detectar_crisis + confirmar_riesgo_real, sin
# cambios en este trabajo.
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

# ── 5. El prompt arranca sin la señal del router — en los DOS modos ──────
# Frases con MÉTODO o PLAN explícito que el detector por keywords NO matchea
# (verificado: detectar_crisis les da score 0.0). Las agarra ÚNICAMENTE el
# context_router, clasificándolas "explicita" → 0.6. Antes esto era EL
# agujero que corría solo en modo llamada (chat escrito ya tenía cobertura
# porque esperaba). Ahora los dos arrancan igual, sin la señal — la cobertura
# real (que no se pierda del todo) la prueban test_router_paralelo.py
# (corta el stream) y test_router_paralelo_chat.py (corta o regenera la
# respuesta) por su cuenta, con el mecanismo genérico de score, no con estas
# frases puntuales.
SOLO_LOS_AGARRA_EL_ROUTER = [
    "tengo pastillas y me las voy a tomar todas",
    "guardé todo lo que necesito para terminar con esto",
    "me quiero cortar las venas",
    "no quiero vivir más",
]
print()
print("-- método/plan sin keyword: el prompt arranca sin la señal en los dos modos --")
for texto in SOLO_LOS_AGARRA_EL_ROUTER:
    t_call, _ = correr(texto, modo_llamada=True)
    t_chat, _ = correr(texto, modo_llamada=False)
    check(
        f"chat escrito: el prompt se arma sin la señal del router → {texto[:34]!r}",
        t_chat["crisis_score"] == 0.0,
        f"score={t_chat['crisis_score']} — la cobertura llega después de llamar al LLM",
    )
    check(
        f"modo llamada: el prompt se arma sin la señal del router → {texto[:34]!r}",
        t_call["crisis_score"] == 0.0,
        f"score={t_call['crisis_score']} — la cobertura llega después, durante el stream",
    )

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
