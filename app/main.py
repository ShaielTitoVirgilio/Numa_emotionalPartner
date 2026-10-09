# app/main.py

import hmac
import os
import json
import time
import uuid
from typing import Any
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exception_handlers import http_exception_handler
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from pywebpush import webpush, WebPushException
from pydantic import BaseModel

from app.core.config import config
from app.core.auth import get_current_user_id
from app.core.observability import init_sentry, capturar_error, etiquetar_request
from app.core.logging_utils import log_event
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
from app.routes.diag_router import router as diag_router
from app.routes.tts_router import router as tts_router
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


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Une la pieza que faltaba entre Sentry (solo ve errores) y los `print()`
    sueltos que caían en los logs de Railway sin estructura: una línea JSON
    por request de la API con método, endpoint, status, latencia y
    user_id/email (si el endpoint es autenticado) — para poder buscar "qué le
    pasó a este usuario" o "está tardando este endpoint" sin esperar a que
    reviente una excepción. request.state.user_id/user_email los deja
    seteados get_current_user_id (app/core/auth.py) cuando el endpoint pasa
    por ese dependency.

    El email SOLO va a estos logs (Railway, que mira el dueño de la app para
    saber a quién atender) — nunca a Sentry (marcar_usuario ahí sigue
    mandando nada más que el UUID) y nunca junto con contenido de mensajes.

    También taguea el scope de Sentry con el mismo request_id: si más
    adelante en este request salta un error, el evento en Sentry ya viene
    con ese contexto pegado.

    No loguea body, headers de auth, ni nada del contenido del request —
    mismo criterio de privacidad que observability.py. Los estáticos
    (/, /static, /manifest.json, etc.) se excluyen a propósito: no aportan
    nada al seguimiento y solo generarían ruido.
    """

    _PREFIJOS_API = (
        "/chat", "/auth", "/onboarding", "/feedback", "/checkin",
        "/dashboard", "/account", "/apple", "/memories", "/subscribe",
        "/api/", "/speech-to-text", "/tts",
    )

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(self._PREFIJOS_API):
            return await call_next(request)

        request_id = uuid.uuid4().hex[:12]
        etiquetar_request(request_id=request_id, endpoint=request.url.path)
        inicio = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            log_event(
                "request",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                user_id=getattr(request.state, "user_id", None),
                email=getattr(request.state, "user_email", None),
                status=500,
                latencia_ms=round((time.perf_counter() - inicio) * 1000, 1),
                excepcion_no_manejada=True,
            )
            raise

        response.headers["X-Request-ID"] = request_id
        log_event(
            "request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            user_id=getattr(request.state, "user_id", None),
            email=getattr(request.state, "user_email", None),
            status=response.status_code,
            latencia_ms=round((time.perf_counter() - inicio) * 1000, 1),
        )
        return response


app.add_middleware(RequestLoggingMiddleware)


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


@app.get("/manifest.json")
def serve_manifest():
    """Manifest de la PWA, con el nombre según el entorno.

    Se sirve desde acá y no como archivo estático para que NumaDev (staging)
    se instale en el celular como una app SEPARADA y con otro nombre. Si las
    dos usaran el mismo manifest, en la pantalla de inicio quedarían dos íconos
    idénticos llamados "Numa" y no habría forma de saber cuál es cuál — que es
    justo el error que hace que uno crea que está probando y en realidad esté
    tocando datos de usuarios reales.
    """
    with open(os.path.join("frontend", "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)

    if not config.es_produccion:
        manifest["name"] = "Numa DEV"
        manifest["short_name"] = "Numa DEV"
        manifest["description"] = "Numa — entorno de pruebas"
        # Color distinto: se ve en la barra de estado y en la splash screen.
        manifest["theme_color"] = "#c98b3a"

    return JSONResponse(manifest, headers={"Cache-Control": "no-cache"})


@app.get("/api/entorno")
def entorno():
    """Le dice al frontend en qué entorno corre, para mostrar el cartel de DEV."""
    return {"entorno": config.APP_ENTORNO, "es_produccion": config.es_produccion}

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
# Diagnóstico de latencia del stream (ADMIN_KEY por header). Hace llamadas
# reales al LLM, así que no se expone sin la key — ver diag_router.py.
app.include_router(diag_router)
# Token efimero de Cartesia para la voz del modo llamada (ver tts_router.py).
app.include_router(tts_router)
