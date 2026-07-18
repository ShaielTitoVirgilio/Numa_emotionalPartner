"""Test LIMPIO y aislado: ¿un request nuevo pega el cache del prefijo CORE que
calentó OTRO request con distinta cola? ¿Hace falta prompt_cache_key?

Diseño: system prompt FIJO (~9k tok, el prefijo compartido). Dos llamadas que
solo difieren en el user message (la cola). Uso un nonce único por trial para
que la cola sea NUEVA (sin contaminar de runs previos). El system prompt es el
mismo → si el cache de prefijo anda, la 2ª llamada debe cachear ~todo el system.

Trial 1: SIN prompt_cache_key.   Trial 2: CON prompt_cache_key.
Si solo el Trial 2 cachea → la clave es obligatoria en producción."""
import os, time, uuid
from dotenv import load_dotenv
from datetime import date
from openai import OpenAI
load_dotenv()
import app.numa_prompt as N

SYSTEM = N.construir_prompt(
    perfil={"nombre": "Sofia", "edad": 28},
    memorias=[{"content": "Vive sola desde marzo", "category": "emocional", "priority": 4}],
    num_interacciones=3, checkin_hoy=2, crisis_score=0.0,
    historial_reciente=[{"role": "user", "content": "hola"}],
    mood_actual="sad", ultimo_mensaje="hola", hoy=date.today(),
    router_hints={"ok": True, "estado_emocional": "triste_vacio", "senal_riesgo": "none"},
)
client = OpenAI(api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1")
MODEL = os.getenv("CHAT_MODEL", "openai/gpt-5.6-luna")

def call(user, cache_key=None):
    eb = {"reasoning": {"effort": "low"}, "usage": {"include": True}}
    if cache_key:
        eb["prompt_cache_key"] = cache_key
    r = client.chat.completions.create(
        model=MODEL, temperature=0.7, max_tokens=120,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        extra_body=eb,
    )
    u = r.usage
    det = getattr(u, "prompt_tokens_details", None)
    return u.prompt_tokens, (getattr(det, "cached_tokens", 0) if det else 0) or 0

def trial(nombre, key):
    n = uuid.uuid4().hex[:8]  # cola NUEVA, nunca enviada
    pW, cW = call(f"warmup {n}: contame algo", key)
    time.sleep(2)
    pT, cT = call(f"test {n}: y ahora otra cosa distinta", key)
    print(f"\n{nombre} (key={key!r}):")
    print(f"  warmup: prompt={pW} cached={cW}")
    print(f"  test:   prompt={pT} cached={cT}  → {cT/max(pT,1)*100:.0f}% del input")
    return cT

print(f"MODEL={MODEL}  system≈{len(SYSTEM)//4} tok  (prefijo compartido)")
c1 = trial("TRIAL 1 — SIN key", None)
time.sleep(3)
c2 = trial("TRIAL 2 — CON key", "numa-core-v1")

print("\n── VEREDICTO ──")
print(f"  sin key: test cacheó {c1} tok | con key: test cacheó {c2} tok")
if c2 >= 6000 and c1 < 2000:
    print("  → prompt_cache_key es NECESARIO: sin él no cachea entre requests distintos.")
elif c1 >= 6000 and c2 >= 6000:
    print("  → cachea con y sin key (el ruteo ya mantiene afinidad).")
elif c1 < 2000 and c2 < 2000:
    print("  → NO cachea ni con key: el prefijo parcial no se aprovecha por esta vía.")
else:
    print("  → resultado mixto, ver números arriba.")
