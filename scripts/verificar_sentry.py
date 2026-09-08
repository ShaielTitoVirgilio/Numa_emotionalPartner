"""
Comprueba que Sentry está bien configurado Y que la privacidad se respeta.

    venv/bin/python scripts/verificar_sentry.py

Manda 2 eventos de prueba al proyecto de Sentry configurado en SENTRY_DSN:
uno con un error "no manejado" y otro pasando por capturar_error(), que es
como la app reporta los errores que atrapa. Además imprime lo que se enviaría,
ya scrubeado, para que puedas confirmar con tus propios ojos que NO viaja
contenido de conversaciones.

Si SENTRY_DSN no está seteada, avisa y no manda nada.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import config
from app.core.observability import _before_send, capturar_error, init_sentry, marcar_usuario

print("=" * 68)
print("1. ¿Hay DSN configurada?")
print("=" * 68)
if not config.SENTRY_DSN:
    print("  ✗ SENTRY_DSN está vacía: Sentry NO va a reportar nada.")
    print("    Agregala al .env (local) y a las variables de Railway (producción).")
    sys.exit(1)

dsn = config.SENTRY_DSN
print(f"  ✓ DSN presente: {dsn[:22]}…{dsn[-12:]}")
print(f"    environment          = {config.SENTRY_ENVIRONMENT}")
print(f"    traces_sample_rate   = {config.SENTRY_TRACES_SAMPLE_RATE}"
      f"{'   (0 = sin datos de performance)' if not config.SENTRY_TRACES_SAMPLE_RATE else ''}")

print()
print("=" * 68)
print("2. Prueba de privacidad: ¿el filtro borra lo sensible?")
print("=" * 68)
evento_falso = {
    "request": {
        "data": {"conversation": [{"role": "user", "content": "algo muy privado"}]},
        "cookies": {"sesion": "abc"},
        "query_string": "access_token=secreto",
        "headers": {"Authorization": "Bearer supersecreto", "User-Agent": "Safari"},
    },
    "extra": {"mensaje": "texto privado del usuario", "modelo": "gpt-5.6-luna"},
}
limpio = _before_send(evento_falso, {})
req = limpio.get("request", {})
checks = [
    ("body del request eliminado",      "data" not in req),
    ("cookies eliminadas",              "cookies" not in req),
    ("query string eliminada",          "query_string" not in req),
    ("header Authorization scrubeado",  req.get("headers", {}).get("Authorization") == "[scrubbed]"),
    ("extra['mensaje'] scrubeado",      limpio["extra"]["mensaje"] == "[scrubbed]"),
    ("dato NO sensible conservado",     limpio["extra"]["modelo"] == "gpt-5.6-luna"),
]
todo_ok = True
for nombre, ok in checks:
    print(f"  {'✓' if ok else '✗'} {nombre}")
    todo_ok &= ok
if not todo_ok:
    print("\n  ✗ La privacidad NO se está respetando. NO uses esto en producción.")
    sys.exit(1)

print()
print("=" * 68)
print("3. Enviando 2 eventos de prueba a Sentry…")
print("=" * 68)
if not init_sentry():
    print("  ✗ init_sentry() devolvió False.")
    sys.exit(1)
print("  ✓ Sentry inicializado")

marcar_usuario("00000000-0000-0000-0000-000000000000")

# a) error reportado por capturar_error() — el camino de los `except` de la app
try:
    raise ValueError("PRUEBA Numa: error manejado (capturar_error)")
except ValueError as e:
    capturar_error(e, contexto="verificacion_sentry", origen="script")
print("  ✓ evento 1 enviado (capturar_error, contexto=verificacion_sentry)")

# b) excepción no manejada — el camino automático del SDK
import sentry_sdk
try:
    raise RuntimeError("PRUEBA Numa: error no manejado")
except RuntimeError as e:
    sentry_sdk.capture_exception(e)
print("  ✓ evento 2 enviado (capture_exception)")

sentry_sdk.flush(timeout=10)
time.sleep(1)

print()
print("=" * 68)
print("Andá a tu proyecto en Sentry: deberías ver los 2 eventos 'PRUEBA Numa',")
print(f"en el environment '{config.SENTRY_ENVIRONMENT}', con el user id 0000…0000")
print("y SIN nada del contenido de las conversaciones.")
print("=" * 68)
