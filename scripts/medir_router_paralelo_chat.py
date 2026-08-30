"""
Mide el turno de /chat REAL (con el router en paralelo) contra servicios REALES
(Supabase + LLM), para comparar contra la línea de base de
scripts/profile_chat_turn.py (todo secuencial) con el MISMO usuario/mensaje.

No es una simulación de cuánto se ahorraría — corre _preparar_turno() y
_resolver_router_paralelo_chat() tal cual quedaron en el código, de punta a
punta, y mide el reloj real.

Solo LEE: las background_tasks quedan encoladas pero nunca se ejecutan (nadie
llama a bt.tasks acá), así que no escribe conversación ni memorias ni logs de
crisis. Consume tokens de 2 LLMs (router + principal) por repetición.

    venv/bin/python scripts/medir_router_paralelo_chat.py [repeticiones]
"""
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import BackgroundTasks

import app.routes.chat_router as cr
from app.llm_client import LLMClient

USER = os.getenv("PROFILE_USER_ID", "cd4127a1-1c7f-4db3-8de4-f58f5e671d72")
MSG = "Hoy salí a caminar por la rambla y estuvo tranquilo."
REPETICIONES = int(sys.argv[1]) if len(sys.argv) > 1 else 5

llm = LLMClient()
cr.llm = llm  # mismo cliente que usa chat_endpoint


def _body():
    return cr.ChatRequest(conversation=[cr.Message(role="user", content=MSG)])


print(f"user_id: {USER}")
print(f"{REPETICIONES} repeticiones, calentando conexiones (no se mide)…\n")

# Precalentar: la primera llamada a cada proveedor suele traer overhead de
# conexión/DNS que no queremos mezclado con la medición real.
try:
    cr._preparar_turno(_body(), USER, BackgroundTasks())
except Exception as e:
    print(f"⚠️ precalentamiento falló (sigue igual): {e}")

filas = []
for i in range(REPETICIONES):
    bt = BackgroundTasks()
    t0 = time.perf_counter()
    turno = cr._preparar_turno(_body(), USER, bt)
    t_prep = time.perf_counter() - t0

    if turno["crisis_confirmada"]:
        print(f"vuelta {i+1}: crisis confirmada (no debería pasar con este mensaje) — salteo")
        continue

    t1 = time.perf_counter()
    result = llm.generate_response(
        conversation=[m.model_dump() for m in turno["conversation"]],
        system_prompt=turno["system_prompt"],
    )
    t_llm = time.perf_counter() - t1

    t2 = time.perf_counter()
    resolucion = cr._resolver_router_paralelo_chat(
        fut_router_paralelo=turno.get("_fut_router_paralelo"),
        crisis_score=turno["crisis_score"],
        ultimo_mensaje=turno["ultimo_mensaje"],
        user_id=USER,
        background_tasks=bt,
        reconstruir_prompt=turno["_reconstruir_prompt"],
        llamar_llm=lambda sp: llm.generate_response(
            conversation=[m.model_dump() for m in turno["conversation"]], system_prompt=sp,
        ),
        evento_proactivo=turno["evento_proactivo"],
        tema_abierto=turno["tema_abierto"],
        memoria_ctx_id=turno["memoria_ctx_id"],
    )
    t_resolver = time.perf_counter() - t2

    t_total = t_prep + t_llm + t_resolver
    diag = resolucion["diag"]
    filas.append((t_prep, t_llm, t_resolver, t_total, diag.get("t_router_paralelo_ms"), diag.get("router_accion")))
    print(
        f"vuelta {i+1}: prep={t_prep*1000:6.0f}ms  llm={t_llm*1000:6.0f}ms  "
        f"resolver_router={t_resolver*1000:5.0f}ms  TOTAL={t_total*1000:6.0f}ms  "
        f"(router real: {diag.get('t_router_paralelo_ms')}ms, accion={diag.get('router_accion')})"
    )

if not filas:
    print("\nSin datos (todas las vueltas fallaron o dieron crisis).")
    sys.exit(1)

preps = [f[0] for f in filas]
llms = [f[1] for f in filas]
resolvers = [f[2] for f in filas]
totales = [f[3] for f in filas]

print("\n" + "=" * 78)
print(f"{'':<20} {'mejor':>8} {'mediana':>8} {'peor':>8}")
print(f"{'t_preparar_turno':<20} {min(preps)*1000:7.0f}ms {statistics.median(preps)*1000:7.0f}ms {max(preps)*1000:7.0f}ms")
print(f"{'t_llm_principal':<20} {min(llms)*1000:7.0f}ms {statistics.median(llms)*1000:7.0f}ms {max(llms)*1000:7.0f}ms")
print(f"{'t_resolver_router':<20} {min(resolvers)*1000:7.0f}ms {statistics.median(resolvers)*1000:7.0f}ms {max(resolvers)*1000:7.0f}ms")
print(f"{'TOTAL turno':<20} {min(totales)*1000:7.0f}ms {statistics.median(totales)*1000:7.0f}ms {max(totales)*1000:7.0f}ms")
print("=" * 78)
print(
    "\nt_resolver_router chico (idealmente ~0ms) confirma que el router ya había\n"
    "terminado cuando el LLM principal contestó — el 1.5-2s del router quedó\n"
    "'escondido' detrás del LLM principal en vez de sumarse antes.\n"
    "Compará t_preparar_turno de acá contra 'TOTAL como está hoy' de\n"
    "profile_chat_turn.py (mismo user/mensaje) para ver la línea de base vieja."
)
