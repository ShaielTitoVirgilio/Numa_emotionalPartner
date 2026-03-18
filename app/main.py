# app/main.py

import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.routes.auth_router import router as auth_router
from app.routes.chat_router import router as chat_router
from app.routes.onboarding_router import router as onboarding_router
from app.routes.feedback_router import router as feedback_router


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
# STATIC + FRONTEND
# ==========================

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join("frontend", "index.html"))


# ==========================
# ROUTERS
# ==========================

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(onboarding_router)
app.include_router(feedback_router)