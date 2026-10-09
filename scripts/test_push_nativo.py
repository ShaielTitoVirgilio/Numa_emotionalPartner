"""
Verifica el push nativo (Expo) sin tocar Supabase ni Expo reales.

Qué se prueba:
  1. POST /push/device-token exige auth, rechaza tokens que no son de Expo y
     guarda el válido atado al usuario autenticado (no a uno del body).
  2. DELETE /push/device-token borra solo del usuario autenticado.
  3. /api/send-daily-push entrega el MISMO mensaje contextual a PWA y a
     dispositivos nativos, marca el anti-spam UNA sola vez por usuario, y
     alcanza a usuarios que solo tienen app nativa.
  4. Sin evento relevante cae al genérico.
  5. Si la tabla de tokens falla, el push web sigue saliendo.
  6. Si Expo falla / un token es DeviceNotRegistered, no revienta y se limpia.
  7. Sin admin key → 401.

Uso: python scripts/test_push_nativo.py
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ADMIN_KEY", "k")
os.environ["VAPID_PRIVATE_KEY"] = "dummy"

from fastapi.testclient import TestClient

import app.main as m
from app import expo_push
from app.core.auth import get_current_user_id
from app.core.config import config

config.ADMIN_KEY = "k"
m.app.dependency_overrides[get_current_user_id] = lambda: "user-A"
cliente = TestClient(m.app)
H = {"x-admin-key": "k"}
TOK1, TOK2 = "ExponentPushToken[aaa]", "ExponentPushToken[bbb]"
fallos = []


def check(nombre, cond):
    print(("OK   " if cond else "FALLA"), nombre)
    if not cond:
        fallos.append(nombre)


# ── 1 y 2: endpoints ────────────────────────────────────────────────
with mock.patch.object(expo_push, "supabase") as sb:
    r = cliente.post("/push/device-token", json={"token": TOK1, "platform": "ios", "user_id": "otro"})
    fila = sb.table.return_value.upsert.call_args[0][0]
    check("registrar: 200", r.status_code == 200)
    check("registrar: usa el user_id del token de auth, no el del body", fila["user_id"] == "user-A")
    check("registrar: guarda token y plataforma", fila["token"] == TOK1 and fila["platform"] == "ios")
    check("registrar: upsert por token", sb.table.return_value.upsert.call_args[1]["on_conflict"] == "token")

    r = cliente.post("/push/device-token", json={"token": "no-es-expo"})
    check("registrar: token inválido → 422", r.status_code == 422)

    r = cliente.request("DELETE", "/push/device-token", json={"token": TOK1})
    q = sb.table.return_value.delete.return_value.eq
    check("borrar: 200", r.status_code == 200)
    check("borrar: filtra por token Y por user_id", q.call_count == 1 and q.return_value.eq.call_args[0] == ("user_id", "user-A"))

m.app.dependency_overrides.clear()
check("sin auth → 401/403", cliente.post("/push/device-token", json={"token": TOK1}).status_code in (401, 403))
m.app.dependency_overrides[get_current_user_id] = lambda: "user-A"


# ── 3 a 7: send-daily-push ──────────────────────────────────────────
class Resp:
    def __init__(self, data): self._d = data
    def raise_for_status(self): pass
    def json(self): return {"data": self._d}


def correr(push_ctx, web, tokens, expo_resp=None, tokens_falla=False):
    """Ejecuta send-daily-push con todo mockeado; devuelve (resp, webpush, expo_post, marcar)."""
    with mock.patch.object(m, "supabase") as sb, \
         mock.patch.object(m, "webpush") as wp, \
         mock.patch.object(m, "construir_push_contextual", return_value=push_ctx), \
         mock.patch.object(m, "marcar_push_enviado") as marcar, \
         mock.patch.object(m, "_cargar_vapid", return_value="v", create=True), \
         mock.patch.object(expo_push.httpx, "post") as post, \
         mock.patch.object(expo_push, "supabase") as sb2:
        sb.table.return_value.select.return_value.execute.return_value.data = web
        if tokens_falla:
            sb2.table.return_value.select.return_value.execute.side_effect = RuntimeError("no existe la tabla")
        else:
            sb2.table.return_value.select.return_value.execute.return_value.data = tokens
        post.side_effect = lambda url, json=None, **kw: Resp(expo_resp(json) if expo_resp else [{"status": "ok"}] * len(json))
        r = cliente.post("/api/send-daily-push", headers=H)
        return r, wp, post, marcar


CTX = {"title": "Numa 🐼", "body": "Hoy tenés la charla. Mucha suerte 🍀", "memory_id": "mem1", "push_type": "reminder"}
WEB = [{"user_id": "u1", "subscription_data": {"endpoint": "x"}}]

r, wp, post, marcar = correr(CTX, WEB, [{"user_id": "u1", "token": TOK1}, {"user_id": "u2", "token": TOK2}])
enviados = [x for call in post.call_args_list for x in call[1]["json"]]
check("send: 200", r.status_code == 200)
check("send: llega a web + a ambos usuarios nativos (u1 y u2)", wp.call_count == 1 and {e["to"] for e in enviados} == {TOK1, TOK2})
check("send: nativo lleva el mensaje contextual", all(e["body"] == CTX["body"] and e["title"] == CTX["title"] for e in enviados))
check("send: canal Android 'default'", all(e["channelId"] == "default" for e in enviados))
check("send: anti-spam marcado 1 vez por usuario (u1 web+nativo cuenta una)", marcar.call_count == 2)
check("send: texto de respuesta cuenta usuarios", "2 notificaciones de 2 usuarios" in r.json()["message"])

r, wp, post, marcar = correr(None, [], [{"user_id": "u2", "token": TOK2}])
check("send: usuario solo-nativo sin evento recibe el genérico", post.call_args[1]["json"][0]["body"].startswith("Hola, ¿querés contarme"))
check("send: genérico no marca anti-spam", marcar.call_count == 0)

r, wp, post, marcar = correr(CTX, WEB, [], tokens_falla=True)
check("send: tabla de tokens rota → el push web igual sale", r.status_code == 200 and wp.call_count == 1)

def expo_muerto(lote):
    return [{"status": "error", "details": {"error": "DeviceNotRegistered"}} for _ in lote]
with mock.patch.object(expo_push, "_borrar_tokens_muertos") as borrar:
    r, wp, post, marcar = correr(CTX, [], [{"user_id": "u2", "token": TOK2}], expo_resp=expo_muerto)
    check("send: DeviceNotRegistered → token borrado", borrar.call_args[0][0] == [TOK2])
check("send: si Expo no aceptó, NO marca anti-spam", marcar.call_count == 0 and r.status_code == 200)

with mock.patch.object(expo_push.httpx, "post", side_effect=RuntimeError("expo caído")):
    with mock.patch.object(m, "supabase") as sb, mock.patch.object(expo_push, "supabase") as sb2, \
         mock.patch.object(m, "construir_push_contextual", return_value=CTX), \
         mock.patch.object(m, "marcar_push_enviado") as marcar, mock.patch.object(m, "_cargar_vapid", return_value="v", create=True):
        sb.table.return_value.select.return_value.execute.return_value.data = []
        sb2.table.return_value.select.return_value.execute.return_value.data = [{"user_id": "u2", "token": TOK2}]
        r = cliente.post("/api/send-daily-push", headers=H)
        check("send: Expo caído → 200 sin reventar y sin marcar", r.status_code == 200 and marcar.call_count == 0)

check("send: sin admin key → 401", cliente.post("/api/send-daily-push").status_code == 401)
check("send: admin key mala → 401", cliente.post("/api/send-daily-push", headers={"x-admin-key": "mala"}).status_code == 401)

print("\n" + ("TODO OK" if not fallos else f"FALLARON {len(fallos)}: {fallos}"))
sys.exit(1 if fallos else 0)
