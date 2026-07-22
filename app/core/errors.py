# app/core/errors.py
"""
Distinción entre errores "esperados" e "inesperados".

Antes toda la API hacía `raise HTTPException(detail=str(e))`. Eso mezclaba dos
cosas muy distintas en la misma respuesta:

  - Mensajes escritos a propósito para el usuario ("Email o contraseña
    incorrectos") → está bien mostrarlos.
  - Errores técnicos imprevistos (Supabase caído, KeyError, timeout) → el
    usuario terminaba viendo texto crudo tipo {'code': '23503', ...} en medio
    de una app en español, y de paso filtrábamos detalles internos.

NumaError marca el primer caso: su mensaje SÍ se le muestra al usuario.
Cualquier otra excepción se considera un bug/incidente: se reporta a Sentry y
al usuario se le devuelve un mensaje genérico.
"""

MENSAJE_GENERICO = "Algo salió mal de nuestro lado. Probá de nuevo en un momento."


class NumaError(Exception):
    """Error cuyo mensaje está pensado para mostrarle al usuario."""


def es_credencial_invalida(e: BaseException) -> bool:
    """¿El fallo de login es por credenciales malas (normal) o por un problema nuestro?

    Un usuario que se equivoca la contraseña es un evento esperado y no debe
    ensuciar Sentry. Pero si Supabase está caído, hoy el usuario ve
    "Email o contraseña incorrectos" y nosotros no nos enteramos de nada:
    ese caso sí queremos reportarlo.
    """
    texto = str(e).lower()
    marcadores = (
        "invalid login credentials",
        "invalid_credentials",
        "invalid credentials",
        "email not confirmed",
        "email_not_confirmed",
    )
    return any(m in texto for m in marcadores)
