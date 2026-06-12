from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.auth_service import register_user, login_user, get_user_profile, refresh_session, verify_email_otp
from app.core.auth import get_current_user_id

router = APIRouter()

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
def register_endpoint(request: RegisterRequest):
    try:
        user = register_user(request.email, request.password, request.nombre)
        return {"message": "Usuario creado correctamente", "user_id": user.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
def login_endpoint(request: LoginRequest):
    try:
        result = login_user(request.email, request.password)
        return result
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/refresh")
def refresh_endpoint(request: RefreshRequest):
    try:
        result = refresh_session(request.refresh_token)
        return result
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.get("/profile/{user_id}")
def profile_endpoint(user_id: str, auth_user_id: str = Depends(get_current_user_id)):
    # Solo se puede leer el perfil propio: el user_id del path debe coincidir
    # con el del token. Antes cualquiera podía leer el perfil de cualquiera.
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="No podés acceder a este perfil")
    try:
        profile = get_user_profile(user_id)
        return profile
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/verify-email")
def verify_email_endpoint(request: VerifyEmailRequest):
    try:
        result = verify_email_otp(request.email, request.token)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))