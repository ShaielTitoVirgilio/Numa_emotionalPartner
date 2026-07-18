"""Tests de la mejora de memoria proactiva (sesión 2026-07-13).

Parte 1 (unitaria, sin red): protección contra la poda + detectores de flags.
Parte 2 (en vivo, ~4 llamadas a Luna ≈ $0.05): comportamiento del prompt —
  A) con TEMA ABIERTO presente, Numa lo retoma;
  B) con solo memorias generales (sin bloque proactivo), NO saca temas viejos;
  C) con RECURSO presente y usuario mal, Numa se lo recuerda con suavidad.

Uso:  venv/bin/python test_memoria_proactiva_v2.py [--solo-unit]
"""
import sys
from datetime import date

from app.memory_service import (
    _protegida_de_desactivacion,
    detectar_tema_abierto,
    detectar_recurso,
)

FALLAS = []


def check(nombre, cond):
    print(("  ✅ " if cond else "  ❌ ") + nombre)
    if not cond:
        FALLAS.append(nombre)


# ══════════════ PARTE 1: UNITARIOS ══════════════
print("── _protegida_de_desactivacion ──")
hoy = date(2026, 7, 13)
check("evento futuro protegido",
      _protegida_de_desactivacion({"event_date": "2026-07-20", "followed_up": False}, hoy))
check("evento reciente sin followup protegido",
      _protegida_de_desactivacion({"event_date": "2026-07-11", "followed_up": False}, hoy))
check("evento ya seguido NO protegido",
      not _protegida_de_desactivacion({"event_date": "2026-07-11", "followed_up": True}, hoy))
check("evento viejo NO protegido",
      not _protegida_de_desactivacion({"event_date": "2026-06-01", "followed_up": False}, hoy))
check("tema abierto reciente protegido",
      _protegida_de_desactivacion({"status": "open", "created_at": "2026-07-01T00:00:00Z"}, hoy))
check("tema abierto viejo (>45d) NO protegido",
      not _protegida_de_desactivacion({"status": "open", "created_at": "2026-01-01T00:00:00Z"}, hoy))
check("tema cerrado NO protegido",
      not _protegida_de_desactivacion({"status": "closed", "created_at": "2026-07-01T00:00:00Z"}, hoy))
check("recurso reciente protegido",
      _protegida_de_desactivacion({"helped_before": True, "created_at": "2026-06-01T00:00:00Z"}, hoy))
check("recurso viejo (>90d) NO protegido",
      not _protegida_de_desactivacion({"helped_before": True, "created_at": "2025-12-01T00:00:00Z"}, hoy))
check("memoria común NO protegida",
      not _protegida_de_desactivacion({"content": "le gusta el mate"}, hoy))

print("── detectar_tema_abierto ──")
for txt, esperado in [
    ("Está peleado con su mejor amigo y no sabe si escribirle.", True),
    ("Está evaluando si renunciar a su trabajo actual.", True),
    ("Está esperando el resultado de un análisis médico.", True),
    ("Todavía no decidió si mudarse a Rosario.", True),
    ("Le gusta el cine coreano.", False),
    ("Se siente ansioso antes de rendir.", False),
    ("Jugó un partido de fútbol con amigos.", False),
]:
    check(f"{txt[:48]!r} -> {esperado}", detectar_tema_abierto(txt) == esperado)

print("── detectar_recurso ──")
for txt, esperado in [
    ("Salir a correr le despeja la mente cuando está estresado.", True),
    ("Hablar con su hermana la tranquiliza cuando algo la angustia.", True),
    ("Dormir temprano le cambió el día.", True),
    ("Ya no le sirve meditar, dice que se aburre.", False),
    ("Dejó de ayudarlo salir a caminar.", False),
    ("Fue a correr el sábado.", False),
]:
    check(f"{txt[:48]!r} -> {esperado}", detectar_recurso(txt) == esperado)

if "--solo-unit" in sys.argv:
    print("\n" + ("TODOS OK ✅" if not FALLAS else f"FALLAS: {FALLAS}"))
    sys.exit(0 if not FALLAS else 1)

# ══════════════ PARTE 2: EN VIVO (Luna) ══════════════
from app.llm_client import LLMClient
from app.numa_prompt import construir_prompt

llm = LLMClient()
MEMS = [
    {"content": "Su mamá vive en Rosario y hablan poco", "category": "relaciones", "priority": 3},
    {"content": "Trabaja medio turno en una farmacia", "category": "trabajo", "priority": 3},
    {"content": "Le gusta leer novelas de misterio", "category": "hobbies", "priority": 2},
]
RH_NEUTRAL = {"ok": True, "estado_emocional": "neutral", "senal_riesgo": "none",
              "pide_ejercicio": False, "pregunta_app": False, "pregunta_capacidades": False}
RH_TRISTE = dict(RH_NEUTRAL, estado_emocional="triste_vacio")


def turno(conv, **kw):
    sp = construir_prompt(
        memorias=MEMS, num_interacciones=len(conv), historial_reciente=conv,
        ultimo_mensaje=conv[-1]["content"], hoy=date.today(), **kw)
    return llm.generate_response(conv, sp)["message"]


print("\n── VIVO A: tema abierto presente → lo retoma ──")
conv = [
    {"role": "user", "content": "hola! todo tranqui por acá"},
    {"role": "assistant", "content": "Hola. Qué bueno leerte tranquilo."},
    {"role": "user", "content": "sí, un finde relajado la verdad"},
]
msg = turno(conv, router_hints=RH_NEUTRAL,
            tema_abierto={"content": "Está peleado con su hermano y no sabe si escribirle"})
print(f"  🐻 {msg}")
check("menciona el tema del hermano", "herman" in msg.lower())

print("\n── VIVO B: SIN bloque proactivo → no saca temas viejos ──")
conv_b = [
    {"role": "user", "content": "hola, cómo va"},
    {"role": "assistant", "content": "Hola. Bien por acá. ¿Vos?"},
    {"role": "user", "content": "bien, terminando unas cosas del trabajo"},
]
msg_b = turno(conv_b, router_hints=RH_NEUTRAL)
print(f"  🐻 {msg_b}")
check("NO trae a la mamá/Rosario de la nada",
      "rosario" not in msg_b.lower() and "mamá" not in msg_b.lower())
check("NO trae las novelas de la nada", "novela" not in msg_b.lower())

print("\n── VIVO C: recurso presente + usuario mal → se lo recuerda ──")
conv_c = [
    {"role": "user", "content": "uf, vengo con la cabeza a mil"},
    {"role": "assistant", "content": "¿Qué te tiene así, más o menos?"},
    {"role": "user", "content": "el laburo que no para, y no me puedo concentrar en nada"},
]
msg_c = turno(conv_c, router_hints=RH_TRISTE, mood_actual="stressed",
              memoria_recurso={"content": "Salir a correr le despeja la mente cuando está estresado"})
print(f"  🐻 {msg_c}")
check("menciona correr como recurso propio", "corr" in msg_c.lower())

print("\n" + ("TODOS OK ✅" if not FALLAS else f"FALLAS ({len(FALLAS)}): {FALLAS}"))
sys.exit(0 if not FALLAS else 1)
