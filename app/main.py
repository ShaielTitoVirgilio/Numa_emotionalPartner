# app/main.py

import hmac
import os
import json
from typing import Any
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.exception_handlers import http_exception_handler
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from pywebpush import webpush, WebPushException
from pydantic import BaseModel

from app.core.config import config
from app.core.auth import get_current_user_id
from app.core.observability import init_sentry, capturar_error
from app.core.ratelimit import client_ip
from app.memory_service import construir_push_contextual, marcar_push_enviado
from app.routes.auth_router import router as auth_router
from app.routes.chat_router import router as chat_router
from app.routes.onboarding_router import router as onboarding_router
from app.routes.feedback_router import router as feedback_router
from app.routes.checkin_router import router as checkin_router
from app.routes.dashboard_router import router as dashboard_router
from app.routes.account_router import router as account_router
from app.routes.apple_router import router as apple_router
from app.routes.memories_router import router as memories_router
from app.supabase_client import supabase
from app.core.errors import NumaError, MENSAJE_GENERICO

# ==========================
# VALIDACIÓN DE ENTORNO (fail-fast)
# ==========================

if not config.ADMIN_KEY:
    raise RuntimeError(
        "ADMIN_KEY no está configurada. Definila en el .env antes de arrancar: "
        "sin ella los endpoints de administración quedarían abiertos."
    )

# ==========================
# OBSERVABILIDAD
# ==========================

# Antes de crear la app, para que las integraciones enganchen todo.
# Sin SENTRY_DSN es no-op y la app arranca igual.
_sentry_activo = init_sentry()
print(f"🔭 Sentry: {'activo' if _sentry_activo else 'desactivado (sin SENTRY_DSN)'}")

# ==========================
# APP
# ==========================

limiter = Limiter(key_func=client_ip)

app = FastAPI(title="Numa Emotional Partner API", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ==========================
# MIDDLEWARE
# ==========================

class NoCacheJSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith(".js") or path.endswith(".css") or path.endswith(".html") or path == "/":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

app.add_middleware(NoCacheJSMiddleware)


# Red de seguridad: la app tiene decenas de `except Exception` que convierten el
# error en HTTPException(500). Sentry no captura esas por ser "manejadas", así
# que las reportamos acá — pase lo que pase, un 5xx queda registrado.
# (Los 4xx son errores del cliente, no fallas nuestras: no se reportan.)
@app.exception_handler(HTTPException)
async def _reportar_5xx(request: Request, exc: HTTPException):
    if exc.status_code >= 500:
        capturar_error(exc, contexto="http_5xx", ruta=request.url.path)
    return await http_exception_handler(request, exc)


# ==========================
# MODELOS
# ==========================

class SuscripcionPush(BaseModel):
    subscription_data: Any


# ==========================
# STATIC + FRONTEND
# ==========================

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join("frontend", "index.html"))

@app.get("/sw.js")
def serve_sw():
    return FileResponse(
        os.path.join("frontend", "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"}
    )


# ==========================
# PUSH NOTIFICATIONS
# ==========================

@app.post("/subscribe")
def subscribe(data: SuscripcionPush, user_id: str = Depends(get_current_user_id)):
    try:
        supabase.table("user_notifications").upsert({
            "user_id": user_id,
            "subscription_data": data.subscription_data
        }, on_conflict="user_id").execute()
        return {"ok": True}
    except Exception as e:
        capturar_error(e, contexto="subscribe")
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)

@app.post("/api/send-daily-push")
def send_daily_push(x_admin_key: str = Header(None)):
    admin_key_env = config.ADMIN_KEY
    if not x_admin_key or not hmac.compare_digest(x_admin_key, admin_key_env):
        raise HTTPException(status_code=401, detail="No autorizado")

    try:
        res = supabase.table("user_notifications").select("*").execute()
        subscriptions = res.data or []

        success_count = 0
        contextual_count = 0
        vapid_private = os.getenv("VAPID_PRIVATE_KEY")

        if not vapid_private:
            raise HTTPException(status_code=500, detail="Falta VAPID_PRIVATE_KEY en las variables de entorno")

        GENERICO = {
            "title": "Numa 🐼",
            "body": "Hola, ¿querés contarme cómo te está yendo estos días?",
        }

        for sub in subscriptions:
            user_id = sub.get("user_id")

            # Push contextual: si el usuario tiene un evento relevante (hoy/mañana/ayer),
            # el mensaje habla de ESE evento; si no, cae al genérico. (req. 7)
            push = None
            if user_id:
                try:
                    push = construir_push_contextual(user_id)
                except Exception as ex:
                    capturar_error(ex, contexto="construir_push_contextual")
                    print(f"⚠️ construir_push_contextual falló para {user_id}: {ex}")

            payload = {"title": push["title"], "body": push["body"]} if push else GENERICO

            try:
                webpush(
                    subscription_info=sub["subscription_data"],
                    data=json.dumps(payload),
                    vapid_private_key=vapid_private,
                    vapid_claims={"sub": "mailto:shaieltv@gmail.com"}
                )
                success_count += 1
                # Marcar el push como enviado SOLO tras el envío exitoso (anti-spam, req. 8)
                if push:
                    contextual_count += 1
                    marcar_push_enviado(push["memory_id"], push["push_type"])
            except WebPushException as ex:
                capturar_error(ex, contexto="webpush_envio")
                print(f"Error enviando push a una suscripción: {ex}")

        return {
            "message": (
                f"Se enviaron {success_count} notificaciones de {len(subscriptions)} "
                f"({contextual_count} contextuales)."
            )
        }
    except HTTPException:
        raise
    except Exception as e:
        capturar_error(e, contexto="send_daily_push")
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)


# ==========================
# ROUTERS
# ==========================

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(onboarding_router)
app.include_router(feedback_router)
app.include_router(checkin_router)
app.include_router(dashboard_router)
app.include_router(account_router)
app.include_router(apple_router)
app.include_router(memories_router)
