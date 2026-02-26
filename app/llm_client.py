from dotenv import load_dotenv
import os
import re

load_dotenv()
import json
from typing import List, Literal, TypedDict
from openai import OpenAI
from app.numa_prompt import NUMA_PROMPT

Mood = Literal[
    "neutral",
    "calm",
    "happy",
    "excited",
    "stressed",
    "overwhelmed",
    "sad",
    "anxious",
]

class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str

class LLMRawResponse(TypedDict):
    message: str
    mood: Mood


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
    ) -> LLMRawResponse:
        completion = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=300,
            messages=[
                {"role": "system", "content": NUMA_PROMPT},
                *conversation,
            ],
        )

        raw = completion.choices[0].message.content
        if not raw:
            raise RuntimeError("Empty response from LLM")

        # Extraer el bloque JSON aunque el modelo agregue texto antes o después
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            raw_json = json_match.group(0)
        else:
            raw_json = raw.strip()

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            parsed = {
                "message": raw.strip(),
                "mood": "neutral",
                "suggested_action": None,
            }

        if "message" not in parsed or "mood" not in parsed:
            raise RuntimeError(f"Malformed LLM response: {parsed}")

        # Validar que el mood sea uno de los permitidos
        valid_moods = {"neutral", "calm", "happy", "excited", "stressed", "overwhelmed", "sad", "anxious"}
        if parsed["mood"] not in valid_moods:
            parsed["mood"] = "neutral"

        return {
            "message": parsed["message"],
            "mood": parsed["mood"],
            "suggested_action": parsed.get("suggested_action"),
        }