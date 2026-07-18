"""Verifica el nuevo M25: (1) ante contexto que amerita, Numa OFRECE preguntando
y NO manda suggested_action todavía; (2) cuando el usuario acepta, ahí sí lo setea."""
from datetime import date
from app.llm_client import LLMClient
from app.numa_prompt import construir_prompt

llm = LLMClient()  # targets de producción (Luna primario)

def correr(nombre, conv):
    sp = construir_prompt(
        num_interacciones=len(conv), historial_reciente=conv,
        ultimo_mensaje=conv[-1]["content"], hoy=date.today(), mood_actual="stressed",
        router_hints={"ok": True, "estado_emocional": "ansioso", "senal_riesgo": "none",
                      "pide_ejercicio": True, "pregunta_app": False, "pregunta_capacidades": False},
    )
    r = llm.generate_response(conv, sp)
    print(f"\n── {nombre} ──")
    print(f"  🐻 {r['message']}")
    print(f"  suggested_action = {r['suggested_action']!r}")
    return r

# Escenario 1: contexto que amerita (tensa, durmió mal), NO pide ejercicio explícito
conv1 = [
    {"role": "user", "content": "hola, vengo medio quemado"},
    {"role": "assistant", "content": "Hola. ¿Qué te tiene así?"},
    {"role": "user", "content": "el laburo, no paro y encima duermo mal hace días"},
    {"role": "assistant", "content": "Se nota que venís arrastrando cansancio de varios frentes."},
    {"role": "user", "content": "si, estoy con el cuerpo tenso todo el tiempo"},
]
r1 = correr("ESC 1 — contexto amerita (esperado: OFRECE preguntando, suggested_action=None)", conv1)

# Escenario 2: Numa ofreció, el usuario acepta
conv2 = conv1 + [
    {"role": "assistant", "content": "¿Querés que probemos una respiración para soltar un poco esa tensión?"},
    {"role": "user", "content": "dale, probemos"},
]
r2 = correr("ESC 2 — el usuario acepta (esperado: suggested_action = un ejercicio válido)", conv2)

print("\n── CHEQUEO ──")
ok1 = r1["suggested_action"] is None and "?" in r1["message"]
ok2 = bool(r2["suggested_action"])
print(f"  ESC1 ofrece sin mandar (pregunta + sin suggested_action): {'✅' if ok1 else '⚠️'}")
print(f"  ESC2 setea suggested_action al aceptar: {'✅' if ok2 else '⚠️'}")
