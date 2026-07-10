"""
Corre las mismas conversaciones REALES (conversaciones_emparejadas.csv) contra
varios modelos vía OpenRouter, reusando el prompt real (construir_prompt) y el
parseo/validación de JSON real (LLMClient) — para comparar el modelo de
producción (Llama 70B en Groq) contra GPT-5.6, Gemini, Grok, Claude, etc.

Requiere OPENROUTER_API_KEY en .env.

Uso:
    source venv/bin/activate

    # 20 mensajes fijos (reproducible) contra dos modelos de OpenRouter:
    python eval_multimodelo.py 20 fijo openai/gpt-5.6-sol,google/gemini-3.1-pro-preview

    # lo mismo + el modelo de producción (Groq) como baseline en la misma corrida:
    python eval_multimodelo.py 20 fijo --incluir-groq openai/gpt-5.6-sol

    # 8 mensajes al azar:
    python eval_multimodelo.py 8 azar openai/gpt-5.6-terra,x-ai/grok-4.5

Los model id son los de https://openrouter.ai/models (columna "by <proveedor>").
Guarda todas las respuestas en eval_multimodelo_resultados.csv para comparar
mensaje por mensaje (incluye la respuesta real de Numa ya grabada en el CSV
fuente, vía conversaciones_emparejadas.csv, para referencia).

Nota de costo: los modelos "Pro"/flagship (GPT-5.6 Sol, Claude Fable) son
sensiblemente más caros por token de output. Arrancá con n chico (15-20) antes
de correr contra las 421 conversaciones completas.
"""
import csv
import random
import sys

from app.core.config import config
from app.core.llm import get_client
from app.llm_client import LLMClient, _FALLBACK_RESPONSE
from app.numa_prompt import construir_prompt
from test_modelo import _TUTEO, _cargar_mensajes, _eco

# LLMClient absorbe errores de la API (402 sin crédito, 5xx, rate limit, etc.)
# y devuelve este texto de cortesía en vez de levantar excepción — así el chat
# real nunca se rompe. Para el eval eso es un falso "✅ pasó" si no lo
# detectamos explícitamente: hay que distinguir "no tuteó/no hizo eco" de
# "nunca llegó a responder".
_FALLBACK_TEXT = _FALLBACK_RESPONSE["message"]

RESULTADOS_CSV = "eval_multimodelo_resultados.csv"


def _entradas_a_evaluar(modelos_openrouter: list[str], incluir_groq: bool):
    """Devuelve [(etiqueta, LLMClient, kwargs_extra_para_generate_response), ...]."""
    if not config.OPENROUTER_API_KEY:
        sys.exit("Falta OPENROUTER_API_KEY en .env")
    entradas = []
    if incluir_groq:
        # Baseline Groq explícito (LLMClient() sin args ya no es "solo Groq":
        # ahora son los targets de producción, OpenRouter primario incluido).
        entradas.append((
            f"groq:{config.GROQ_MODEL}",
            LLMClient(client=get_client("groq"), model=config.GROQ_MODEL),
            {},
        ))
    for modelo in modelos_openrouter:
        cliente = LLMClient(client=get_client("openrouter"), model=modelo)
        entradas.append((
            f"openrouter:{modelo}",
            cliente,
            {
                # Headroom generoso: algunos modelos (Grok 4.5, Claude Fable)
                # tienen razonamiento OBLIGATORIO — rechazan con 400 si se manda
                # reasoning.enabled=false, así que no lo apagamos, solo le bajamos
                # el esfuerzo. El reasoning cuenta contra max_tokens, por eso el
                # headroom grande (mismo problema que gpt-oss/qwen en Groq, ver
                # app/core/llm.py, pero acá no sabemos cuánto gasta cada modelo).
                "max_tokens_base": 1600,
                "extra_body": {"reasoning": {"effort": "low"}},
            },
        ))
    return entradas


def _evaluar(etiqueta: str, cliente: LLMClient, kwargs_extra: dict, mensajes: list[str]) -> tuple[dict, list[dict]]:
    print(f"\n{'=' * 70}\n🤖 {etiqueta}\n{'=' * 70}")
    fallas = {"tuteo": 0, "eco": 0, "comillas": 0, "vacio_o_error": 0}
    filas = []

    for i, msg in enumerate(mensajes, 1):
        system_prompt = construir_prompt(ultimo_mensaje=msg)
        conversation = [{"role": "user", "content": msg}]
        try:
            resp = cliente.generate_response(conversation, system_prompt, **kwargs_extra)
            texto = resp["message"]
            mood = resp["mood"]
        except Exception as e:
            print(f"\n[{i}] 👤 {msg}\n    ⚠️ ERROR: {e}")
            fallas["vacio_o_error"] += 1
            filas.append({"modelo": etiqueta, "mensaje": msg, "respuesta": "", "mood": "", "flags": "ERROR: " + str(e)})
            continue

        hay_fallback = texto.strip() == _FALLBACK_TEXT
        hay_tuteo = bool(_TUTEO.search(texto)) and not hay_fallback
        hay_eco = _eco(msg, texto) and not hay_fallback
        hay_comillas = ('"' in texto or "“" in texto or "”" in texto) and not hay_fallback
        hay_vacio = not texto.strip() or hay_fallback
        if hay_tuteo:
            fallas["tuteo"] += 1
        if hay_eco:
            fallas["eco"] += 1
        if hay_comillas:
            fallas["comillas"] += 1
        if hay_vacio:
            fallas["vacio_o_error"] += 1

        flags = []
        if hay_fallback:
            flags.append("FALLBACK(no respondió el modelo — ver log de errores)")
        if hay_tuteo:
            flags.append("TUTEO")
        if hay_eco:
            flags.append("ECO")
        if hay_comillas:
            flags.append("COMILLAS")
        if hay_vacio and not hay_fallback:
            flags.append("VACIO")
        marca = "  ⚠️ " + " ".join(flags) if flags else "  ✅"

        print(f"\n[{i}] 👤 {msg}")
        print(f"    🐻 {texto}")
        print(f"    🎭 mood={mood}{marca}")

        filas.append({
            "modelo": etiqueta,
            "mensaje": msg,
            "respuesta": texto,
            "mood": mood,
            "flags": ",".join(flags),
        })

    total = len(mensajes)
    print(f"\nRESUMEN {etiqueta}:")
    print(f"  Tuteo / fuera de registro : {fallas['tuteo']}/{total}")
    print(f"  Eco (recita al usuario)   : {fallas['eco']}/{total}")
    print(f"  Comillas en la respuesta  : {fallas['comillas']}/{total}")
    print(f"  Vacío / error             : {fallas['vacio_o_error']}/{total}")

    return fallas, filas


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)

    n = int(sys.argv[1])
    fijo = sys.argv[2] == "fijo"
    resto = sys.argv[3:]

    incluir_groq = "--incluir-groq" in resto
    resto = [a for a in resto if a != "--incluir-groq"]
    if not resto:
        sys.exit(
            "Falta la lista de modelos de OpenRouter (separados por coma). "
            "Ej: openai/gpt-5.6-sol,google/gemini-3.1-pro-preview"
        )
    modelos_openrouter = [m.strip() for m in resto[0].split(",") if m.strip()]

    mensajes_todos = _cargar_mensajes()
    seleccion = mensajes_todos[:n] if fijo else random.sample(mensajes_todos, min(n, len(mensajes_todos)))

    entradas = _entradas_a_evaluar(modelos_openrouter, incluir_groq)

    resumen_general = {}
    filas_totales = []
    for etiqueta, cliente, kwargs_extra in entradas:
        fallas, filas = _evaluar(etiqueta, cliente, kwargs_extra, seleccion)
        resumen_general[etiqueta] = fallas
        filas_totales.extend(filas)

    with open(RESULTADOS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["modelo", "mensaje", "respuesta", "mood", "flags"])
        w.writeheader()
        w.writerows(filas_totales)

    print(f"\n{'=' * 70}\nCOMPARATIVA ({len(seleccion)} mensajes){'=' * 70}")
    for etiqueta, fallas in resumen_general.items():
        print(f"  {etiqueta}: tuteo={fallas['tuteo']} eco={fallas['eco']} comillas={fallas['comillas']} vacio/error={fallas['vacio_o_error']}")
    print(f"\n📄 Respuestas completas guardadas en {RESULTADOS_CSV}")


if __name__ == "__main__":
    main()
