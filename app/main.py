# app/main.py

import os
import json
from typing import Any
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pywebpush import webpush, WebPushException
from pydantic import BaseModel

from app.routes.auth_router import router as auth_router
from app.routes.chat_router import router as chat_router
from app.routes.onboarding_router import router as onboarding_router
from app.routes.feedback_router import router as feedback_router
from app.supabase_client import supabase

# ==========================
# APP
# ==========================

limiter = Limiter(key_func=get_remote_address)

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
        if path.endswith(".js") or path.endswith(".css"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

app.add_middleware(NoCacheJSMiddleware)


# ==========================
# MODELOS
# ==========================

class SuscripcionPush(BaseModel):
    user_id: str
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
def subscribe(data: SuscripcionPush):
    try:
        supabase.table("user_notifications").upsert({
            "user_id": data.user_id,
            "subscription_data": data.subscription_data
        }, on_conflict="user_id").execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/send-daily-push")
def send_daily_push(x_admin_key: str = Header(None)):
    admin_key_env = os.getenv("ADMIN_KEY", "")
    if not x_admin_key or x_admin_key != admin_key_env:
        raise HTTPException(status_code=401, detail="No autorizado")

    try:
        res = supabase.table("user_notifications").select("*").execute()
        subscriptions = res.data or []

        success_count = 0
        vapid_private = os.getenv("VAPID_PRIVATE_KEY")

        if not vapid_private:
            raise HTTPException(status_code=500, detail="Falta VAPID_PRIVATE_KEY en las variables de entorno")

        for sub in subscriptions:
            try:
                webpush(
                    subscription_info=sub["subscription_data"],
                    data=json.dumps({
                        "title": "Numa 🐼",
                        "body": "Hola, ¿querés contarme cómo te está yendo estos días?"
                    }),
                    vapid_private_key=vapid_private,
                    vapid_claims={"sub": "mailto:shaieltv@gmail.com"}
                )
                success_count += 1
            except WebPushException as ex:
                print(f"Error enviando push al usuario {sub.get('user_id')}: {ex}")

        return {"message": f"Se enviaron {success_count} notificaciones de {len(subscriptions)}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================
# ROUTERS
# ==========================

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(onboarding_router)
app.include_router(feedback_router)