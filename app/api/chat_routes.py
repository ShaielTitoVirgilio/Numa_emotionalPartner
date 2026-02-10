'''
FastAPI recibe texto
arma el servicio
pide una respuesta
devuelve JSON limpio
 No sabe qué es Groq
 No sabe qué es un prompt
 No sabe qué es Numa
'''
from fastapi import APIRouter
from app.services.chat_service import ChatService
from app.llm.groq_client import GroqClient

router = APIRouter()

chat_service = ChatService(GroqClient())

@router.post("/chat")
def chat(payload: dict):
    texto = payload.get("message", "")
    historial = payload.get("history")

    return {
        "response": chat_service.chat(texto, historial)
    }

