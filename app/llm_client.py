"""
🤖 LLM Client - Solo habla con Groq
No piensa, no decide, solo ejecuta llamadas a la API
"""
from groq import Groq
from typing import List, Dict, Optional
import os

class LLMClient:
    def __init__(self, api_key: str):
        """Inicializa el cliente de Groq"""
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.1-8b-instant"
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 150
    ) -> str:
        """
        Llama a Groq y devuelve la respuesta
        
        Args:
            messages: Lista de mensajes en formato [{"role": "user/assistant/system", "content": "..."}]
            temperature: Creatividad del modelo (0.0 - 1.0)
            max_tokens: Máximo de tokens en la respuesta
            
        Returns:
            str: Respuesta del modelo
        """
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            respuesta = completion.choices[0].message.content
            
            # Fallback si no hay respuesta
            if not respuesta:
                return "Estoy acá contigo."
            
            return respuesta.strip()
            
        except Exception as e:
            print(f"❌ Error en LLM: {e}")
            return "Perdón, tuve un problema. ¿Podés intentar de nuevo?"