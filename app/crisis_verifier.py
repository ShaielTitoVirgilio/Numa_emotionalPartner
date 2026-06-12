# app/crisis_verifier.py
"""
Verificador de crisis en dos pasos (capa 2).

El detector por keywords (capa 1) ya filtra hipérboles, negaciones y tercera
persona, pero ninguna lista cubre todo el lenguaje natural. Antes de devolver
la respuesta hardcodeada de emergencia, este módulo pasa el mensaje por un
clasificador LLM rápido que responde una sola cosa: ¿la persona está
expresando riesgo REAL y ACTUAL sobre sí misma?

FAIL-SAFE POR DISEÑO: ante cualquier error, timeout, respuesta ambigua o
falta de API key, se asume riesgo real y se mantiene la respuesta de
emergencia. El verificador solo puede REDUCIR falsos positivos, nunca
silenciar una crisis verdadera.
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

# El 8B era demasiado conservador (decía "riesgo real" a todo y no filtraba
# nada); el 70B discrimina bien y en Groq sigue siendo rápido para ~30 tokens.
_VERIFIER_MODEL = "llama-3.3-70b-versatile"
_TIMEOUT_SECONDS = 5

_PROMPT = """Sos un clasificador de seguridad para una app de apoyo emocional en español rioplatense.

Te paso el último mensaje de un usuario que activó una alerta de riesgo por palabras clave de la categoría {categoria}.

Primero clasificá el mensaje en UNO de estos tipos:
- "actual": la persona expresa riesgo real y presente sobre SÍ MISMA (ideación suicida, búsqueda de método, autolesión). Incluye ambigüedad seria.
- "hiperbole": exageración o chiste cotidiano ("me quiero matar, qué papelón", "me muero de vergüenza").
- "tercero": habla del riesgo de OTRA persona, no del suyo.
- "pasado": algo que sintió o intentó en el pasado y narra con distancia.
- "ficcion": tarea, cuento, película, letra de canción, pregunta informativa/académica.

Después derivá riesgo_real: true solo si el tipo es "actual".
ANTE LA DUDA entre "actual" y cualquier otro tipo, elegí "actual". Es preferible un falso positivo a ignorar una crisis.

Mensaje del usuario:
\"\"\"{mensaje}\"\"\"

Respondé SOLO con JSON: {{"tipo": "...", "riesgo_real": true/false}}"""


def confirmar_riesgo_real(mensaje: str, categoria: str) -> bool:
    """True si la respuesta de emergencia hardcodeada debe mantenerse.

    Devuelve False solo cuando el clasificador afirma con claridad que NO hay
    riesgo real; en ese caso el mensaje sigue al LLM principal con los módulos
    de crisis activados (no se ignora: se acompaña con cuidado y se loguea).
    """
    try:
        resp = _client.chat.completions.create(
            model=_VERIFIER_MODEL,
            temperature=0.0,
            max_tokens=40,
            timeout=_TIMEOUT_SECONDS,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": _PROMPT.format(categoria=categoria, mensaje=mensaje[:1000]),
            }],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        valor = data.get("riesgo_real")
        if valor is False:
            return False
        return True  # true, ausente o tipo raro → riesgo real
    except Exception as e:
        print(f"⚠️ Crisis verifier no disponible (se asume riesgo real): {e}")
        return True
