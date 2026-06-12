# app/core/ratelimit.py
"""
Key function para slowapi consciente del proxy.

Detrás del proxy de Railway, request.client.host es siempre la IP del proxy:
el rate limit por IP agrupaba a todos los usuarios en un mismo bucket.
Se usa el primer hop de X-Forwarded-For (lo setea el proxy) y se cae a la
IP directa si el header no está.
"""

from starlette.requests import Request
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)
