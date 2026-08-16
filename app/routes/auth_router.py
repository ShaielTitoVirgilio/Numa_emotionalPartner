from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from app.auth_service import register_user, login_user, get_user_profile, refresh_session, verify_email_otp
from app.core.auth import get_current_user_id
from app.core.errors import NumaError, MENSAJE_GENERICO
from app.core.observability import capturar_error
from app.core.ratelimit import client_ip
from app.repositories.user_repository import UserRepository

router = APIRouter()
user_repo = UserRepository()
# Sin rate limit acá, /register, /login, /refresh y /verify-email quedaban
# expuestos a fuerza bruta (login, el OTP de 8 dígitos de verify-email) y a
# spam de cuentas (register) sin ningún freno — a diferencia de /chat, que
# ya lo tenía desde el vamos.
limiter = Limiter(key_func=client_ip)

MAX_NOMBRE_CHARS = 60

class RegisterRequest(BaseModel):
    email: str
    password: str
    nombre: str

class LoginRequest(BaseModel):
    email: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class VerifyEmailRequest(BaseModel):
    email: str
    token: str

@router.post("/register")
@limiter.limit("5/minute")
def register_endpoint(request: Request, body: RegisterRequest):
    try:
        user = register_user(body.email, body.password, body.nombre)
        return {"message": "Usuario creado correctamente", "user_id": user.id}
    except NumaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        capturar_error(e, contexto="register")
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)

@router.post("/login")
@limiter.limit("10/minute")
def login_endpoint(request: Request, body: LoginRequest):
    try:
        result = login_user(body.email, body.password)
        return result
    except NumaError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        capturar_error(e, contexto="login")
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)

@router.post("/refresh")
@limiter.limit("30/minute")
def refresh_endpoint(request: Request, body: RefreshRequest):
    try:
        result = refresh_session(body.refresh_token)
        return result
    except NumaError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        capturar_error(e, contexto="refresh")
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)

@router.get("/profile/{user_id}")
def profile_endpoint(user_id: str, auth_user_id: str = Depends(get_current_user_id)):
    # Solo se puede leer el perfil propio: el user_id del path debe coincidir
    # con el del token. Antes cualquiera podía leer el perfil de cualquiera.
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="No podés acceder a este perfil")
    try:
        profile = get_user_profile(user_id)
        return profile
    except NumaError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        capturar_error(e, contexto="get_profile")
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)

class UpdateNombreRequest(BaseModel):
    nombre: str

    @field_validator("nombre")
    @classmethod
    def _limpiar(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v[:MAX_NOMBRE_CHARS]


@router.patch("/profile/nombre")
def update_nombre_endpoint(
    request: UpdateNombreRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Cambiar el nombre con el que Numa se dirige al usuario.

    Sólo toca `nombre`: el resto del perfil (respuestas del onboarding) queda
    intacto. El user_id sale del token, nunca del body.
    """
    try:
        user_repo.create_profile_if_missing(user_id)
        user_repo.upsert_profile(user_id, {"nombre": request.nombre})
        return {"nombre": request.nombre}
    except Exception as e:
        capturar_error(e, contexto="update_nombre")
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)


@router.post("/verify-email")
@limiter.limit("5/minute")
def verify_email_endpoint(request: Request, body: VerifyEmailRequest):
    try:
        result = verify_email_otp(body.email, body.token)
        return result
    except NumaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        capturar_error(e, contexto="verify_email")
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)