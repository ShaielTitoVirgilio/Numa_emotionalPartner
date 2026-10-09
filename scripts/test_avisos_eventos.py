"""
Verifica GET /memories/avisos (avisos de eventos para las notificaciones
LOCALES de numa-mobile), sin tocar Supabase real.

  1. Cada evento da un aviso "hoy" (fecha del evento) y uno "seguimiento"
     (día siguiente), con los textos del push contextual.
  2. Un evento ya seguido (followed_up) NO genera seguimiento.
  3. Eventos sin título/fecha válida se ignoran.
  4. La consulta filtra por el usuario autenticado, solo memorias activas con
     fecha, en una ventana [hoy-2, hoy+30], con tope de eventos.
  5. Requiere auth; si la base falla responde 500 genérico (sin detalles).

Uso: python scripts/test_avisos_eventos.py
"""
import os
import sys
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ADMIN_KEY", "k")

from fastapi.testclient import TestClient

import app.main as m
from app import memory_service
from app.core.auth import get_current_user_id

fallos = []


def check(nombre, cond):
    print(("OK   " if cond else "FALLA"), nombre)
    if not cond:
        fallos.append(nombre)


class Q:
    """Query fake: cualquier método encadena; registra llamadas; execute devuelve filas."""
    def __init__(self, filas=None, error=None):
        self.filas, self.error, self.llamadas = filas or [], error, []

    def __getattr__(self, nombre):
        if nombre == "not_":
            self.llamadas.append(("not_",))
            return self
        def f(*a, **k):
            self.llamadas.append((nombre, a))
            if nombre == "execute":
                if self.error:
                    raise self.error
                return mock.Mock(data=self.filas)
            return self
        return f


hoy = date.today()
d = lambda n: (hoy + timedelta(days=n)).isoformat()
FILAS = [
    {"id": "e1", "content": "Tiene una charla con el decano.", "event_title": "la charla con el decano", "event_date": d(2), "followed_up": False},
    {"id": "e2", "content": "x", "event_title": "el examen de química", "event_date": d(0), "followed_up": True},
    {"id": "e3", "content": "", "event_title": "", "event_date": d(1), "followed_up": False},
    {"id": "e4", "content": "x", "event_title": "algo", "event_date": "basura", "followed_up": False},
    {"id": "e5", "content": "Tiene una cita médica.", "event_title": None, "event_date": d(3), "followed_up": False},
]

m.app.dependency_overrides[get_current_user_id] = lambda: "user-A"
cliente = TestClient(m.app)

q = Q(FILAS)
with mock.patch.object(memory_service, "supabase") as sb:
    sb.table.return_value = q
    r = cliente.get("/memories/avisos")
av = r.json().get("avisos", [])
por = {(a["id"], a["tipo"]): a for a in av}

check("200", r.status_code == 200)
check("hoy: fecha del evento y texto contextual",
      por[("e1", "hoy")]["fecha"] == d(2) and por[("e1", "hoy")]["cuerpo"] == "Hoy tenés la charla con el decano. Mucha suerte 🍀")
check("seguimiento: día siguiente y texto contextual",
      por[("e1", "seguimiento")]["fecha"] == d(3) and por[("e1", "seguimiento")]["cuerpo"] == "¿Cómo te fue con la charla con el decano?")
check("evento ya seguido: hay 'hoy' pero NO seguimiento", ("e2", "hoy") in por and ("e2", "seguimiento") not in por)
check("sin título → ignorado", not any(a["id"] == "e3" for a in av))
check("fecha inválida → ignorado", not any(a["id"] == "e4" for a in av))
check("sin event_title usa el content, sin punto final", por[("e5", "hoy")]["cuerpo"] == "Hoy tenés Tiene una cita médica. Mucha suerte 🍀")
check("título de la notificación", all(a["titulo"] == "Numa 🐼" for a in av))

check("filtra por el usuario autenticado", ("eq", ("user_id", "user-A")) in q.llamadas)
check("solo memorias activas", ("eq", ("is_active", True)) in q.llamadas)
check("solo con fecha", ("not_",) in q.llamadas)
check("ventana [hoy-2, hoy+30]", ("gte", ("event_date", d(-2))) in q.llamadas and ("lte", ("event_date", d(30))) in q.llamadas)
check("tope de eventos", ("limit", (20,)) in q.llamadas)

with mock.patch.object(memory_service, "supabase") as sb:
    sb.table.return_value = Q(error=RuntimeError("detalle interno secreto"))
    r = cliente.get("/memories/avisos")
check("base caída → 500", r.status_code == 500)
check("500 sin filtrar detalles internos", "secreto" not in r.text)

m.app.dependency_overrides.clear()
check("sin auth → 401/403", cliente.get("/memories/avisos").status_code in (401, 403))

print("\n" + ("TODO OK" if not fallos else f"FALLARON {len(fallos)}: {fallos}"))
sys.exit(1 if fallos else 0)
