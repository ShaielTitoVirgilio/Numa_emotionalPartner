from supabase import create_client
from app.core.db import supabase
from app.core.config import config
from app.core.retry import with_retry


def _auth_client():
    # Fresh client per call: sign_in/sign_up mutate the client's internal session,
    # which would replace the service-key header on the shared `supabase` client
    # and cause all subsequent DB queries to use the (expirable) user JWT.
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)


def register_user(email: str, password: str, nombre: str):
    response = _auth_client().auth.sign_up({
        "email": email,
        "password": password,
    })

    user = response.user
    if not user:
        raise Exception("Error al crear el usuario")

    # Reintentar con backoff por si el usuario aún no propagó en auth.users
    with_retry(lambda: supabase.table("users_profiles").upsert({
        "id": user.id,
        "nombre": nombre,
        "onboarding_completo": False,
    }).execute())

    return user


def login_user(email: str, password: str):
    response = _auth_client().auth.sign_in_with_password({
        "email": email,
        "password": password,
    })

    user = response.user
    session = response.session

    if not user or not session:
        raise Exception("Email o contraseña incorrectos")

    return {
        "user_id": user.id,
        "email": user.email,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
    }


def refresh_session(refresh_token: str):
    response = _auth_client().auth.refresh_session(refresh_token)
    session = response.session
    user = response.user
    if not session or not user:
        raise Exception("No se pudo renovar la sesión")
    return {
        "user_id": user.id,
        "email": user.email,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
    }


def get_user_profile(user_id: str):
    response = supabase.table("users_profiles") \
        .select("*") \
        .eq("id", user_id) \
        .execute()

    if not response.data:
        return {"onboarding_completo": False}

    return response.data[0]
