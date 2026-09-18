"""Verifica que ningun cliente de Supabase del backend arranque el hilo de
refresco automatico de GoTrue.

Por que existe: con auto_refresh_token=True (el default de la libreria),
cualquier llamada que deje una sesion en el cliente (sign_in_with_password,
sign_up, verify_otp, refresh_session) arranca un threading.Timer que se
reprograma solo cada ~1h para siempre. Como _auth_client() crea un cliente
descartable por llamada, cada login/refresh dejaba un hilo huerfano rotando el
refresh_token de ese usuario por su cuenta -> el celular se quedaba con un token
ya usado -> "Invalid Refresh Token: Already Used" -> sesion cerrada sola.
Ver el comentario completo en app/auth_service.py, _auth_client().

No toca la red: create_client() no hace ninguna request, y el test del timer usa
un valor grande y lo cancela enseguida. Correr despues de tocar auth_service.py,
core/db.py, o de actualizar la libreria supabase.
"""

import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Sin .env real (CI, checkout limpio) igual tiene que poder correr: create_client
# valida que url/key no esten vacios, pero no se conecta a ningun lado.
os.environ.setdefault("SUPABASE_URL", "https://dummy.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "dummy-service-key")

from supabase import ClientOptions, create_client  # noqa: E402

from app.auth_service import _auth_client  # noqa: E402
from app.core.config import config  # noqa: E402
from app.core.db import supabase as cliente_compartido  # noqa: E402
from app.supabase_client import supabase as cliente_legacy  # noqa: E402

fallos = []


def _chequear_api_privada(auth):
    """La libreria expone esto como privado: si cambia de nombre, el test tiene
    que fallar ruidosamente en vez de pasar sin verificar nada."""
    for attr in ("_auto_refresh_token", "_refresh_token_timer", "_start_auto_refresh_token"):
        if not hasattr(auth, attr):
            fallos.append(
                f"La libreria supabase cambio su API interna: falta {attr!r}. "
                "Revisar a mano que el refresco automatico siga apagado."
            )
            return False
    return True


def verificar(nombre, client):
    auth = client.auth
    if not _chequear_api_privada(auth):
        return

    if auth._auto_refresh_token is not False:
        fallos.append(f"{nombre}: auto_refresh_token deberia ser False, es {auth._auto_refresh_token!r}")
        return

    # Prueba real del mecanismo: pedirle explicitamente que arranque el timer.
    hilos_antes = threading.active_count()
    auth._start_auto_refresh_token(3_600_000)
    if auth._refresh_token_timer is not None:
        auth._refresh_token_timer.cancel()
        fallos.append(f"{nombre}: arranco un threading.Timer de refresco pese a auto_refresh_token=False")
    elif threading.active_count() != hilos_antes:
        fallos.append(f"{nombre}: quedo un hilo vivo despues de _start_auto_refresh_token()")
    else:
        print(f"  OK  {nombre}: auto_refresh_token=False y no arranca ningun hilo")


print("Clientes reales de la app:")
verificar("app/core/db.py (cliente compartido)", cliente_compartido)
verificar("app/supabase_client.py (legacy, push)", cliente_legacy)
verificar("app/auth_service.py (_auth_client)", _auth_client())

# Control negativo: sin la opcion, el timer SI arranca. Si esto no pasara, el
# test de arriba no estaria probando nada.
print("Control (cliente con el default de la libreria):")
control = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
if _chequear_api_privada(control.auth):
    hilos_antes = threading.active_count()
    control.auth._start_auto_refresh_token(3_600_000)
    timer = control.auth._refresh_token_timer
    if timer is None:
        fallos.append(
            "Control: un cliente con el default NO arranco el timer. El default de la "
            "libreria cambio (o la API interna se movio) y este test ya no prueba nada."
        )
    else:
        print(f"  OK  el default si arranca el timer (hilos: {hilos_antes} -> {threading.active_count()})")
        timer.cancel()
        control.auth._refresh_token_timer = None

# Tambien en el caso que importa de verdad: un cliente nuevo por cada llamada.
if any(_auth_client().auth._auto_refresh_token is not False for _ in range(3)):
    fallos.append("_auth_client() devolvio algun cliente con auto_refresh_token=True")

if fallos:
    print("\nFALLO:")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\nTodo OK: ningun cliente del backend arranca el refresco automatico.")
