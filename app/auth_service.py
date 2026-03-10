from app.supabase_client import supabase
import time

def register_user(email: str, password: str, nombre: str):
    # Crear usuario en Supabase Auth
    response = supabase.auth.sign_up({
        "email": email,
        "password": password,
    })

    user = response.user
    if not user:
        raise Exception("Error al crear el usuario")


    time.sleep(0.5) 
    # Crear perfil en users_profiles
    supabase.table("users_profiles").insert({
        "id": user.id,
        "nombre": nombre,
        "onboarding_completo": False,
    }).execute()

    return user


def login_user(email: str, password: str):
    response = supabase.auth.sign_in_with_password({
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
    }


def get_user_profile(user_id: str):
    response = supabase.table("users_profiles") \
        .select("*") \
        .eq("id", user_id) \
        .execute()

    # Si no existe el perfil, devolver onboarding_completo False
    # para que la app lo mande al onboarding en vez de romper
    if not response.data:
        return {"onboarding_completo": False}

    return response.data[0]