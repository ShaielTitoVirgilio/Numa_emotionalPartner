"""
Tests de la lógica PURA del sistema de memorias contextuales — sin DB ni LLM.

Cubre:
  1. _decidir_followups     → guard "aún no" + refechado vs cierre de eventos
  2. elegir_memoria_contextual → política por estado emocional (router Qwen)
  3. _mismo_evento           → matching laxo de títulos para el upsert
  4. _en_cooldown_proactivo  → ventana anti-repetición
  5. seleccionar_modulos     → gates de M32/M33 (crisis los bloquea)
  6. construir_prompt        → los bloques dinámicos entran cuando corresponde

Uso:
    source venv/bin/activate
    python test_memoria_contextual.py
"""

from datetime import date, datetime, timedelta, timezone

from app.memory_service import (
    _decidir_followups,
    _en_cooldown_proactivo,
    _mismo_evento,
    elegir_memoria_contextual,
    resolver_fecha_relativa,
)
from app.numa_prompt import construir_prompt, seleccionar_modulos

PASADAS = 0
FALLIDAS = 0


def check(nombre: str, cond: bool, extra: str = ""):
    global PASADAS, FALLIDAS
    if cond:
        PASADAS += 1
        print(f"  ✅ {nombre}")
    else:
        FALLIDAS += 1
        print(f"  ❌ {nombre} {extra}")


HOY = date(2026, 7, 8)  # miércoles

# ══════════════════════════════════════════════════════════════
print("\n1) _decidir_followups — cierre vs refechado")
# ══════════════════════════════════════════════════════════════

ev_pasado = {"id": "ev1", "event_title": "examen de matemática",
             "content": "Tiene examen de matemática.", "event_date": "2026-07-07"}
ev_futuro = {"id": "ev2", "event_title": "entrevista de trabajo",
             "content": "Tiene entrevista de trabajo.", "event_date": "2026-07-15"}

# Evento ya ocurrido + usuario habla de él → se cierra
ids, refs = _decidir_followups([ev_pasado], "me fue bien en el examen!", HOY)
check("evento pasado respondido → followed_up", ids == ["ev1"] and not refs)

# EL CASO DEL BUG: "aún no lo tuve, es el martes que viene" → NO cerrar, refechar
ids, refs = _decidir_followups(
    [ev_pasado], "aún no lo tuve, el examen lo tengo el martes que viene", HOY)
check("aún-no → NO se cierra", ids == [])
check("aún-no + fecha nueva → se refecha", len(refs) == 1 and refs[0]["id"] == "ev1")
if refs:
    nueva = date.fromisoformat(refs[0]["event_date"])
    esperada = resolver_fecha_relativa("el examen lo tengo el martes que viene", HOY)
    check("la fecha nueva es la que resuelve el mensaje", nueva == esperada,
          f"(nueva={nueva}, esperada={esperada})")
    check("la fecha nueva es futura y es martes", nueva > HOY and nueva.weekday() == 1,
          f"(nueva={nueva})")

# "todavía no" sin fecha nueva → no cerrar, no refechar (queda abierto como está)
ids, refs = _decidir_followups([ev_pasado], "todavía no rendí el examen", HOY)
check("aún-no sin fecha → queda intacto", ids == [] and refs == [])

# Evento FUTURO mencionado al pasar → no se toca (antes ni entraba en la query)
ids, refs = _decidir_followups([ev_futuro], "qué nervios la entrevista", HOY)
check("evento futuro mencionado → intacto", ids == [] and refs == [])

# Evento futuro pospuesto → se refecha
ids, refs = _decidir_followups(
    [ev_futuro], "me pasaron la entrevista para la semana que viene", HOY)
check("evento futuro pospuesto → se refecha",
      len(refs) == 1 and refs[0]["event_date"] == (HOY + timedelta(days=7)).isoformat())

# Mensaje sin relación → nada
ids, refs = _decidir_followups([ev_pasado, ev_futuro], "hoy comí ravioles", HOY)
check("mensaje sin relación → nada", ids == [] and refs == [])

# ══════════════════════════════════════════════════════════════
print("\n2) elegir_memoria_contextual — política por estado")
# ══════════════════════════════════════════════════════════════

EV_HOY_IMP3   = {"id": "e1", "bucket": "hoy",     "importance": 3, "event_title": "partido"}
EV_PROX_IMP4  = {"id": "e2", "bucket": "proximo", "importance": 4, "event_title": "cirugía"}
EV_PROX_IMP2  = {"id": "e3", "bucket": "proximo", "importance": 2, "event_title": "partido"}
TEMA          = [{"id": "t1", "content": "Está peleado con su mejor amigo."}]
RECURSO       = [{"id": "r1", "content": "Salir a correr le despeja la mente."}]

def elegir(estado, evento=None, temas=None, recursos=None, ok=True, riesgo=0.0):
    return elegir_memoria_contextual(
        estado_emocional=estado, router_ok=ok, riesgo_score=riesgo,
        evento=evento, temas_abiertos=temas or [], recursos=recursos or [])

r = elegir("neutral", evento=EV_HOY_IMP3, temas=TEMA, recursos=RECURSO, riesgo=0.5)
check("riesgo ≥ 0.35 → nada", r is None)

r = elegir(None, evento=EV_HOY_IMP3, temas=TEMA, recursos=RECURSO, ok=False)
check("router caído → comportamiento histórico (solo evento)",
      r and r["tipo"] == "evento")

r = elegir(None, temas=TEMA, recursos=RECURSO, ok=False)
check("router caído sin evento → nada", r is None)

r = elegir("triste_vacio", evento=EV_HOY_IMP3, temas=TEMA, recursos=RECURSO)
check("triste + recurso disponible → recurso", r and r["tipo"] == "recurso")

r = elegir("triste_vacio", evento=EV_PROX_IMP4)
check("triste sin recurso + evento importante → evento", r and r["tipo"] == "evento")

r = elegir("triste_vacio", evento=EV_HOY_IMP3, temas=TEMA)
check("triste sin recurso + evento liviano → nada (no preguntar por el partido)",
      r is None)

r = elegir("duelo", evento=EV_PROX_IMP4)
check("duelo + evento importante (cirugía) → evento", r and r["tipo"] == "evento")

r = elegir("duelo", evento=EV_HOY_IMP3, temas=TEMA, recursos=RECURSO)
check("duelo + evento liviano → nada (ni recurso: duelo no se 'soluciona')",
      r is None)

r = elegir("ansioso", recursos=RECURSO)
check("ansioso + recurso → recurso", r and r["tipo"] == "recurso")

r = elegir("ansioso", evento=EV_HOY_IMP3)
check("ansioso sin recurso + evento de hoy → evento", r and r["tipo"] == "evento")

r = elegir("ansioso", evento=EV_PROX_IMP2)
check("ansioso sin recurso + evento lejano → nada", r is None)

r = elegir("enojado", evento=EV_HOY_IMP3)
check("enojado + evento de hoy → evento", r and r["tipo"] == "evento")

r = elegir("enojado", evento=EV_PROX_IMP2, temas=TEMA, recursos=RECURSO)
check("enojado + evento lejano → nada", r is None)

r = elegir("neutral", evento=EV_HOY_IMP3, temas=TEMA)
check("neutral + evento → evento primero", r and r["tipo"] == "evento")

r = elegir("neutral", temas=TEMA)
check("neutral sin evento + tema abierto → tema_abierto",
      r and r["tipo"] == "tema_abierto")

r = elegir("buenas_noticias", temas=TEMA)
check("buenas noticias + tema abierto → tema_abierto",
      r and r["tipo"] == "tema_abierto")

r = elegir("neutral")
check("nada disponible → nada", r is None)

# ══════════════════════════════════════════════════════════════
print("\n3) _mismo_evento — matching de títulos")
# ══════════════════════════════════════════════════════════════

check("'examen' ↔ 'examen de matemática'", _mismo_evento("examen", "examen de matemática"))
check("'entrevista de trabajo' ↔ 'entrevista'", _mismo_evento("entrevista de trabajo", "entrevista"))
check("'cumpleaños de la madre' ≠ 'entrevista'", not _mismo_evento("cumpleaños de la madre", "entrevista"))
check("vacío ≠ algo", not _mismo_evento("", "examen"))

# ══════════════════════════════════════════════════════════════
print("\n4) _en_cooldown_proactivo")
# ══════════════════════════════════════════════════════════════

ahora = datetime.now(timezone.utc)
check("insertado hace 1h → en cooldown",
      _en_cooldown_proactivo((ahora - timedelta(hours=1)).isoformat()))
check("insertado hace 30h → libre",
      not _en_cooldown_proactivo((ahora - timedelta(hours=30)).isoformat()))
check("nunca insertado (None) → libre", not _en_cooldown_proactivo(None))
check("timestamp corrupto → libre (fail-safe)", not _en_cooldown_proactivo("no-es-fecha"))

# ══════════════════════════════════════════════════════════════
print("\n5) seleccionar_modulos — gates de M32/M33")
# ══════════════════════════════════════════════════════════════

BASE = dict(
    ultimo_mensaje="todo tranquilo por acá",
    historial_reciente=[], num_interacciones=5, mood_actual=None,
    checkin_hoy=None, es_primera_vez=False, es_inicio_sesion=False,
    tiene_memorias=True, dias_inactivo=0, ultimo_modulo_critico=False,
)

mods = seleccionar_modulos(**BASE, crisis_score=0.0, hay_tema_abierto=True)
check("tema abierto fuera de crisis → M32", "M32_tema_abierto" in mods)

mods = seleccionar_modulos(**BASE, crisis_score=0.5, hay_tema_abierto=True)
check("tema abierto EN crisis → sin M32", "M32_tema_abierto" not in mods)

mods = seleccionar_modulos(**BASE, crisis_score=0.0, hay_recurso=True)
check("recurso fuera de crisis → M33", "M33_memoria_recurso" in mods)

mods = seleccionar_modulos(**BASE, crisis_score=0.7, hay_recurso=True)
check("recurso EN crisis → sin M33", "M33_memoria_recurso" not in mods)

mods = seleccionar_modulos(**BASE, crisis_score=0.0)
check("sin señales → sin M32/M33",
      "M32_tema_abierto" not in mods and "M33_memoria_recurso" not in mods)

# ══════════════════════════════════════════════════════════════
print("\n6) construir_prompt — bloques dinámicos")
# ══════════════════════════════════════════════════════════════

COMUNES = dict(
    perfil=None, memorias=[{"content": "Estudia medicina.", "priority": 3, "category": "estudios"}],
    num_interacciones=5, ultimo_mensaje="todo tranquilo",
    router_hints={"ok": True, "estado_emocional": "neutral", "senal_riesgo": "none",
                  "pide_ejercicio": False, "pregunta_app": False, "pregunta_capacidades": False},
)

p = construir_prompt(**COMUNES, tema_abierto={"id": "t1", "content": "Está peleado con su mejor amigo."})
check("prompt con tema abierto → bloque presente", "TEMA ABIERTO DEL USUARIO" in p)
check("prompt con tema abierto → módulo M32 presente", "ALGO QUE EL USUARIO DEJÓ SIN RESOLVER" in p)

p = construir_prompt(**COMUNES, memoria_recurso={"id": "r1", "content": "Salir a correr le despeja la mente."})
check("prompt con recurso → bloque presente", "RECURSO DEL USUARIO" in p)
check("prompt con recurso → módulo M33 presente", "ALGO QUE YA LE FUNCIONÓ" in p)

p = construir_prompt(**COMUNES)
check("prompt sin señales → sin bloques nuevos",
      "TEMA ABIERTO DEL USUARIO" not in p and "RECURSO DEL USUARIO" not in p)

p = construir_prompt(**COMUNES, crisis_score=0.7,
                     tema_abierto={"id": "t1", "content": "Está peleado con su mejor amigo."},
                     memoria_recurso={"id": "r1", "content": "Correr le despeja."})
check("prompt en crisis → los bloques nuevos NO entran",
      "TEMA ABIERTO DEL USUARIO" not in p and "RECURSO DEL USUARIO" not in p)

# Formato de extracción: M08/M09 anuncian los campos nuevos
p = construir_prompt(**COMUNES)
check("M08 explica temas abiertos", "TEMAS ABIERTOS" in p)
check("M09 incluye los campos open/helped", '"open": false' in p and '"helped": false' in p)

# ══════════════════════════════════════════════════════════════
print(f"\n{'='*50}\nResultado: {PASADAS} pasadas · {FALLIDAS} fallidas")
if FALLIDAS:
    raise SystemExit(1)
print("Todo OK ✅")
