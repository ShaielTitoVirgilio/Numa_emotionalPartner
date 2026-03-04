# app/llm_client.py

from dotenv import load_dotenv
import os
import re
import json
from typing import List, Literal, TypedDict, Optional
from openai import OpenAI

load_dotenv()

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
        load_dotenv()
        self.client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        )

    def generate_response(
        self,
        conversation: List[ChatMessage],
        system_prompt: str,       # ← recibe el prompt dinámico armado por construir_prompt()
    ) -> LLMRawResponse:

        completion = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=400,
            messages=[
                {"role": "system", "content": system_prompt},
                *conversation,
            ],
        )

        raw = completion.choices[0].message.content
        if not raw:
            raise RuntimeError("Empty response from LLM")

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

        if "message" not in parsed or "mood" not in parsed:
            raise RuntimeError(f"Malformed LLM response: {parsed}")

        valid_moods = {"neutral", "calm", "happy", "excited", "stressed", "overwhelmed", "sad", "anxious"}
        if parsed.get("mood") not in valid_moods:
            parsed["mood"] = "neutral"

        return {
            "message": parsed["message"],
            "mood": parsed["mood"],
            "suggested_action": parsed.get("suggested_action"),
            "memory": parsed.get("memory"),   # None si no hay nada para recordar
        }