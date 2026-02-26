from typing import List, Literal, TypedDict
from app.llm_client import LLMClient, ChatMessage, Mood

SuggestedAction = Literal[
    "respiracion_box",
    "respiracion_478",
    "respiracion_balance",
    "meditacion_bodyscan",
    "meditacion_mindfulness",
    "yoga_cuello",
    "yoga_ansiedad",
    "lectura",
    "none"
]
RiskLevel = Literal["none", "low", "high"]


class ChatResponse(TypedDict):
    message: str
    mood: Mood
    suggested_action: SuggestedAction
    risk_level: RiskLevel


# Mapeo de mood → ejercicio más adecuado según evidencia
MOOD_TO_ACTION: dict[str, SuggestedAction] = {
    "stressed":    "respiracion_box",       # Calmante rápido, usado en contextos de alta presión
    "overwhelmed": "respiracion_balance",   # Equilibra el sistema nervioso de forma gradual
    "anxious":     "yoga_ansiedad",         # Grounding físico para ansiedad
    "sad":         "meditacion_bodyscan",   # Reconecta con el cuerpo, suave para tristeza
    "happy":       "none",
    "excited":     "none",
    "calm":        "none",
    "neutral":     "none",
}

# Frases de riesgo expandidas
HIGH_RISK_PHRASES = [
    "no quiero seguir",
    "no vale la pena",
    "me quiero morir",
    "no aguanto más",
    "quiero desaparecer",
    "ya no puedo más",
    "no tiene sentido seguir",
    "quiero terminar con todo",
    "no quiero estar acá",
    "mejor si no existiera",
]

LOW_RISK_PHRASES = [
    "me siento muy mal",
    "estoy destruido",
    "no sé cuánto más aguanto",
    "todo está mal",
    "estoy al límite",
]


class ChatService:
    def __init__(self):
        self.llm = LLMClient()

    def handle_message(
        self,
        conversation: List[ChatMessage],
    ) -> ChatResponse:
        llm_response = self.llm.generate_response(conversation)

        mood = llm_response["mood"]

        # Usar ejercicio sugerido por el LLM si existe, sino derivar del mood
        suggested_action: SuggestedAction = (
            llm_response.get("suggested_action")
            or MOOD_TO_ACTION.get(mood, "none")
        )

        risk_level: RiskLevel = self._detect_risk(conversation)

        return {
            "message": llm_response["message"],
            "mood": mood,
            "suggested_action": suggested_action,
            "risk_level": risk_level,
        }

    def _detect_risk(self, conversation: List[ChatMessage]) -> RiskLevel:
        last_user_message = conversation[-1]["content"].lower()

        for phrase in HIGH_RISK_PHRASES:
            if phrase in last_user_message:
                return "high"

        for phrase in LOW_RISK_PHRASES:
            if phrase in last_user_message:
                return "low"

        return "none"