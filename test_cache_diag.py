"""Diagnóstico final: 5 llamadas seguidas, MISMO system prompt (~9k tok),
DISTINTO user cada vez (nonce). ¿En algún momento empieza a cachear el prefijo?
Además imprime el bloque usage CRUDO para ver todos los campos de cache que
reporta OpenRouter (cached_tokens, cache_discount, cost, etc.)."""
import os, time, uuid, json
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
print(f"MODEL={MODEL}  system≈{len(SYSTEM)//4} tok")

for i in range(5):
    r = client.chat.completions.create(
        model=MODEL, temperature=0.7, max_tokens=80,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": f"turno {i} {uuid.uuid4().hex[:6]}: decime algo"}],
        extra_body={"reasoning": {"effort": "low"}, "usage": {"include": True},
                    "prompt_cache_key": "numa-core-v1"},
    )
    raw = r.model_dump()
    usage = raw.get("usage", {})
    print(f"\n[{i}] usage crudo: {json.dumps(usage, ensure_ascii=False)}")
    time.sleep(2)
