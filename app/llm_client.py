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

class MemoryItem(TypedDict):
    content: str
    category: str
    priority: int

class LLMRawResponse(TypedDict):
    message: str
    mood: Mood
    suggested_action: Optional[str]
    memories: List[MemoryItem]


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
            response_format={"type": "json_object"},  # Capa 1: fuerza JSON válido a nivel API
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
                "memories": [],
            }

        # ─────────────────────────────────────────────────────────────
        # VALIDACIONES
        # ─────────────────────────────────────────────────────────────
        valid_moods = {"neutral", "calm", "happy", "excited", "stressed", "overwhelmed", "sad", "anxious"}
        if parsed.get("mood") not in valid_moods:
            parsed["mood"] = "neutral"

        message_clean = re.sub(r'\[EJERCICIO:\s*\w+\]', '', str(parsed.get("message", ""))).strip()
        # Capa 3: eliminar cualquier residuo del formato JSON pegado al final del mensaje
        # 1) bloques markdown tipo ```json o ``` que el modelo a veces agrega
        message_clean = re.sub(r'\s*```[\s\S]*$', '', message_clean).strip()
        # 2) JSON crudo (sin requerir whitespace antes del '{', cubre casos como "Hola.{...")
        message_clean = re.sub(r'\{[\s\S]*$', '', message_clean).strip()

        valid_categories = {"trabajo", "estudios", "relaciones", "salud", "identidad", "emocional", "hobbies", "vida_cotidiana", "otro"}

        # Normalizar memorias: acepta nuevo formato (array "memories") y viejo (campos sueltos)
        raw_memories = parsed.get("memories")
        if isinstance(raw_memories, list):
            memories = []
            for m in raw_memories[:2]:  # máx 2
                if not isinstance(m, dict):
                    continue
                content = str(m.get("content") or "").strip()
                if not content:
                    continue
                cat = m.get("category")
                cat = cat if cat in valid_categories else "otro"
                try:
                    prio = max(1, min(5, int(m.get("priority") or 3)))
                except (TypeError, ValueError):
                    prio = 3
                memories.append({"content": content, "category": cat, "priority": prio})
        else:
            # Fallback: formato viejo con campos sueltos
            old_content = str(parsed.get("memory") or "").strip()
            if old_content:
                raw_cat = parsed.get("memory_category")
                cat = raw_cat if raw_cat in valid_categories else "otro"
                memories = [{"content": old_content, "category": cat, "priority": 3}]
            else:
                memories = []

        return {
            "message":          message_clean,
            "mood":             parsed["mood"],
            "suggested_action": parsed.get("suggested_action"),
            "memories":         memories,
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