# app/core/auth.py
"""
Autenticación de usuarios para la API.

Toda la API confiaba ciegamente en el user_id que mandaba el cliente
(broken access control / IDOR). Este módulo agrega un dependency de FastAPI
que valida el access_token de Supabase y deriva el user_id DEL TOKEN.

Uso:
    from app.core.auth import get_current_user_id

    @router.post("/chat")
    def chat(body: ChatRequest, user_id: str = Depends(get_current_user_id)):
        ...

El token validado se cachea en memoria unos minutos para no golpear el
servidor de auth de Supabase en cada mensaje del chat.
"""

import hashlib
import time
from typing import Dict, Tuple, Optional

from fastapi import Header, HTTPException

from app.core.db import supabase

# token_hash → (expires_at_epoch, user_id)
_TOKEN_CACHE: Dict[str, Tuple[float, str]] = {}
_TOKEN_TTL_SECONDS = 300  # 5 minutos
_MAX_CACHE_ENTRIES = 2000


def _prune_cache(now: float) -> None:
    if len(_TOKEN_CACHE) <= _MAX_CACHE_ENTRIES:
        return
    expirados = [k for k, (exp, _) in _TOKEN_CACHE.items() if exp <= now]
    for k in expirados:
        _TOKEN_CACHE.pop(k, None)
    # Si sigue lleno (todos vigentes), resetear: peor caso es re-validar
    if len(_TOKEN_CACHE) > _MAX_CACHE_ENTRIES:
        _TOKEN_CACHE.clear()


def get_current_user_id(authorization: Optional[str] = Header(None)) -> str:
    """Valida el Bearer token de Supabase y devuelve el user_id del token.

    Lanza 401 si falta el header o el token es inválido/expirado.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="No autorizado")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="No autorizado")

    now = time.time()
    key = hashlib.sha256(token.encode()).hexdigest()
    cached = _TOKEN_CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]

    try:
        res = supabase.auth.get_user(token)
        user = getattr(res, "user", None)
    except Exception:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

    if not user or not getattr(user, "id", None):
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

    _prune_cache(now)
    _TOKEN_CACHE[key] = (now + _TOKEN_TTL_SECONDS, user.id)
    return user.id
