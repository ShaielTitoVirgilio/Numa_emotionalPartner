"""
Perfilador de un turno de chat: dónde se van los segundos.

Corre cada etapa del pipeline de /chat por separado, contra los servicios
REALES (LLMs y Supabase), y reporta cuánto tarda cada una. Sirve para saber
si una lentitud es del router, del LLM principal, de Supabase o de la red,
en vez de adivinar.

    venv/bin/python scripts/profile_chat_turn.py

Solo LEE (ninguna etapa escribe en la base). Consume unos pocos tokens de LLM
por corrida: son 2 llamadas × 3 repeticiones.
"""
import os
import statistics
import sys
import time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.context_router import clasificar_contexto
from app.crisis_detector import detectar_crisis
from app.llm_client import LLMClient
from app.memory_service import (
    get_checkin_hoy_cached,
    get_dias_inactivo,
    get_open_topics,
    get_proactive_memories,
    get_recent_memories,
    get_resource_memories,
    get_topic_patterns_cached,
)
from app.numa_prompt import construir_prompt
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.user_repository import UserRepository

# Poné acá tu user_id (sale de los logs del server: GET /profile/<uuid>).
USER = os.getenv("PROFILE_USER_ID", "cd4127a1-1c7f-4db3-8de4-f58f5e671d72")
MSG = "Hoy salí a caminar por la rambla y estuvo tranquilo."
CONV = [{"role": "user", "content": MSG}]
REPETICIONES = 3

user_repo = UserRepository()
feedback_repo = FeedbackRepository()
llm = LLMClient()

prompt = construir_prompt(
    perfil=None, memorias=[], patrones=[], es_inicio_sesion=False, num_interacciones=6,
    es_primera_vez=False, ubicacion=None, crisis_score=0.05,
    historial_reciente=CONV, mood_actual=None, ultimo_mensaje=MSG,
    preguntas_seguidas=0, hoy=date.today(), router_hints={"ok": False},
)

# (nombre, función, tipo, ¿depende del resultado del router?)
ETAPAS = [
    ("detectar_crisis (keywords)",   lambda: detectar_crisis(MSG),                                   "local",    False),
    ("clasificar_contexto [LLM #1]", lambda: clasificar_contexto(CONV),                              "LLM",      False),
    ("get_profile",                  lambda: user_repo.get_profile(USER),                            "supabase", False),
    ("get_recent_memories",          lambda: get_recent_memories(user_id=USER, days=30, max_items=12), "supabase", False),
    ("get_topic_patterns_cached",    lambda: get_topic_patterns_cached(user_id=USER),                "supabase", False),
    ("get_checkin_hoy_cached",       lambda: get_checkin_hoy_cached(USER),                           "supabase", False),
    ("get_dias_inactivo",            lambda: get_dias_inactivo(USER),                                "supabase", False),
    ("hay_crisis_reciente",          lambda: feedback_repo.hay_crisis_reciente(USER),                "supabase", False),
    ("get_proactive_memories",       lambda: get_proactive_memories(user_id=USER, hoy=date.today()), "supabase", True),
    ("get_open_topics",              lambda: get_open_topics(user_id=USER),                          "supabase", True),
    ("get_resource_memories",        lambda: get_resource_memories(user_id=USER),                    "supabase", True),
    ("generate_response [LLM #2]",   lambda: llm.generate_response(conversation=CONV, system_prompt=prompt), "LLM", True),
]

print(f"user_id: {USER}")
print("Calentando conexiones (no se mide)…")
for _n, fn, _t, _d in ETAPAS:
    try:
        fn()
    except Exception:
        pass

print(f"\n{'etapa':<32} {'mejor':>7} {'prom':>7}  tipo")
print("-" * 72)
medidas = {}
for nombre, fn, tipo, depende in ETAPAS:
    tiempos = []
    for _ in range(REPETICIONES):
        t0 = time.time()
        try:
            fn()
        except Exception as e:
            print(f"{nombre:<32}  ERROR: {str(e)[:28]}")
            break
        tiempos.append(time.time() - t0)
    if not tiempos:
        continue
    medidas[nombre] = (min(tiempos), statistics.mean(tiempos), tipo, depende)
    print(f"{nombre:<32} {min(tiempos):6.2f}s {statistics.mean(tiempos):6.2f}s  {tipo}")

llm_t   = sum(v[1] for v in medidas.values() if v[2] == "LLM")
sb_t    = sum(v[1] for v in medidas.values() if v[2] == "supabase")
sb_indep = sum(v[1] for v in medidas.values() if v[2] == "supabase" and not v[3])
sb_dep   = sum(v[1] for v in medidas.values() if v[2] == "supabase" and v[3])
router_t = medidas.get("clasificar_contexto [LLM #1]", (0, 0))[1]

print("-" * 72)
print(f"{'LLM (2 llamadas, hoy en serie)':<32} {llm_t:6.2f}s")
print(f"{'Supabase (consultas en serie)':<32} {sb_t:6.2f}s")
print(f"{'TOTAL como está hoy (todo en serie)':<32} {llm_t + sb_t:6.2f}s")

# Qué se ganaría paralelizando lo que NO depende del router.
paralelo = max(router_t, sb_indep) + sb_dep + (llm_t - router_t)
print(f"\n{'Si se paralelizara lo independiente':<32} {paralelo:6.2f}s"
      f"   (ahorro ~{(llm_t + sb_t) - paralelo:.1f}s)")
print("  (el router y las consultas que no dependen de él pueden correr a la vez;")
print("   las marcadas como dependientes tienen que esperar su resultado)")
