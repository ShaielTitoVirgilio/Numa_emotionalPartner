# app/routes/password_reset_router.py
"""
Flujo de recuperación de contraseña:

  1. POST /forgot-password          → manda OTP al email vía Supabase
  2. POST /forgot-password/verify   → valida el OTP, devuelve reset_token (5 min)
  3. POST /forgot-password/reset    → valida reset_token, actualiza contraseña

Seguridad:
  - El código OTP expira a los 5 min desde que fue pedido (controlado en backend)
  - Max 5 intentos de código por solicitud → lockout
  - Max 3 solicitudes por email por hora → rate limit
  - reset_token es UUID único, de un solo uso, expira en 5 min
  - Errores de "email no existe" devuelven 200 (prevent enumeration)
  - Pedir nuevo código invalida el anterior
"""

import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth_service import _auth_client
from app.core.db import supabase

router = APIRouter(tags=["password-reset"])

# ── Stores en memoria ────────────────────────────────────────────────────────
# { email → { requested_at, attempts } }
_pending: dict = {}

# { reset_token_hash → { user_id, email, expires_at, used } }
_reset_tokens: dict = {}

# Rate limit solicitudes: { email → [timestamp, ...] }
_request_history: dict = {}

# ── Constantes ───────────────────────────────────────────────────────────────
OTP_EXPIRY_MINUTES   = 5
RESET_TOKEN_MINUTES  = 5
MAX_CODE_ATTEMPTS    = 5
MAX_REQUESTS_PER_HOUR = 3
MIN_PASSWORD_LENGTH  = 8


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _rate_limited(email: str) -> bool:
    """True si el email superó MAX_REQUESTS_PER_HOUR en la última hora."""
    cutoff = _now() - timedelta(hours=1)
    history = _request_history.get(email, [])
    history = [t for t in history if t > cutoff]
    _request_history[email] = history
    return len(history) >= MAX_REQUESTS_PER_HOUR


def _record_request(email: str):
    _request_history.setdefault(email, []).append(_now())


def _invalidate_reset_tokens(email: str):
    """Marca como usados todos los reset_tokens existentes de este email."""
    for data in _reset_tokens.values():
        if data["email"] == email:
            data["used"] = True


# ── Modelos ──────────────────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: str

class VerifyCodeRequest(BaseModel):
    email: str
    code: str          # 6 dígitos, con o sin guión

class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    """Envía OTP al email. Responde 200 siempre (prevent enumeration)."""
    email = req.email.strip().lower()

    # Rate limit silencioso
    if _rate_limited(email):
        # Devolvemos 200 para no revelar que el email existe y está siendo spameado
        return {"ok": True}

    _record_request(email)

    try:
        client = _auth_client()
        client.auth.sign_in_with_otp({
            "email": email,
            "options": {"should_create_user": False},
        })
    except Exception:
        # Si el email no existe u otro error → silencioso
        pass

    # Registrar solicitud (para controlar expiración y reintentos)
    _pending[email] = {
        "requested_at": _now(),
        "attempts": 0,
    }

    # Invalidar reset_tokens anteriores de este email
    _invalidate_reset_tokens(email)

    return {"ok": True}


@router.post("/forgot-password/verify")
def verify_code(req: VerifyCodeRequest):
    """Valida el OTP. Devuelve reset_token válido 5 min si es correcto."""
    email = req.email.strip().lower()
    # Limpiar el guión si viene en formato XXX-XXX
    code = req.code.strip().replace("-", "").replace(" ", "")

    # Validar formato (debe ser 6 dígitos)
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(status_code=400, detail="Formato de código inválido.")

    # Verificar que existe una solicitud pendiente
    pending = _pending.get(email)
    if not pending:
        raise HTTPException(
            status_code=400,
            detail="No hay una solicitud de recuperación activa para este email."
        )

    # Verificar expiración (5 min desde que se pidió)
    elapsed = _now() - pending["requested_at"]
    if elapsed > timedelta(minutes=OTP_EXPIRY_MINUTES):
        del _pending[email]
        raise HTTPException(
            status_code=400,
            detail="El código expiró. Solicitá uno nuevo."
        )

    # Verificar límite de intentos
    if pending["attempts"] >= MAX_CODE_ATTEMPTS:
        del _pending[email]
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos fallidos. Solicitá un nuevo código."
        )

    # Incrementar intentos antes de verificar (evita timing attacks)
    pending["attempts"] += 1

    # Verificar OTP con Supabase
    try:
        client = _auth_client()
        response = client.auth.verify_otp({
            "email": email,
            "token": code,
            "type": "email",
        })
        user = response.user
        if not user:
            raise Exception("Sin usuario en respuesta")
    except Exception:
        attempts_left = MAX_CODE_ATTEMPTS - pending["attempts"]
        if attempts_left <= 0:
            del _pending[email]
            raise HTTPException(
                status_code=429,
                detail="Demasiados intentos fallidos. Solicitá un nuevo código."
            )
        raise HTTPException(
            status_code=400,
            detail=f"Código incorrecto. Intentos restantes: {attempts_left}."
        )

    # OTP válido → limpiar pending
    user_id = user.id
    del _pending[email]

    # Invalidar reset_tokens anteriores
    _invalidate_reset_tokens(email)

    # Generar reset_token opaco de un solo uso
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash(raw_token)

    _reset_tokens[token_hash] = {
        "user_id":    user_id,
        "email":      email,
        "expires_at": _now() + timedelta(minutes=RESET_TOKEN_MINUTES),
        "used":       False,
    }

    return {"reset_token": raw_token}


@router.post("/forgot-password/reset")
def reset_password(req: ResetPasswordRequest):
    """Actualiza la contraseña usando el reset_token obtenido en /verify."""

    # Validar nueva contraseña
    if len(req.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
        )

    token_hash = _hash(req.reset_token)
    token_data = _reset_tokens.get(token_hash)

    if not token_data:
        raise HTTPException(status_code=400, detail="Token inválido o expirado.")

    if token_data["used"]:
        raise HTTPException(status_code=400, detail="Este token ya fue utilizado.")

    if _now() > token_data["expires_at"]:
        del _reset_tokens[token_hash]
        raise HTTPException(
            status_code=400,
            detail="El tiempo para cambiar la contraseña expiró. Solicitá un nuevo código."
        )

    # Marcar como usado ANTES de llamar a Supabase (evita doble uso por error de red)
    token_data["used"] = True

    try:
        client = _auth_client()
        client.auth.admin.update_user_by_id(
            token_data["user_id"],
            {"password": req.new_password}
        )
    except Exception as e:
        # Si falla, desmarcar para permitir reintento
        token_data["used"] = False
        raise HTTPException(
            status_code=500,
            detail="No se pudo actualizar la contraseña. Intentá de nuevo."
        )

    # Limpiar el token del store
    del _reset_tokens[token_hash]

    return {"ok": True}
