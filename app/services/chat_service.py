from typing import List, Dict
from app.llm.client import LLMClient
from app.prompts.numa_prompt import NUMA_PROMPT

class ChatService:

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def chat(self, user_text: str, history: List[Dict[str, str]] = None) -> str:
        messages = [
            {"role": "system", "content": NUMA_PROMPT}
        ]

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": user_text})

        response = self.llm.chat(messages)

        return response or "Estoy acá contigo."
