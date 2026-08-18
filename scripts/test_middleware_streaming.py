"""
Verifica que los middlewares de main.py NO rompan el streaming.

Contexto: en producción /chat/stream entrega el mensaje del LLM de golpe (69
chunks en 74ms, ~900 por segundo, imposible para generación en vivo) en vez de
irlo goteando. Una hipótesis era BaseHTTPMiddleware, que en algunas versiones
de Starlette junta el cuerpo de la respuesta antes de mandarlo.

RESULTADO: la hipótesis era FALSA. Con la versión de Starlette que usa este
proyecto, BaseHTTPMiddleware NO bufferiza: medido acá abajo, el primer chunk
llega a los ~108ms igual que con ASGI puro (~112ms), y los dos gotean con
separación de 101ms. Se probó reescribir los middlewares como ASGI puro y se
revirtió, porque no arreglaba nada y tocaba código de todos los requests.

Este test queda igual por dos motivos: deja constancia de que el middleware ya
se descartó como causa (para no volver a sospechar de él), y es una red contra
regresiones — si algún día alguien agrega un middleware que sí bufferiza, acá
salta.

⚠️ Levanta un uvicorn de verdad y pega por HTTP real. NO se puede testear esto
con httpx.ASGITransport: ese transporte junta la respuesta por su cuenta y da
el mismo resultado con y sin middleware (verificado: 514ms para el primer
chunk incluso sin ningún middleware). O sea que mediría el arnés, no el código.

Correr con: venv/bin/python scripts/test_middleware_streaming.py
"""
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.main import NoCacheJSMiddleware, RequestLoggingMiddleware

CHUNKS = 5
DEMORA = 0.1  # 100ms entre chunks -> el mensaje entero tarda ~500ms

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    if ok:
        print(f"✅ {nombre}")
    else:
        fallos += 1
        print(f"❌ {nombre}{chr(10) + '   ' + detalle if detalle else ''}")


def _puerto_libre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()
    return puerto


def _app_con(middlewares):
    app = FastAPI()
    for mw in middlewares:
        app.add_middleware(mw)

    # Arranca con /chat para caer dentro de _PREFIJOS_API y que el middleware
    # de logging haga su trabajo (si no, se saltea y no probaría nada).
    @app.get("/chat/prueba-stream")
    async def _stream():
        import asyncio

        async def gen():
            for i in range(CHUNKS):
                await asyncio.sleep(DEMORA)
                yield f"chunk{i}\n"

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    return app


def _medir(app):
    """Levanta uvicorn, pide el stream por HTTP real y devuelve los ms en que
    llegó cada chunk. Devuelve también el servidor para poder frenarlo."""
    puerto = _puerto_libre()
    config = uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="error")
    server = uvicorn.Server(config)
    hilo = threading.Thread(target=server.run, daemon=True)
    hilo.start()

    esperando = time.perf_counter()
    while not server.started:
        if time.perf_counter() - esperando > 10:
            raise RuntimeError("uvicorn no arrancó")
        time.sleep(0.02)

    marcas = []
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{puerto}", timeout=30) as cli:
            inicio = time.perf_counter()
            with cli.stream("GET", "/chat/prueba-stream") as r:
                for _ in r.iter_lines():
                    marcas.append((time.perf_counter() - inicio) * 1000)
    finally:
        server.should_exit = True
        hilo.join(timeout=10)
    return marcas


def _separacion(marcas):
    if len(marcas) < 2:
        return 0.0
    return (marcas[-1] - marcas[0]) / (len(marcas) - 1)


# ── 1. Los middlewares REALES dejan pasar el stream de a pedazos ─────────
marcas_reales = _medir(_app_con([NoCacheJSMiddleware, RequestLoggingMiddleware]))
sep_reales = _separacion(marcas_reales)
print(f"   → middlewares REALES de main.py: primer chunk {marcas_reales[0]:.0f}ms, "
      f"separación media {sep_reales:.0f}ms, marcas {[round(m) for m in marcas_reales]}")

check(f"llegan los {CHUNKS} chunks", len(marcas_reales) == CHUNKS, f"llegaron {len(marcas_reales)}")
check(
    "los chunks llegan SEPARADOS (streaming vivo)",
    sep_reales > 50,
    f"separación media {sep_reales:.0f}ms (bufferizado daría ~0)",
)
# Lo que de verdad importa para el modo llamada: poder hablar la primera
# oración sin esperar a que el LLM termine todo el mensaje.
check(
    "el PRIMER chunk llega temprano, sin esperar al resto",
    marcas_reales[0] < DEMORA * 1000 * (CHUNKS - 1),
    f"primer chunk a los {marcas_reales[0]:.0f}ms (el mensaje entero tarda ~{DEMORA*1000*CHUNKS:.0f}ms)",
)


# ── 2. La comparación que descartó la hipótesis ──────────────────────────
# Réplica mínima de un middlware BaseHTTPMiddleware. NO es un assert de
# "el nuevo es mejor": se midió y resultó que da lo mismo. Queda como registro
# ejecutable de que esta vía ya se probó, para no perder tiempo sospechando de
# ella otra vez.
class _NoCacheViejo(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache"
        return response


class _LoggingViejo(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Request-ID"] = "test"
        return response


marcas_base = _medir(_app_con([_NoCacheViejo, _LoggingViejo]))
sep_base = _separacion(marcas_base)
print(f"   → BaseHTTPMiddleware pelado (control): primer chunk {marcas_base[0]:.0f}ms, "
      f"separación media {sep_base:.0f}ms, marcas {[round(m) for m in marcas_base]}")

check(
    "BaseHTTPMiddleware TAMPOCO bufferiza (hipótesis descartada, no regresión)",
    sep_base > 50,
    f"separación media {sep_base:.0f}ms — si esto pasa a ~0, esta versión de "
    "Starlette SÍ bufferiza y la hipótesis vuelve a estar viva",
)
print(f"   → diferencia entre los dos en el primer chunk: "
      f"{abs(marcas_base[0] - marcas_reales[0]):.0f}ms (ruido; no es la causa)")

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(0 if fallos == 0 else 1)
