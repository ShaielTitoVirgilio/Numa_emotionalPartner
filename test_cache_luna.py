"""Prueba empírica: ¿el prompt caching de OpenRouter dispara para gpt-5.6-luna?
Hace 2 llamadas IDÉNTICAS seguidas y compara los tokens cacheados que reporta
la API. No imprime la API key. Se puede borrar después."""
import os, time, json
from dotenv import load_dotenv
from datetime import date
from openai import OpenAI

load_dotenv()
import app.numa_prompt as N

# ── Prompt realista (~9k tok), mismo armado que producción ──
perfil = {"nombre": "Sofia", "edad": 28, "ocupacion": "estudiante de enfermeria", "genero": "femenino"}
memorias = [
    {"content": "Está estudiando enfermería y le cuesta el último año", "category": "estudios", "priority": 3},
    {"content": "Se peleó con su hermana Caro por temas de la casa", "category": "relaciones", "priority": 3},
    {"content": "Correr a la mañana la ayuda a despejarse", "category": "salud", "priority": 2, "helped_before": True},
    {"content": "Vive sola desde marzo y a veces se siente aislada", "category": "emocional", "priority": 4},
    {"content": "Su mamá vive en Rosario y hablan poco", "category": "relaciones", "priority": 3},
]
patrones = [{"topic": "estudios", "count": 5}, {"topic": "relaciones", "count": 3}]
conv = [
    {"role": "user", "content": "hola, no venia muy bien esta semana"},
    {"role": "assistant", "content": "Hola Sofi. ¿Qué fue lo que se te hizo cuesta arriba?"},
    {"role": "user", "content": "no se, me siento medio vacia, como sin ganas de nada"},
]
system_prompt = N.construir_prompt(
    perfil=perfil, memorias=memorias, patrones=patrones,
    num_interacciones=len(conv), es_inicio_sesion=False, checkin_hoy=2,
    crisis_score=0.0, ultimo_modulo_critico=False, historial_reciente=conv,
    mood_actual="sad", ultimo_mensaje=conv[-1]["content"], preguntas_seguidas=0,
    hoy=date.today(),
    router_hints={"ok": True, "estado_emocional": "triste_vacio", "senal_riesgo": "none",
                  "pide_ejercicio": False, "pregunta_app": False, "pregunta_capacidades": False},
)

client = OpenAI(api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1")
MODEL = os.getenv("CHAT_MODEL", "openai/gpt-5.6-luna")
messages = [{"role": "system", "content": system_prompt}, *conv]

def llamar(n):
    r = client.chat.completions.create(
        model=MODEL, temperature=0.7, max_tokens=400,
        response_format={"type": "json_object"},
        messages=messages,
        extra_body={"reasoning": {"effort": "low"}, "usage": {"include": True}},
    )
    u = r.usage
    det = getattr(u, "prompt_tokens_details", None)
    cached = getattr(det, "cached_tokens", None) if det else None
    # OpenRouter a veces expone el ahorro como cache_discount en el dict crudo
    raw = r.model_dump()
    disc = raw.get("usage", {}).get("cache_discount")
    print(f"  [call {n}] prompt_tokens={u.prompt_tokens}  cached_tokens={cached}  "
          f"completion={u.completion_tokens}  cache_discount={disc}")
    return u.prompt_tokens, cached

print(f"MODEL={MODEL}  system≈{len(system_prompt)//4} tok")
p1, c1 = llamar(1)
time.sleep(2)   # seguidas, dentro de la ventana tibia
p2, c2 = llamar(2)

print("\n── RESULTADO ──")
if c2 and c2 > (c1 or 0):
    print(f"✅ CACHE DISPARA: call 2 cacheó {c2} tok (~{c2/max(p2,1)*100:.0f}% del input).")
elif c1 or c2:
    print(f"↔️  Cache reportado pero sin salto claro (c1={c1}, c2={c2}).")
else:
    print("❌ La API no reportó cached_tokens (o el modelo/ruta no lo expone así).")
