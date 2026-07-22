from supabase import create_client
from app.core.db import supabase
from app.core.config import config
from app.core.errors import NumaError, es_credencial_invalida
from app.core.observability import capturar_error
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
        raise NumaError("Error al crear el usuario")

    # Signup repetido: GoTrue devuelve un usuario ofuscado SIN identities para no
    # revelar si el email existe. Sin este corte, el upsert de abajo reintenta ~8s
    # contra un id inexistente (FK 23503) y el fetch de la app móvil muere antes
    # con "Network request failed" en vez de mostrar este mensaje.
    if not user.identities:
        raise NumaError("Este email ya está registrado. Probá iniciando sesión.")

    try:
        with_retry(lambda: supabase.table("users_profiles").upsert({
            "id": user.id,
            "nombre": nombre,
            "onboarding_completo": False,
        }).execute())
    except Exception as e:
        err = str(e)
        if "23503" in err or "foreign key" in err.lower():
            raise NumaError("Este email ya está registrado. Probá iniciando sesión.")
        raise

    return user


def login_user(email: str, password: str):
    try:
        response = _auth_client().auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
    except Exception as e:
        # Que el usuario se equivoque la contraseña es normal y no se reporta.
        # Pero si Supabase está caído (o mal configurado), antes el usuario veía
        # "Email o contraseña incorrectos" y nosotros no nos enterábamos nunca:
        # ese caso sí es un incidente nuestro.
        if not es_credencial_invalida(e):
            capturar_error(e, contexto="login_supabase")
        raise NumaError("Email o contraseña incorrectos")

    user = response.user
    session = response.session

    if not user or not session:
        raise NumaError("Email o contraseña incorrectos")

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
        raise NumaError("No se pudo renovar la sesión")
    return {
        "user_id": user.id,
        "email": user.email,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
    }


def verify_email_otp(email: str, token: str):
    response = _auth_client().auth.verify_otp({
        "email": email,
        "token": token,
        "type": "signup",
    })
    user = response.user
    session = response.session
    if not user or not session:
        raise NumaError("Código inválido o expirado")
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
