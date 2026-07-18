"""Prueba en condición de PRODUCCIÓN: dos turnos DISTINTOS (distinto estado
emocional + distinto mensaje + distintas memorias) que comparten solo el prefijo
CORE. Si el reorder funciona, el 2º turno debe cachear ~el CORE (~7.700 tok),
no el input completo. Prueba que el ahorro es real turno-a-turno, no solo con
prompts idénticos."""
import os, time
from dotenv import load_dotenv
from datetime import date
from openai import OpenAI
load_dotenv()
import app.numa_prompt as N

def prompt_para(estado, msg, mems, mood):
    conv = [{"role": "user", "content": msg}]
    return N.construir_prompt(
        perfil={"nombre": "Sofia", "edad": 28}, memorias=mems,
        num_interacciones=3, checkin_hoy=2, crisis_score=0.0,
        historial_reciente=conv, mood_actual=mood, ultimo_mensaje=msg, hoy=date.today(),
        router_hints={"ok": True, "estado_emocional": estado, "senal_riesgo": "none",
                      "pide_ejercicio": False, "pregunta_app": False, "pregunta_capacidades": False},
    )

# Turno A: triste, memorias X. Turno B: ansioso, memorias Y, otro mensaje.
A = prompt_para("triste_vacio", "me siento vacia, sin ganas de nada",
                [{"content": "Vive sola desde marzo", "category": "emocional", "priority": 4}], "sad")
B = prompt_para("ansioso", "no puedo parar de pensar en el examen, no duermo",
                [{"content": "Rinde farmacologia la semana que viene", "category": "estudios", "priority": 3}], "anxious")

client = OpenAI(api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1")
MODEL = os.getenv("CHAT_MODEL", "openai/gpt-5.6-luna")

def llamar(tag, system, user):
    r = client.chat.completions.create(
        model=MODEL, temperature=0.7, max_tokens=400,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        extra_body={"reasoning": {"effort": "low"}, "usage": {"include": True},
                    "prompt_cache_key": "numa-core-v1"},
    )
    u = r.usage
    det = getattr(u, "prompt_tokens_details", None)
    cached = getattr(det, "cached_tokens", None) if det else 0
    print(f"  [{tag}] prompt_tokens={u.prompt_tokens}  cached_tokens={cached}")
    return u.prompt_tokens, cached or 0

print(f"MODEL={MODEL}")
print("Turno A (triste) — calienta el CORE:")
pA, cA = llamar("A", A, "me siento vacia, sin ganas de nada")
time.sleep(2)
print("Turno B (ansioso, distinto msg/memorias) — comparte solo el CORE:")
pB, cB = llamar("B", B, "no puedo parar de pensar en el examen, no duermo")

print("\n── RESULTADO ──")
print(f"Turno B cacheó {cB} de {pB} tok (~{cB/max(pB,1)*100:.0f}% del input).")
if cB >= 6000:
    print(f"✅ El prefijo CORE cachea con cola dinámica distinta: ahorro real en producción.")
elif cB >= 1024:
    print(f"↔️  Cachea parcial ({cB} tok) — menos de lo esperado, revisar prefijo.")
else:
    print(f"❌ No cacheó el prefijo entre turnos distintos.")
