"""
Verifica que Numa se entere de que empezó una charla nueva aunque la app
reenvíe la charla vieja, y que ante un "hola" abra trayendo algo de otro día
(2026-10-15).

Lo que estaba roto:
1. es_inicio_sesion era `len(conversation) == 1`. numa-mobile guarda la charla
   en el teléfono y reenvía los últimos 20 mensajes, así que en la app eso
   pasaba una sola vez en la vida del usuario: M23 (saludo con memoria) y M24
   (reenganche) no se activaban nunca, y dias_inactivo no se calculaba.
2. El mood de la ÚLTIMA respuesta (que puede ser de hace días) decidía qué
   memoria traer al volver.
3. Ante un "hola", el criterio de los bloques decía "traelo cuando la charla
   se apague" — la charla arrancaba en frío y la memoria no se usaba.

Correr con: venv/bin/python scripts/test_inicio_sesion.py
(con SUPABASE_URL apuntando a algo inválido: este test no toca ninguna base)
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.memory_service import es_saludo_inicial, evaluar_inicio_sesion  # noqa: E402
from app.numa_prompt import construir_prompt  # noqa: E402

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    if ok:
        print(f"✅ {nombre}")
    else:
        fallos += 1
        print(f"❌ {nombre}{chr(10) + '   ' + detalle if detalle else ''}")


AHORA = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)

# ── 1. evaluar_inicio_sesion ─────────────────────────────────────────────
check("sin respuesta previa → inicio", evaluar_inicio_sesion(None, AHORA) == (True, 0))
check(
    "hace 10 minutos → misma charla",
    evaluar_inicio_sesion(AHORA - timedelta(minutes=10), AHORA) == (False, 0),
)
check(
    "hace 3h59 → misma charla",
    evaluar_inicio_sesion(AHORA - timedelta(hours=3, minutes=59), AHORA)[0] is False,
)
check(
    "hace 4h → charla nueva",
    evaluar_inicio_sesion(AHORA - timedelta(hours=4), AHORA) == (True, 0),
)
check(
    "hace 6 días → charla nueva con 6 días inactivo",
    evaluar_inicio_sesion(AHORA - timedelta(days=6, hours=2), AHORA) == (True, 6),
)

# ── 2. es_saludo_inicial ─────────────────────────────────────────────────
for s in ["hola", "Hola!", "holaaa", "hola numa", "Hola Numa 🐼", "buenas",
          "buen día", "Buenas tardes, ¿cómo andás?", "holis", "hey numa, todo bien?",
          "hola de nuevo"]:
    check(f"saludo: {s!r}", es_saludo_inicial(s))
for s in ["hola, hoy me fue horrible en el laburo", "estoy mal", "", "no sé",
          "hola tengo una pregunta sobre la app", "bien", "gracias"]:
    check(f"NO saludo: {s!r}", not es_saludo_inicial(s))

# ── 3. Prompt ────────────────────────────────────────────────────────────
memorias = [{"content": "Estudia medicina y está en el último año.", "priority": 3,
             "category": "estudios", "id": "m1",
             "created_at": (AHORA - timedelta(days=5)).isoformat()}]
tema = {"id": "t1", "content": "Está peleado con su hermano y no sabe si escribirle.",
        "created_at": (AHORA - timedelta(days=4)).isoformat()}

p = construir_prompt(
    memorias=memorias, num_interacciones=20, es_inicio_sesion=True,
    vuelve_tras_pausa=True, apertura_saludo=True, tema_abierto=tema,
    ultimo_mensaje="hola", dias_inactivo=6,
)
check("M23 entra al volver aunque haya 20 mensajes", "INICIO DE SESIÓN" in p)
check("M23 tiene la instrucción del saludo", "SI EL USUARIO SOLO SALUDÓ" in p)
check("tema abierto ofrecido", "TEMA ABIERTO DEL USUARIO — DISPONIBLE" in p)
check("con criterio de saludo (traerlo ya)", "traelo EN ESTA respuesta" in p)
check("sin el criterio de 'charla apagada'", "cuando la charla se apagó" not in p)
check("contexto: primer mensaje de una charla nueva", "PRIMER mensaje de una charla nueva" in p)
check("no dice 'Mensajes en esta sesión: 20'", "Mensajes en esta sesión: 20" not in p)
check("M24 entra (6 días)", "USUARIO QUE VUELVE" in p)
check(
    "el reenganche usa el MISMO tema ofrecido, no otro",
    "la misma del bloque" in p and "Estudia medicina" not in p.split("DATOS DE REENGANCHE")[1].split("\n\n")[0],
)

p_normal = construir_prompt(
    memorias=memorias, num_interacciones=6, es_inicio_sesion=False,
    tema_abierto=tema, ultimo_mensaje="sí, igual",
)
check("en medio de la charla: criterio de siempre", "cuando la charla se apagó" in p_normal)
check("en medio de la charla: sin M23", "INICIO DE SESIÓN" not in p_normal)
check("en medio de la charla: cuenta mensajes", "Mensajes en esta sesión: 6" in p_normal)

# ── 4. Integración: _preparar_turno de punta a punta ─────────────────────
from unittest.mock import patch  # noqa: E402
from fastapi import BackgroundTasks  # noqa: E402
import app.routes.chat_router as cr  # noqa: E402

_ahora = datetime.now(timezone.utc)
_mem_prio3 = [{
    "content": "Estudia medicina y está en el último año.", "priority": 3,
    "category": "estudios", "id": "m3",
    "created_at": (_ahora - timedelta(days=5)).isoformat(), "last_proactive_at": None,
}]
_tema_db = [{
    "id": "t1", "content": "Está peleado con su hermano y no sabe si escribirle.",
    "priority": 4, "category": "relaciones",
    "created_at": (_ahora - timedelta(days=4)).isoformat(), "last_proactive_at": None,
}]

# La charla vieja que reenvía la app (terminó triste, hace días) + un "hola" nuevo.
_charla_vieja = []
for i in range(9):
    _charla_vieja += [
        {"role": "user", "content": f"mensaje viejo {i}"},
        {"role": "assistant", "content": "te leo"},
    ]


def _turno(ultima_respuesta, mensaje, temas=None, memorias=None, mood="sad", checkin=None):
    body = cr.ChatRequest(
        conversation=_charla_vieja + [{"role": "user", "content": mensaje}],
        ultimo_mood=mood, perfil={},
    )
    parches = [
        patch.object(cr, "get_ultima_respuesta_numa", return_value=ultima_respuesta),
        patch.object(cr, "get_recent_memories", return_value=(memorias or [], [])),
        patch.object(cr, "get_topic_patterns_cached", return_value=[]),
        patch.object(cr, "get_dias_inactivo", return_value=0),
        patch.object(cr, "get_checkin_hoy_cached", return_value=checkin),
        patch.object(cr, "get_proactive_memories", return_value=[]),
        patch.object(cr, "get_open_topics", return_value=temas or []),
        patch.object(cr, "get_resource_memories", return_value=[]),
        patch.object(cr.feedback_repo, "hay_crisis_reciente", return_value=False),
        patch.object(cr, "clasificar_contexto", return_value=dict(cr.resultado_vacio())),
    ]
    for p_ in parches:
        p_.start()
    try:
        return cr._preparar_turno(body, "u1", BackgroundTasks())
    finally:
        for p_ in parches:
            p_.stop()


t = _turno(_ahora - timedelta(days=6), "hola numa", temas=_tema_db, memorias=_mem_prio3)
sp = t["system_prompt"]
check("integración: 'hola' tras 6 días con 19 mensajes viejos → M23", "INICIO DE SESIÓN" in sp)
check("integración: trae el tema abierto (mood viejo 'sad' descartado)", "TEMA ABIERTO DEL USUARIO — DISPONIBLE" in sp)
check("integración: queda marcado para el cierre", t["memoria_ctx_id"] == "t1")
check("integración: M24 con los 6 días", "6 días sin usar la app" in sp)

check("integración: 'hola' al volver → al LLM le llega solo el saludo",
      [m.content for m in t["conversation_llm"]] == ["hola numa"])
check("integración: se guarda con la conversación completa", len(t["conversation"]) == 19)

t = _turno(_ahora - timedelta(days=2), "hola", temas=[], memorias=_mem_prio3)
check(
    "integración: sin tema, el saludo acepta una memoria prioridad 3",
    "ALGO QUE TE CONTÓ OTRO DÍA — DISPONIBLE" in t["system_prompt"] and t["memoria_ctx_id"] == "m3",
)

t = _turno(_ahora - timedelta(days=2), "hola", temas=_tema_db, memorias=_mem_prio3, checkin=1)
check("integración: check-in 'mal' + hola → no se ofrece memoria",
      t["memoria_ctx_id"] is None and "— DISPONIBLE" not in t["system_prompt"])

t = _turno(_ahora - timedelta(minutes=5), "hola", temas=_tema_db, memorias=_mem_prio3, mood="calm")
check("integración: misma charla → el LLM ve todo", len(t["conversation_llm"]) == 19)
check("integración: misma charla (hace 5 min) → sin M23", "INICIO DE SESIÓN" not in t["system_prompt"])
check(
    "integración: misma charla → prioridad 3 NO alcanza para el respaldo",
    "ALGO QUE TE CONTÓ OTRO DÍA — DISPONIBLE" not in t["system_prompt"],
)

t = _turno(_ahora - timedelta(days=3), "hola, hoy me fue horrible en el laburo",
           temas=_tema_db, memorias=_mem_prio3)
check("integración: vuelve contando algo → M23 igual", "INICIO DE SESIÓN" in t["system_prompt"])
check("integración: vuelve contando algo → el LLM ve la charla completa", len(t["conversation_llm"]) == 19)
check(
    "integración: vuelve contando algo → sin estado confiable, no se fuerza tema",
    "TEMA ABIERTO DEL USUARIO — DISPONIBLE" not in t["system_prompt"],
)

# Si la base falla, se cae al criterio viejo sin romper el turno.
with patch.object(cr, "get_ultima_respuesta_numa", side_effect=RuntimeError("base caída")):
    body = cr.ChatRequest(conversation=_charla_vieja + [{"role": "user", "content": "hola"}],
                          ultimo_mood="calm", perfil={})
    parches = [
        patch.object(cr, "get_recent_memories", return_value=([], [])),
        patch.object(cr, "get_topic_patterns_cached", return_value=[]),
        patch.object(cr, "get_dias_inactivo", return_value=0),
        patch.object(cr, "get_checkin_hoy_cached", return_value=None),
        patch.object(cr, "get_proactive_memories", return_value=[]),
        patch.object(cr, "get_open_topics", return_value=[]),
        patch.object(cr, "get_resource_memories", return_value=[]),
        patch.object(cr.feedback_repo, "hay_crisis_reciente", return_value=False),
        patch.object(cr, "clasificar_contexto", return_value=dict(cr.resultado_vacio())),
        patch.object(cr, "capturar_error"),
    ]
    for p_ in parches:
        p_.start()
    try:
        t = cr._preparar_turno(body, "u1", BackgroundTasks())
        check("base caída: el turno sale igual (criterio viejo)", "system_prompt" in t)
    finally:
        for p_ in parches:
            p_.stop()

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
