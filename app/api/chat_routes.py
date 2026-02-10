from fastapi import APIRouter
from app.services.chat_service import ChatService
from app.llm.groq_client import GroqClient

router = APIRouter()
chat_service = ChatService(GroqClient())


@router.post("/chat")
def chat(payload: dict):
    return chat_service.chat(
        payload.get("message", ""),
        payload.get("history")
    )
