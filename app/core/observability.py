# app/core/observability.py
"""
Reporte de errores a Sentry.

Numa maneja conversaciones de salud mental y detección de crisis: el contenido
de los mensajes NUNCA debe salir del servidor. Por eso esta configuración es
deliberadamente restrictiva y NO se debe relajar sin pensarlo:

  - send_default_pii=False    → no manda IP, cookies ni headers de auth.
  - max_request_body_size="never" → no captura el body del request (ahí viajan
    los mensajes del chat y el audio).
  - _before_send()            → borra cualquier resto de body/headers/cookies
    que alguna integración haya podido adjuntar, y recorta los `extra`.

Lo que SÍ se manda: tipo de excepción, stacktrace, endpoint, y el user_id
(un UUID opaco, necesario para poder ayudar a un usuario concreto que reporta
un problema). El user_id no revela contenido de las conversaciones.

Si SENTRY_DSN no está seteada, init_sentry() no hace nada: en local y en tests
la app corre igual, sin reportar a ningún lado.
"""

from typing import Any, Dict, Optional

from app.core.config import config


# Claves que jamás queremos ver en un evento de Sentry.
_CLAVES_SENSIBLES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-admin-key",
    "password",
    "token",
    "access_token",
    "refresh_token",
    "apikey",
    "api_key",
    "subscription_data",
    "mensaje",
    "message",
    "content",
    "conversation",
    "messages",
    "texto",
    "text",
}


def _scrub(valor: Any, profundidad: int = 0) -> Any:
    """Reemplaza recursivamente los valores de claves sensibles por un marcador."""
    if profundidad > 6:
        return "[truncado]"
    if isinstance(valor, dict):
        limpio = {}
        for k, v in valor.items():
            if str(k).lower() in _CLAVES_SENSIBLES:
                limpio[k] = "[scrubbed]"
            else:
                limpio[k] = _scrub(v, profundidad + 1)
        return limpio
    if isinstance(valor, (list, tuple)):
        return [_scrub(v, profundidad + 1) for v in valor[:20]]
    return valor


def _before_send(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Última barrera antes de que el evento salga del servidor."""
    request = event.get("request")
    if isinstance(request, dict):
        # El body puede contener la conversación entera: no sale nunca.
        request.pop("data", None)
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                k: ("[scrubbed]" if k.lower() in _CLAVES_SENSIBLES else v)
                for k, v in headers.items()
            }
        # La query string puede llevar tokens.
        request.pop("query_string", None)

    if isinstance(event.get("extra"), dict):
        event["extra"] = _scrub(event["extra"])

    if isinstance(event.get("contexts"), dict):
        event["contexts"] = _scrub(event["contexts"])

    return event


def init_sentry() -> bool:
    """Inicializa Sentry si hay DSN configurada. Devuelve True si quedó activo."""
    dsn = config.SENTRY_DSN
    if not dsn:
        return False

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=config.SENTRY_ENVIRONMENT,
        # Sin performance monitoring por defecto: no lo necesitamos todavía y
        # consume cuota del plan gratuito. Se sube por env var si hace falta.
        traces_sample_rate=config.SENTRY_TRACES_SAMPLE_RATE,
        # ── Privacidad (ver docstring del módulo) ──
        send_default_pii=False,
        max_request_body_size="never",
        before_send=_before_send,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
    )
    return True


def capturar_error(e: BaseException, contexto: str = "", **tags: str) -> None:
    """Reporta a Sentry un error que el código atrapa y convierte en respuesta.

    La app tiene decenas de `except Exception` que devuelven un HTTPException o
    un valor por defecto. Sentry solo captura automáticamente las excepciones NO
    manejadas, así que esos errores serían invisibles: esta función los reporta
    explícitamente sin cambiar el comportamiento de la app.

    Es no-op si Sentry no está configurado, y nunca lanza: si el reporte falla,
    el request del usuario sigue su curso igual.
    """
    try:
        import sentry_sdk

        client = sentry_sdk.get_client()
        if client is None or not client.is_active():
            return
        with sentry_sdk.new_scope() as scope:
            if contexto:
                scope.set_tag("contexto", contexto)
            for k, v in tags.items():
                scope.set_tag(k, v)
            sentry_sdk.capture_exception(e)
    except Exception:
        # Observabilidad nunca debe romper el request.
        pass
