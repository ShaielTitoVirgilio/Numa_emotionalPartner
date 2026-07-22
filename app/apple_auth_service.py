import hmac
import hashlib
import os
import requests
import jwt
from typing import Optional
from jwt.algorithms import RSAAlgorithm
from app.auth_service import _auth_client
from app.core.db import supabase
from app.core.errors import NumaError
from app.core.retry import with_retry

APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISS = "https://appleid.apple.com"
BUNDLE_ID = "app.numa.mobile"


def _fetch_apple_public_keys() -> list:
    resp = requests.get(APPLE_KEYS_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()["keys"]


def verify_apple_token(identity_token: str) -> dict:
    keys = _fetch_apple_public_keys()

    header = jwt.get_unverified_header(identity_token)
    kid = header.get("kid")

    matching = next((k for k in keys if k["kid"] == kid), None)
    if not matching:
        raise NumaError("Clave pública de Apple no encontrada.")

    public_key = RSAAlgorithm.from_jwk(matching)

    try:
        payload = jwt.decode(
            identity_token,
            public_key,
            algorithms=["RS256"],
            audience=BUNDLE_ID,
            issuer=APPLE_ISS,
        )
    except jwt.ExpiredSignatureError:
        raise NumaError("El token de Apple expiró. Intentá de nuevo.")
    except jwt.InvalidTokenError as e:
        raise NumaError(f"Token de Apple inválido: {e}")

    return payload


def _derive_password(apple_sub: str) -> str:
    secret = os.getenv("SECRET_KEY", "numa-apple-fallback-secret")
    return hmac.new(secret.encode(), apple_sub.encode(), hashlib.sha256).hexdigest()


def find_or_create_apple_user(
    apple_sub: str,
    email: Optional[str],
    full_name: Optional[str],
) -> dict:
    derived_password = _derive_password(apple_sub)
    client = _auth_client()

    # Buscar usuario existente por apple_sub
    existing = supabase.table("users_profiles") \
        .select("id") \
        .eq("apple_sub", apple_sub) \
        .execute()

    if existing.data:
        user_id = existing.data[0]["id"]
        auth_user = supabase.auth.admin.get_user_by_id(user_id)
        user_email = auth_user.user.email if auth_user.user else email

        if not user_email:
            raise NumaError("No se pudo recuperar tu cuenta. Contactá soporte.")

        try:
            response = client.auth.sign_in_with_password({
                "email": user_email,
                "password": derived_password,
            })
            return _build_session(response)
        except Exception:
            raise NumaError("No se pudo iniciar sesión con Apple. Intentá de nuevo.")

    # Usuario nuevo — necesitamos email
    if not email:
        raise NumaError(
            "No pudimos obtener tu email de Apple. "
            "En tu iPhone andá a Ajustes → ID de Apple → Contraseñas y Seguridad → "
            "Apps que usan tu ID de Apple → eliminá Numa y volvé a intentarlo."
        )

    # Intentar crear usuario en Supabase Auth
    try:
        response = client.auth.sign_up({
            "email": email,
            "password": derived_password,
        })
        user = response.user
        if not user:
            raise NumaError("No se pudo crear la cuenta con Apple.")
    except Exception as e:
        err = str(e).lower()
        if "already registered" in err or "23505" in err:
            raise NumaError(
                "Este email ya está registrado. "
                "Iniciá sesión con email y contraseña o con Google."
            )
        raise

    # Apple sólo manda el nombre la primera vez que un Apple ID autoriza la app.
    # Cuando no viene, NO lo inventamos: rellenar con el local-part del email
    # significaba guardar "vcd4ckkbvj" (Ocultar mi correo) como si fuera un
    # nombre real, y terminaba en el prompt como "Se llama vcd4ckkbvj".
    # Vacío es el estado honesto: el perfil no muestra nombre, Numa no lo usa,
    # y el usuario puede ponerlo desde Perfil o diciéndoselo a Numa.
    nombre = full_name or ""

    # Guardar perfil con apple_sub (requiere columna apple_sub en users_profiles)
    with_retry(lambda: supabase.table("users_profiles").upsert({
        "id": user.id,
        "nombre": nombre,
        "onboarding_completo": False,
        "apple_sub": apple_sub,
    }).execute())

    # Confirmar email automáticamente (Apple ya lo verificó)
    try:
        supabase.auth.admin.update_user_by_id(user.id, {"email_confirm": True})
    except Exception:
        pass

    login_response = client.auth.sign_in_with_password({
        "email": email,
        "password": derived_password,
    })

    return _build_session(login_response)


def _build_session(response) -> dict:
    return {
        "user_id": response.user.id,
        "email": response.user.email,
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
    }
