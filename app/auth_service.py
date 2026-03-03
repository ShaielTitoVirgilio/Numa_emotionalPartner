from app.supabase_client import supabase


def register_user(email: str, password: str, nombre: str):
    # Crear usuario en Supabase Auth
    response = supabase.auth.sign_up({
        "email": email,
        "password": password,
    })

    user = response.user
    if not user:
        raise Exception("Error al crear el usuario")

    # Crear perfil en users_profiles
    supabase.table("users_profiles").insert({
        "id": user.id,
        "nombre": nombre,
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
    response = supabase.table("users_profiles")\
        .select("*")\
        .eq("id", user_id)\
        .single()\
        .execute()

    return response.data