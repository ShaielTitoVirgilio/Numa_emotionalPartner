from groq import Groq
from typing import List, Dict
from app.llm.client import LLMClient
from app.config.settings import GROQ_API_KEY

class GroqClient(LLMClient):

    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)

    def chat(self, messages: List[Dict[str, str]]) -> str:
        completion = self.client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.7,
            max_tokens=120,
        )

        return completion.choices[0].message.content.strip()
