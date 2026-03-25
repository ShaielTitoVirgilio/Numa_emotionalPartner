from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from app.auth_service import register_user, login_user, get_user_profile
from app.supabase_client import supabase

router = APIRouter()

class RegisterRequest(BaseModel):
    email: str
    password: str
    nombre: str

class LoginRequest(BaseModel):
    email: str
    password: str

class SubscriptionRequest(BaseModel):
    user_id: str
    subscription_data: Dict[str, Any]

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

@router.get("/profile/{user_id}")
def profile_endpoint(user_id: str):
    try:
        profile = get_user_profile(user_id)
        return profile
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/subscribe")
def subscribe_endpoint(request: SubscriptionRequest):
    try:
        # Guarda o actualiza la suscripción del usuario
        supabase.table("user_notifications").upsert({
            "user_id": request.user_id,
            "subscription_data": request.subscription_data
        }).execute()
        return {"message": "Suscripción guardada correctamente"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))