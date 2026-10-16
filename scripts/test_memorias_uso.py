"""
Verifica que las memorias no se gasten sin usarse y que la ventana larga no
pierda datos (2026-10-15).

1. Una memoria ofrecida a Numa solo se da por usada (tema cerrado, evento
   seguido, cooldown) si la respuesta la NOMBRA. Antes bastaba con que entrara
   al prompt.
2. Un tema abierto se cierra por palabras CLAVE del mensaje, no por cualquier
   palabra de 4+ letras ("está todo bien" cerraba "Está peleado con su hermano").
3. Una memoria común traída como respaldo descansa 7 días, no 20 horas.
4. La ventana de memorias pasa a 90 días, y el tope de 3 por categoría ya no
   desactiva nada (antes: is_active=false para siempre).

Correr con: venv/bin/python scripts/test_memorias_uso.py
(con SUPABASE_URL apuntando a algo inválido: este test no toca ninguna base)
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.memory_service as ms  # noqa: E402
from app.memory_service import (  # noqa: E402
    elegir_memoria_respaldo,
    respuesta_menciona_memoria,
)

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    if ok:
        print(f"✅ {nombre}")
    else:
        fallos += 1
        print(f"❌ {nombre}{chr(10) + '   ' + detalle if detalle else ''}")


class _Consulta:
    """Imita la cadena de supabase-py lo justo para estos tests: devuelve
    `filas` en execute() y anota los filtros y updates que se le pidieron."""

    def __init__(self, filas, registro):
        self._filas = filas
        self._registro = registro

    def __getattr__(self, nombre):
        def _metodo(*args, **kwargs):
            self._registro.append((nombre, args))
            return self
        return _metodo

    @property
    def not_(self):
        return self

    def execute(self):
        class _R:
            pass
        r = _R()
        r.data = self._filas
        return r


class _SupabaseFalso:
    def __init__(self, filas):
        self.filas = filas
        self.registro = []

    def table(self, _nombre):
        return _Consulta(self.filas, self.registro)

    def updates(self):
        return [a for (n, a) in self.registro if n == "update"]


# ── 1. respuesta_menciona_memoria ────────────────────────────────────────
tema = {"id": "t1", "content": "Está peleado con su hermano y no sabe si escribirle."}
evento = {"id": "e1", "event_title": "entrevista en la agencia", "content": "Tiene una entrevista."}
renuncia = {"id": "t2", "content": "Está evaluando si renunciar a su trabajo actual."}

check("menciona tema (hermano)",
      respuesta_menciona_memoria("¡Hola! ¿Cómo siguió lo de tu hermano?", tema))
check("menciona con otra forma de la palabra (renuncia ↔ renunciar)",
      respuesta_menciona_memoria("Hola, ¿cómo venís con lo de la renuncia?", renuncia))
check("menciona evento por su título",
      respuesta_menciona_memoria("Che, ¿y cómo te fue en la entrevista?", evento))
check("NO menciona: respuesta sobre otra cosa",
      not respuesta_menciona_memoria("Uh, qué día pesado. ¿Querés contarme qué pasó?", tema))
check("NO menciona por palabras genéricas ('está', 'sabe')",
      not respuesta_menciona_memoria("Está bien no saber todo, ¿sabés?", tema))
check("sin memoria → False", not respuesta_menciona_memoria("hola", None))

# ── 2. cerrar_temas_abiertos con palabras clave ──────────────────────────
filas_temas = [{"id": "t1", "content": tema["content"]}]

sb = _SupabaseFalso(filas_temas)
with patch.object(ms, "supabase", sb):
    ms.cerrar_temas_abiertos("u1", "nada, está todo bien, gracias")
check("'está todo bien' NO cierra 'Está peleado con su hermano'", sb.updates() == [])

sb = _SupabaseFalso(filas_temas)
with patch.object(ms, "supabase", sb):
    ms.cerrar_temas_abiertos("u1", "al final hablé con mi hermano y quedamos bien")
check("hablar del hermano SÍ cierra el tema", sb.updates() == [({"status": "closed"},)])

sb = _SupabaseFalso(filas_temas)
with patch.object(ms, "supabase", sb):
    ms.cerrar_temas_abiertos("u1", "todavía no hablé con mi hermano")
check("'todavía no' con el hermano NO cierra", sb.updates() == [])

# ── 3. Cooldown de 7 días para el respaldo ───────────────────────────────
AHORA = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)


def mem(pid, dias_creada, dias_mencionada=None):
    return {
        "id": pid, "content": f"memoria {pid}", "priority": 4,
        "created_at": (AHORA - timedelta(days=dias_creada)).isoformat(),
        "last_proactive_at": (
            (AHORA - timedelta(days=dias_mencionada)).isoformat()
            if dias_mencionada is not None else None
        ),
    }


check("mencionada hace 3 días → todavía descansa",
      elegir_memoria_respaldo([mem("a", 20, 3)], AHORA) is None)
check("mencionada hace 8 días → vuelve a estar disponible",
      (elegir_memoria_respaldo([mem("a", 20, 8)], AHORA) or {}).get("id") == "a")
check("nunca mencionada → disponible",
      (elegir_memoria_respaldo([mem("a", 20)], AHORA) or {}).get("id") == "a")

# ── 4. _disparar_tareas_turno: solo se cierra lo mencionado ──────────────
from fastapi import BackgroundTasks  # noqa: E402
import app.routes.chat_router as cr  # noqa: E402
from datetime import date  # noqa: E402


def _tareas(mensaje_final, memoria_ctx, tema_abierto=None, evento_proactivo=None):
    bt = BackgroundTasks()
    cr._disparar_tareas_turno(
        bt, user_id="u1", conversation=[], mensaje_final=mensaje_final, mood="calm",
        memorias_validadas=[], ids_a_desactivar=[], evento_proactivo=evento_proactivo,
        tema_abierto=tema_abierto, memoria_ctx_id=(memoria_ctx or {}).get("id"),
        ultimo_mensaje="hola", hoy=date(2026, 10, 15), memoria_ctx=memoria_ctx,
    )
    return [(t.func.__name__, t.args) for t in bt.tasks]


t = _tareas("¡Hola! ¿Cómo siguió lo de tu hermano?", tema, tema_abierto=tema)
check("mencionó el tema → se cierra",
      ("marcar_proactivo_insertado", ("t1", "cerrar_tema")) in t)

t = _tareas("Hola, ¿cómo venís hoy?", tema, tema_abierto=tema)
check("NO lo mencionó → el tema queda abierto (sin marcar)",
      not any(n == "marcar_proactivo_insertado" for n, _ in t))

ev = dict(evento, bucket="ayer")
t = _tareas("¿Y cómo te fue en la entrevista?", ev, evento_proactivo=ev)
check("mencionó el evento de ayer → followup",
      ("marcar_proactivo_insertado", ("e1", "followup")) in t)

t = _tareas("Hola, ¿qué tal el día?", ev, evento_proactivo=ev)
check("NO mencionó el evento → no se da por seguido",
      not any(n == "marcar_proactivo_insertado" for n, _ in t))

# ── 5. Ventana de 90 días, sin desactivar ────────────────────────────────
ahora = datetime.now(timezone.utc)


def fila(pid, cat, prio, dias):
    return {"id": pid, "content": f"contenido {pid}", "category": cat, "priority": prio,
            "created_at": (ahora - timedelta(days=dias)).isoformat()}


filas = [
    fila("viejo4", "trabajo", 4, 60),   # prioridad efectiva 3 (más de 30 días)
    fila("nuevo3", "trabajo", 3, 2),    # 3, más reciente → le gana a viejo4
    fila("t1", "trabajo", 4, 5),
    fila("t2", "trabajo", 4, 6),
    fila("t3", "trabajo", 2, 1),        # quinto de trabajo → fuera del prompt, NO desactivado
    fila("r1", "relaciones", 5, 80),
]
sb = _SupabaseFalso(filas)
with patch.object(ms, "supabase", sb):
    vigentes, a_desactivar = ms.get_recent_memories("u1")
ids = [m["id"] for m in vigentes]
check("no desactiva nada", a_desactivar == [], str(a_desactivar))
check("tope 3 por categoría sigue rigiendo el prompt", sum(1 for i in ids if i in {"viejo4", "nuevo3", "t1", "t2", "t3"}) == 3, str(ids))
check("lo reciente de prioridad 3 le gana a lo de hace 60 días con prioridad 4",
      "nuevo3" in ids and "viejo4" not in ids, str(ids))
check("memoria de hace 80 días entra (ventana 90)", "r1" in ids, str(ids))
gte = [a for (n, a) in sb.registro if n == "gte"]
dias_ventana = (ahora - datetime.fromisoformat(gte[0][1])).days if gte else None
check("la consulta pide 90 días", dias_ventana in (89, 90), str(gte))

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
