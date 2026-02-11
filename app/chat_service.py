from typing import List, Literal, TypedDict
from app.llm_client import LLMClient, ChatMessage, Mood

SuggestedAction = Literal["breathing", "stretch", "focus", "none"]
RiskLevel = Literal["none", "low", "high"]

class ChatResponse(TypedDict):
    message: str
    mood: Mood
    suggested_action: SuggestedAction
    risk_level: RiskLevel


class ChatService:
    def __init__(self):
        self.llm = LLMClient()

    def handle_message(
        self,
        conversation: List[ChatMessage],
    ) -> ChatResponse:
        llm_response = self.llm.generate_response(conversation)

        mood = llm_response["mood"]

        suggested_action: SuggestedAction = "none"
        if mood in ("stressed", "overwhelmed"):
            suggested_action = "breathing"

        risk_level: RiskLevel = self._detect_risk(conversation)

        return {
            "message": llm_response["message"],
            "mood": mood,
            "suggested_action": suggested_action,
            "risk_level": risk_level,
        }

    def _detect_risk(self, conversation: List[ChatMessage]) -> RiskLevel:
        last_user_message = conversation[-1]["content"].lower()

        risky_phrases = [
            "no quiero seguir",
            "no vale la pena",
            "me quiero morir",
            "no aguanto más",
            "quiero desaparecer",
        ]

        for phrase in risky_phrases:
            if phrase in last_user_message:
                return "high"

        return "none"
