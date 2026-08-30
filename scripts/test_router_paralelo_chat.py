"""
Verifica el context_router EN PARALELO para /chat (chat escrito, no streaming).

Contraparte de scripts/test_router_paralelo.py (que cubre modo llamada). Ahí
el router corre en paralelo y, si detecta riesgo, CORTA el stream a mitad de
camino porque no hay forma de "deshacer" lo ya hablado. Acá es distinto:
/chat no le manda nada al usuario hasta tener la respuesta completa, así que
SÍ se puede esperar el resultado final del router antes de devolver algo —
solo que ahora esa espera pasa DESPUÉS de llamar al LLM principal (que
normalmente tarda más), no antes, y por eso no cuesta nada en la práctica.

Qué se verifica, y por qué cada uno importa:

  1. El turno NO espera al router ANTES de llamar al LLM principal (razón de
     ser de todo el cambio) — se mide con _preparar_turno solo.
  2. Riesgo EXPLÍCITO (score >= UMBRAL_CORTE_LLAMADA) que las keywords no
     vieron: se descarta la respuesta ya generada y se devuelve la MISMA
     contención hardcodeada que el resto de los caminos de crisis — sin
     pagar una segunda llamada al LLM (verificado contando llamadas).
  3. Riesgo MEDIO (score >= 0.35) que las keywords no vieron: se REGENERA con
     el prompt correcto (una segunda llamada al LLM, la única vez que esto
     pasa).
  4. Un salto de score que NO cruza una banda nueva (ej. 0.50 -> 0.55, crisis
     modules ya estaban activados con 0.50) NO regenera — sería gasto sin
     ningún cambio real en el prompt (numa_prompt.seleccionar_modulos solo
     corta en 0.35 y 0.60).
  5. El router puede escalar directo a "corte" aunque ya venía en banda
     media (0.45 -> 0.65 cruza el corte de 0.60 que 0.45 no había cruzado).
  6. Un router que falla (excepción) o nunca se lanzó (None) es fail-safe:
     no revienta, no actúa — sigue con lo que ya había.
  7. Cuando SÍ corta, se guarda un crisis_log con nivel "high"; cuando
     regenera, con nivel "medium" — para poder auditar la tasa real después.
  8. La memoria proactiva (evento/tema abierto) se anula cuando corta o
     regenera — no tiene sentido mostrarla en un turno que resultó ser de
     riesgo.

Correr con: venv/bin/python scripts/test_router_paralelo_chat.py
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import BackgroundTasks

import app.routes.chat_router as cr

fallos = 0
_pool = ThreadPoolExecutor(max_workers=8)


def check(nombre, ok, detalle=""):
    global fallos
    if ok:
        print(f"✅ {nombre}")
    else:
        fallos += 1
        print(f"❌ {nombre}{chr(10) + '   ' + detalle if detalle else ''}")


def _fut(senal, demora=0.0, explota=False, ok=True):
    """Future que imita al router: devuelve (hints, ms) tras `demora`."""
    def _tarea():
        time.sleep(demora)
        if explota:
            raise RuntimeError("router caido")
        return ({"ok": ok, "estado_emocional": "triste_vacio", "senal_riesgo": senal,
                 "pide_ejercicio": False, "pregunta_app": False,
                 "pregunta_capacidades": False}, demora * 1000)
    return _pool.submit(_tarea)


def _resolver(fut_router, crisis_score=0.0, resultado_llm=None):
    """Llama a _resolver_router_paralelo_chat con dependencias falsas,
    devuelve (resolucion, veces_que_se_llamo_al_llm, crisis_logs_guardados)."""
    llamadas_llm = {"n": 0}
    crisis_logs = []

    def _llamar_llm(system_prompt):
        llamadas_llm["n"] += 1
        return resultado_llm or {
            "message": "respuesta regenerada", "mood": "sad",
            "suggested_action": None, "memories": [],
            "_llm": {"provider": "test", "model": "test"},
        }

    def _reconstruir_prompt(crisis_score_, router_hints_, evento_, tema_, recurso_):
        return f"prompt regenerado score={crisis_score_}"

    bt = BackgroundTasks()

    def _log_crisis(user_id, mensaje, categoria, nivel):
        crisis_logs.append((categoria, nivel))

    with patch.object(cr.feedback_repo, "save_crisis_log", _log_crisis):
        resolucion = cr._resolver_router_paralelo_chat(
            fut_router_paralelo=fut_router,
            crisis_score=crisis_score,
            ultimo_mensaje="hola",
            user_id="u1",
            background_tasks=bt,
            reconstruir_prompt=_reconstruir_prompt,
            llamar_llm=_llamar_llm,
            evento_proactivo={"tipo": "evento"},
            tema_abierto=None,
            memoria_ctx_id="mem-1",
        )
        # Las tareas de background no corren solas en este test — se ejecutan
        # a mano (BackgroundTask.__call__ es async; se llama al func real
        # directo para no tener que meter un event loop acá) para poder
        # verificar qué se hubiera guardado.
        for tarea in bt.tasks:
            tarea.func(*tarea.args, **tarea.kwargs)

    return resolucion, llamadas_llm["n"], crisis_logs


# ── 1. _preparar_turno NO espera al router (antes de llamar al LLM) ──────
def _turno_rapido(fut_router_lento):
    """Simula _preparar_turno con router lentísimo, para medir que el bloque
    paralelo de Supabase (memorias/patrones/metadatos) no se contagia de la
    lentitud del router — que es justo lo que se sacó."""
    # perfil={} de una: sin esto, _preparar_turno pega a user_repo.get_profile
    # (Supabase real) porque body.perfil es None por default.
    body = cr.ChatRequest(
        conversation=[cr.Message(role="user", content="hola, ¿cómo estás?")], perfil={},
    )
    with patch.object(cr, "clasificar_contexto", side_effect=lambda conv: fut_router_lento.result()[0]), \
         patch.object(cr, "_EJECUTOR_ROUTER_PARALELO") as ejecutor_mock, \
         patch.object(cr, "get_recent_memories", return_value=([], [])), \
         patch.object(cr, "get_topic_patterns_cached", return_value=[]), \
         patch.object(cr, "get_dias_inactivo", return_value=0), \
         patch.object(cr, "get_checkin_hoy_cached", return_value=None), \
         patch.object(cr, "get_proactive_memories", return_value=[]), \
         patch.object(cr.feedback_repo, "hay_crisis_reciente", return_value=False):
        ejecutor_mock.submit.return_value = fut_router_lento
        return cr._preparar_turno(body, "u1", BackgroundTasks())


inicio = time.perf_counter()
fut_lento = _fut("none", demora=2.0)  # router lentísimo a propósito
turno = _turno_rapido(fut_lento)
dur = time.perf_counter() - inicio
check(
    "_preparar_turno NO espera al router (corre en paralelo)",
    dur < 1.0,
    f"tardó {dur*1000:.0f}ms; el router simulado tarda 2000ms",
)
check("el prompt se arma con router_hints ok=False (solo keywords)",
      turno["_tiempos"].get("t_context_router_ms") == 0.0)
check("_fut_router_paralelo queda guardado para resolver después",
      turno.get("_fut_router_paralelo") is fut_lento)

# ── 2. Riesgo EXPLÍCITO → corta, sin pagar una segunda llamada al LLM ────
resolucion, n_llm, logs = _resolver(_fut("explicita", demora=0.05), crisis_score=0.0)
check("riesgo explícito corta (respuesta_corte no es None)",
      resolucion["respuesta_corte"] is not None)
check("el corte NO paga una segunda llamada al LLM (usa la contención fija)",
      n_llm == 0, f"llamó al LLM {n_llm} veces")
check("la contención lleva los teléfonos de ayuda",
      "135" in resolucion["respuesta_corte"]["message"])
check("risk_level del corte es high",
      resolucion["respuesta_corte"]["risk_level"] == "high")
check("se guarda un crisis_log de nivel high",
      logs == [("ROUTER_PARALELO_CHAT", "high")], f"logs={logs}")
check("diag marca router_accion=corte", resolucion["diag"]["router_accion"] == "corte")
check("la memoria proactiva se anula en el corte",
      resolucion["evento_proactivo"] is None and resolucion["memoria_ctx_id"] is None)

# ── 3. Riesgo MEDIO → regenera (UNA sola llamada extra al LLM) ───────────
resolucion, n_llm, logs = _resolver(_fut("implicita", demora=0.05), crisis_score=0.0)
check("riesgo medio NO corta (respuesta_corte es None)",
      resolucion["respuesta_corte"] is None)
check("riesgo medio regenera (result no es None)", resolucion["result"] is not None)
check("regenera con UNA sola llamada extra al LLM", n_llm == 1, f"llamó {n_llm} veces")
check("crisis_score queda actualizado al del router",
      resolucion["crisis_score"] == cr.score_riesgo_router("implicita"))
check("se guarda un crisis_log de nivel medium",
      logs == [("ROUTER_PARALELO_CHAT", "medium")], f"logs={logs}")
check("diag marca router_accion=regenero", resolucion["diag"]["router_accion"] == "regenero")
check("la memoria proactiva se anula al regenerar (ya no correspondería)",
      resolucion["evento_proactivo"] is None and resolucion["memoria_ctx_id"] is None)

# ── 4. Salto DENTRO de la misma banda → NO regenera (sería gasto) ────────
resolucion, n_llm, logs = _resolver(
    _fut("implicita", demora=0.05), crisis_score=0.45,  # ya en banda media
)
check("un score de router que no cruza una banda NUEVA no hace nada",
      resolucion["respuesta_corte"] is None and resolucion["result"] is None,
      f"resolucion={resolucion}")
check("no paga ninguna llamada extra al LLM en este caso", n_llm == 0)
check("no guarda ningún crisis_log de más", logs == [], f"logs={logs}")

# ── 5. Ya en banda media, el router escala a EXPLÍCITO → sí corta ────────
resolucion, n_llm, logs = _resolver(_fut("explicita", demora=0.05), crisis_score=0.45)
check("de banda media a explícita SÍ corta (cruza el corte de 0.60)",
      resolucion["respuesta_corte"] is not None)
check("el crisis_score final es al menos el del router",
      resolucion["crisis_score"] >= cr.UMBRAL_CORTE_LLAMADA)

# ── 6. Fail-safe: router que explota, o que nunca se lanzó ───────────────
resolucion, n_llm, logs = _resolver(_fut("explicita", demora=0.05, explota=True), crisis_score=0.0)
check("un router que falla NO revienta el turno", resolucion is not None)
check("un router que falla no corta ni regenera por las dudas",
      resolucion["respuesta_corte"] is None and resolucion["result"] is None)
check("un router que falla no paga ninguna llamada extra al LLM", n_llm == 0)

resolucion, n_llm, logs = _resolver(None, crisis_score=0.0)
check("sin future (defensivo) no revienta ni actúa",
      resolucion["respuesta_corte"] is None and resolucion["result"] is None)

# ── 7. Router ok=False (clasificar_contexto devolvió sin señal) ──────────
resolucion, n_llm, logs = _resolver(_fut("explicita", demora=0.05, ok=False), crisis_score=0.0)
check("router con ok=False se trata como sin señal (score 0.0)",
      resolucion["respuesta_corte"] is None and resolucion["result"] is None)

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
