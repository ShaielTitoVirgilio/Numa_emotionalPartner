# app/llm_client.py

from dotenv import load_dotenv
import os
import re
import json
from typing import List, Literal, TypedDict, Optional
from openai import OpenAI

load_dotenv()

_openai_shared_client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

Mood = Literal[
    "neutral", "calm", "happy", "excited",
    "stressed", "overwhelmed", "sad", "anxious",
]

class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str

class LLMRawResponse(TypedDict):
    message: str
    mood: Mood
    suggested_action: Optional[str]
    memory: Optional[str]
    memory_category: Optional[str]


class LLMClient:
    def __init__(self):
        self.client = _openai_shared_client

    def generate_response(
        self,
        conversation: List[ChatMessage],
        system_prompt: str,
    ) -> LLMRawResponse:

        completion = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=600,  # subido de 400 para que el JSON no se corte
            messages=[
                {"role": "system", "content": system_prompt},
                *conversation,
            ],
        )

        raw = completion.choices[0].message.content or ""

        # ─────────────────────────────────────────────────────────────
        # PASO 1: intentar parsear el raw completo como JSON puro
        # ─────────────────────────────────────────────────────────────
        parsed = None

        try:
            parsed = json.loads(raw.strip())
        except json.JSONDecodeError:
            pass

        # ─────────────────────────────────────────────────────────────
        # PASO 2: buscar el último { en el texto y parsear desde ahí
        # Usamos rfind para encontrar el bloque JSON aunque haya texto
        # libre antes. Si el JSON está truncado, intentamos repararlo.
        # ─────────────────────────────────────────────────────────────
        if parsed is None:
            last_brace = raw.rfind("{")
            if last_brace != -1:
                json_candidate = raw[last_brace:]
                json_candidate = _reparar_json_truncado(json_candidate)
                try:
                    candidate = json.loads(json_candidate)
                    if "message" in candidate and "mood" in candidate:
                        parsed = candidate
                except json.JSONDecodeError:
                    pass

        # ─────────────────────────────────────────────────────────────
        # PASO 3: fallback total
        # El texto antes del primer { es la respuesta real del modelo
        # ─────────────────────────────────────────────────────────────
        if parsed is None:
            pre_json = raw.split("{")[0].strip()
            parsed = {
                "message": pre_json if pre_json else raw.strip(),
                "mood": "neutral",
                "suggested_action": None,
                "memory": None,
            }

        # ─────────────────────────────────────────────────────────────
        # VALIDACIONES
        # ─────────────────────────────────────────────────────────────
        valid_moods = {"neutral", "calm", "happy", "excited", "stressed", "overwhelmed", "sad", "anxious"}
        if parsed.get("mood") not in valid_moods:
            parsed["mood"] = "neutral"

        message_clean = re.sub(r'\[EJERCICIO:\s*\w+\]', '', str(parsed.get("message", ""))).strip()
        # Eliminar cualquier JSON residual pegado al final del mensaje
        message_clean = re.sub(r'\s*\{[\s\S]*', '', message_clean).strip()

        valid_categories = {"trabajo", "relaciones", "salud", "identidad", "emocional", "otro"}
        raw_category = parsed.get("memory_category")
        memory_category = raw_category if raw_category in valid_categories else "otro" if raw_category else None

        return {
            "message": message_clean,
            "mood": parsed["mood"],
            "suggested_action": parsed.get("suggested_action"),
            "memory": parsed.get("memory"),
            "memory_category": memory_category,
        }


def _reparar_json_truncado(texto: str) -> str:
    """
    Cierra un JSON que fue cortado por el límite de tokens.
    Cuenta comillas y llaves abiertas y las cierra.
    """
    try:
        json.loads(texto)
        return texto  # ya es válido
    except json.JSONDecodeError:
        pass

    reparado = texto.rstrip()

    # Detectar si hay un string abierto (comillas impares no escapadas)
    in_string = False
    escaped = False
    for ch in reparado:
        if escaped:
            escaped = False
            continue
        if ch == '\\':
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string

    if in_string:
        reparado += '"'

    # Cerrar llaves pendientes
    open_braces = reparado.count("{") - reparado.count("}")
    if open_braces > 0:
        reparado += "}" * open_braces

    return reparado