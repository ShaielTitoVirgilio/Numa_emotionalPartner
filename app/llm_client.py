# app/llm_client.py

from dotenv import load_dotenv
import os
import re
import json
from typing import List, Literal, TypedDict, Optional
from openai import OpenAI

# 1. Cargamos el entorno e instanciamos el cliente de OpenAI UNA SOLA VEZ a nivel de módulo.
# Esto permite que la librería mantenga una "Keep-Alive" connection con los servidores de Groq.
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


class LLMClient:
    def __init__(self):
        # 2. Referenciamos el cliente compartido en lugar de crear uno nuevo.
        self.client = _openai_shared_client

    def generate_response(
        self,
        conversation: List[ChatMessage],
        system_prompt: str,       # ← recibe el prompt dinámico armado por construir_prompt()
    ) -> LLMRawResponse:

        # La llamada ahora reutiliza el pool de conexiones TCP/TLS
        completion = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=250,
            messages=[
                {"role": "system", "content": system_prompt},
                *conversation,
            ],
        )

        raw = completion.choices[0].message.content
        if not raw:
            raise RuntimeError("Empty response from LLM")

        # Intentar extraer JSON si el LLM incluye texto extra
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        raw_json = json_match.group(0) if json_match else raw.strip()

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            parsed = {
                "message": raw.strip(),
                "mood": "neutral",
                "suggested_action": None,
                "memory": None,
            }

        # Validaciones de seguridad
        if "message" not in parsed or "mood" not in parsed:
            # Fallback en caso de que el JSON no tenga los campos mínimos
            parsed = {
                "message": str(parsed.get("message", raw.strip())),
                "mood": parsed.get("mood", "neutral"),
                "suggested_action": parsed.get("suggested_action"),
                "memory": parsed.get("memory")
            }

        valid_moods = {"neutral", "calm", "happy", "excited", "stressed", "overwhelmed", "sad", "anxious"}
        if parsed.get("mood") not in valid_moods:
            parsed["mood"] = "neutral"

        # Limpiar tags internos de la respuesta visual
        message_clean = re.sub(r'\[EJERCICIO:\s*\w+\]', '', parsed["message"]).strip()

        return {
            "message": message_clean,   
            "mood": parsed["mood"],
            "suggested_action": parsed.get("suggested_action"),
            "memory": parsed.get("memory"),
        }