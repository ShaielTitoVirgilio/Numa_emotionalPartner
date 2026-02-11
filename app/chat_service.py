"""
🧠 Chat Service - La capa que piensa
Maneja la lógica de conversación, historial, y análisis emocional
"""
from typing import List, Dict, Optional
from dataclasses import dataclass
from app.llm_client import LLMClient
import re

@dataclass
class ChatResponse:
    """Estructura de respuesta del chat"""
    message: str  # Lo que Numa dice
    mood: Optional[str] = None  # Estado emocional inferido
    suggested_action: Optional[str] = None  # Ejercicio sugerido (si aplica)

class ChatService:
    def __init__(self, llm_client: LLMClient, system_prompt: str):
        """
        Inicializa el servicio de chat
        
        Args:
            llm_client: Cliente LLM para hacer las llamadas
            system_prompt: El prompt de sistema (personalidad de Numa)
        """
        self.llm = llm_client
        self.system_prompt = system_prompt
    
    def chat(
        self,
        user_message: str,
        history: List[Dict[str, str]] = None
    ) -> ChatResponse:
        """
        Procesa un mensaje del usuario y devuelve la respuesta de Numa
        
        Args:
            user_message: El mensaje del usuario
            history: Historial de conversación previo
            
        Returns:
            ChatResponse: Respuesta con mensaje, mood y acción sugerida
        """
        # 1. Construir mensajes para el LLM
        messages = self._build_messages(user_message, history)
        
        # 2. Obtener respuesta del LLM
        llm_response = self.llm.chat_completion(messages)
        
        # 3. Analizar la respuesta
        parsed_response = self._parse_response(llm_response)
        
        # 4. Inferir estado emocional (opcional, para futuro)
        mood = self._infer_mood(user_message)
        
        return ChatResponse(
            message=parsed_response["message"],
            mood=mood,
            suggested_action=parsed_response["exercise"]
        )
    
    def _build_messages(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]]
    ) -> List[Dict[str, str]]:
        """Construye la lista de mensajes para enviar al LLM"""
        messages = [{"role": "system", "content": self.system_prompt}]
        
        # Agregar historial si existe
        if history:
            messages.extend(history)
        
        # Agregar mensaje actual del usuario
        messages.append({"role": "user", "content": user_message})
        
        return messages
    
    def _parse_response(self, llm_response: str) -> Dict[str, Optional[str]]:
        """
        Extrae el mensaje y el ejercicio sugerido (si existe)
        
        El formato esperado es:
        "Mensaje de Numa aquí
        [EJERCICIO: respiracion_box]"
        
        Returns:
            {"message": "...", "exercise": "respiracion_box" o None}
        """
        # Buscar patrón [EJERCICIO: id_ejercicio]
        exercise_pattern = r'\[EJERCICIO:\s*(\w+)\]'
        match = re.search(exercise_pattern, llm_response)
        
        if match:
            exercise_id = match.group(1)
            # Remover la etiqueta del mensaje
            clean_message = re.sub(exercise_pattern, '', llm_response).strip()
            return {
                "message": clean_message,
                "exercise": exercise_id
            }
        
        return {
            "message": llm_response,
            "exercise": None
        }
    
    def _infer_mood(self, user_message: str) -> Optional[str]:
        """
        Infiere el estado emocional basado en keywords
        Esto es SIMPLE por ahora, después podemos mejorarlo
        
        Returns:
            str: 'stressed', 'calm', 'anxious', 'sad', 'neutral', etc.
        """
        message_lower = user_message.lower()
        
        # Keywords emocionales
        stress_keywords = ['estresado', 'agobiado', 'caos', 'abrumado', 'mucho', 'no puedo']
        anxious_keywords = ['ansiedad', 'nervioso', 'preocupado', 'miedo', 'pánico']
        sad_keywords = ['triste', 'solo', 'vacío', 'mal', 'llorar']
        calm_keywords = ['tranquilo', 'calma', 'bien', 'paz', 'relajado']
        
        if any(keyword in message_lower for keyword in stress_keywords):
            return 'stressed'
        elif any(keyword in message_lower for keyword in anxious_keywords):
            return 'anxious'
        elif any(keyword in message_lower for keyword in sad_keywords):
            return 'sad'
        elif any(keyword in message_lower for keyword in calm_keywords):
            return 'calm'
        
        return 'neutral'