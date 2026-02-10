from typing import List, Dict
from app.llm.client import LLMClient
from app.prompts.numa_prompt import NUMA_PROMPT
from app.services.mood_service import infer_mood
from app.services.suggestion_service import get_suggestions


class ChatService:

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

def chat(self, user_text: str, history=None) -> dict:
    mood = infer_mood(user_text)
    suggestions = get_suggestions(mood)

    messages = [
        {
            "role": "system",
            "content": f"{NUMA_PROMPT}\n\nEstado general del usuario: {mood}"
        }
    ]

    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": user_text})

    response_text = self.llm.chat(messages)

    return {
        "text": response_text or "Estoy acá contigo.",
        "mood": mood,
        "suggestions": suggestions
    }
