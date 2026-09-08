"""
Verifica el rate limit de los endpoints de autenticación (portado de staging
al lote A, 2026-09-08).

Por qué importa: sin esto, /login y /verify-email quedan expuestos a fuerza
bruta (el OTP de verify-email son 8 dígitos) y /register a spam de cuentas.
/chat ya tenía rate limit desde el vamos; estos cuatro no.

También cubre el riesgo del lado opuesto: un límite DEMASIADO bajo deja
afuera a usuarios legítimos. /refresh es el caso delicado — la app lo llama
sola al abrir y al vencerse el token — por eso tiene el límite más alto.

Correr con: venv/bin/python scripts/test_rate_limit_auth.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from app.main import app

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    if ok:
        print(f"✅ {nombre}")
    else:
        fallos += 1
        print(f"❌ {nombre}{chr(10) + '   ' + detalle if detalle else ''}")


client = TestClient(app)

# (ruta, body, límite declarado)
CASOS = [
    ("/register", {"email": "x@x.com", "password": "12345678", "nombre": "X"}, 5),
    ("/login", {"email": "x@x.com", "password": "mala"}, 10),
    ("/refresh", {"refresh_token": "token-muerto"}, 30),
    ("/verify-email", {"email": "x@x.com", "token": "12345678"}, 5),
]

for ruta, body, limite in CASOS:
    # Se manda el límite + 1: las primeras `limite` pueden fallar por
    # credenciales (401/500, no importa), pero NINGUNA debería dar 429.
    # La que sobra sí.
    codigos = []
    for _ in range(limite + 1):
        try:
            codigos.append(client.post(ruta, json=body).status_code)
        except Exception:
            codigos.append(0)

    dentro = codigos[:limite]
    ultima = codigos[limite]
    check(
        f"{ruta}: las primeras {limite} NO dan 429",
        429 not in dentro,
        f"códigos={dentro}",
    )
    check(
        f"{ruta}: la {limite + 1} da 429 (límite activo)",
        ultima == 429,
        f"dio {ultima}, esperaba 429",
    )

# /refresh es el que más margen necesita: la app lo llama sola.
check(
    "/refresh tiene el límite más alto de los cuatro",
    max(c[2] for c in CASOS if c[0] != "/refresh") < 30,
)

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
