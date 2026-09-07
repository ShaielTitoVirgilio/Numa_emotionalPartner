"""
Verifica el control de preguntas de DOS POLOS (2026-09-07).

Contexto: Numa había dejado prácticamente de preguntar. La causa no era el
filtro determinístico (_quitar_pregunta_final solo actúa con 2 preguntas
seguidas, caso raro) sino que el sistema era asimétrico: _bloque_control_preguntas
solo sabía FRENAR y nada le devolvía el permiso nunca. Estos tests cubren el
polo nuevo (habilitación) y, sobre todo, que los dos frenos que ya existían
sigan diciendo exactamente lo mismo que antes.

Correr con: venv/bin/python scripts/test_senales_preguntas.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.conversation_signals import (
    contar_preguntas_seguidas,
    contar_turnos_sin_preguntar,
)
from app.numa_prompt import (
    TURNOS_SIN_PREGUNTAR_PARA_HABILITAR,
    _bloque_control_preguntas,
    construir_prompt,
)

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    if ok:
        print(f"✅ {nombre}")
    else:
        fallos += 1
        print(f"❌ {nombre}{chr(10) + '   ' + detalle if detalle else ''}")


# ── 1. Contadores ────────────────────────────────────────────────────────
check("racha de preguntas: 0 sin mensajes", contar_preguntas_seguidas([]) == 0)
check(
    "racha de preguntas: cuenta solo desde el final",
    contar_preguntas_seguidas(["¿cómo estás?", "eso pesa.", "¿desde cuándo?"]) == 1,
)
check(
    "racha de preguntas: dos seguidas",
    contar_preguntas_seguidas(["eso pesa.", "¿qué pasó?", "¿y cómo seguiste?"]) == 2,
)
check(
    "racha de preguntas: ignora comillas finales",
    contar_preguntas_seguidas(['¿qué pasó?"']) == 1,
)
check("turnos sin preguntar: 0 sin mensajes", contar_turnos_sin_preguntar([]) == 0)
check(
    "turnos sin preguntar: cuenta hasta la última pregunta",
    contar_turnos_sin_preguntar(["¿qué pasó?", "eso pesa.", "te leo.", "tiene lógica."]) == 3,
)
check(
    "turnos sin preguntar: 0 si el último fue pregunta",
    contar_turnos_sin_preguntar(["eso pesa.", "¿qué pasó?"]) == 0,
)
check(
    "los dos contadores son excluyentes",
    all(
        contar_preguntas_seguidas(h) == 0 or contar_turnos_sin_preguntar(h) == 0
        for h in ([], ["a."], ["¿a?"], ["a.", "¿b?"], ["¿a?", "b."])
    ),
)

# ── 2. Bloque: los frenos que ya existían, intactos ──────────────────────
freno_duro = _bloque_control_preguntas(2)
check("freno con racha 2: sigue siendo NO NEGOCIABLE", "NO NEGOCIABLE" in freno_duro)
check(
    "freno con racha 2: prohíbe los dos signos",
    "ni '¿' ni '?'" in freno_duro,
)
freno_suave = _bloque_control_preguntas(1)
check("freno con racha 1: sigue pidiendo evitar", "Evitá que este también termine" in freno_suave)
check(
    "el freno gana sobre la habilitación si hay racha",
    "RITMO DE PREGUNTAS" not in _bloque_control_preguntas(2, 9),
)

# ── 3. Bloque: polo nuevo de habilitación ────────────────────────────────
check(
    f"sin habilitar por debajo de {TURNOS_SIN_PREGUNTAR_PARA_HABILITAR}",
    _bloque_control_preguntas(0, TURNOS_SIN_PREGUNTAR_PARA_HABILITAR - 1) == "",
)
habilita = _bloque_control_preguntas(0, TURNOS_SIN_PREGUNTAR_PARA_HABILITAR)
check("habilita al llegar al umbral", "RITMO DE PREGUNTAS" in habilita)
check("la habilitación NO obliga", "HABILITA, NO OBLIGA" in habilita)
check(
    "la habilitación pide que sea sobre ESTA conversación",
    "ESTA conversación" in habilita,
)
check(
    "la habilitación advierte contra la pregunta de relleno",
    "relleno" in habilita,
)

# ── 4. Composición del prompt ────────────────────────────────────────────
base = dict(ultimo_mensaje="hola", num_interacciones=5)

p_habilitado = construir_prompt(turnos_sin_preguntar=5, **base)
check("prompt: aparece la habilitación", "RITMO DE PREGUNTAS" in p_habilitado)

p_crisis = construir_prompt(turnos_sin_preguntar=5, crisis_score=0.6, **base)
check("prompt: NO habilita en crisis", "RITMO DE PREGUNTAS" not in p_crisis)

p_critico = construir_prompt(turnos_sin_preguntar=5, ultimo_modulo_critico=True, **base)
check("prompt: NO habilita en post-contención", "RITMO DE PREGUNTAS" not in p_critico)

p_post_ej = construir_prompt(
    ultimo_mensaje="[Post-ejercicio | respiración 4-7-8] ✨",
    num_interacciones=5,
    turnos_sin_preguntar=5,
)
check("prompt: NO habilita en feedback post-ejercicio", "RITMO DE PREGUNTAS" not in p_post_ej)

p_primera = construir_prompt(turnos_sin_preguntar=5, es_primera_vez=True, ultimo_mensaje="hola", num_interacciones=1)
check("prompt: NO habilita en la primera vez del usuario", "RITMO DE PREGUNTAS" not in p_primera)

p_llamada = construir_prompt(turnos_sin_preguntar=5, modo_llamada=True, **base)
check("prompt: NO habilita en modo llamada (voz se afina aparte)", "RITMO DE PREGUNTAS" not in p_llamada)

p_freno = construir_prompt(preguntas_seguidas=2, **base)
check("prompt: el freno duro sigue llegando", "NO NEGOCIABLE" in p_freno)

check(
    "M04 ahora nombra el error opuesto (sequía de preguntas)",
    "OTRO EXTREMO" in construir_prompt(**base),
)

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
