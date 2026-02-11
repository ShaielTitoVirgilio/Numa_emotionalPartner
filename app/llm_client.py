from dotenv import load_dotenv
import os

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
            model="llama-3.1-8b-instant",
            temperature=0.7,
            messages=[
                {"role": "system", "content": NUMA_PROMPT},
                *conversation,
            ],
        )

        raw = completion.choices[0].message.content
        if not raw:
            raise RuntimeError("Empty response from LLM")

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Si el modelo devolvió texto plano, lo envolvemos nosotros
            parsed = {
                "message": raw.strip(),
                "mood": "neutral",
                "suggested_action": None,
                "risk_level": 0,
            }


        if "message" not in parsed or "mood" not in parsed:
            raise RuntimeError(f"Malformed LLM response: {parsed}")

        return {
            "message": parsed["message"],
            "mood": parsed["mood"],
        }
