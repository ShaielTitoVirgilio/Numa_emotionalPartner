from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, UploadFile, File
from pydantic import BaseModel
from typing import List, Literal, Optional, Dict, Any
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.llm_client import LLMClient
from app.numa_prompt import construir_prompt
from app.memory_service import (
    get_recent_memories,
    get_topic_patterns_cached,
    invalidate_patterns_cache,
    deactivate_event_memories,
    detectar_evento_proximo,
    MEMORY_WINDOW_DAYS_DEFAULT,
)
from app.crisis_detector import detectar_crisis
from app.speech_service import speech_to_text
from app.repositories.user_repository import UserRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.feedback_repository import FeedbackRepository

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
llm = LLMClient()
user_repo = UserRepository()
conversation_repo = ConversationRepository()
feedback_repo = FeedbackRepository()


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    conversation: List[Message]
    user_id: Optional[str] = None
    perfil: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    message: str
    mood: str
    suggested_action: Optional[str] = None
    risk_level: Optional[str] = None
    nueva_memoria: Optional[str] = None


@router.post("/speech-to-text")
async def speech_to_text_endpoint(file: UploadFile = File(...)):
    try:
        audio_bytes = await file.read()

        if len(audio_bytes) < 5000:
            raise HTTPException(status_code=400, detail="Audio demasiado corto")

        text = speech_to_text(audio_bytes, file.filename)
        return {"text": text}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ STT ERROR:", e)
        raise HTTPException(status_code=503, detail="Servicio de transcripción no disponible")


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("18/minute")
def chat_endpoint(request: Request, body: ChatRequest, background_tasks: BackgroundTasks):
    try:
        perfil = body.perfil

        if perfil is None and body.user_id:
            try:
                perfil = user_repo.get_profile(body.user_id)
            except Exception:
                perfil = None

        ultimo_mensaje = body.conversation[-1].content if body.conversation else ""
        crisis = detectar_crisis(ultimo_mensaje)

        if crisis["detected"]:
            if crisis["log_level"] in ("critical", "high"):
                background_tasks.add_task(
                    feedback_repo.save_crisis_log,
                    body.user_id,
                    ultimo_mensaje,
                    crisis["category"],
                    crisis["log_level"],
                )
            return {
                "message":          crisis["message"],
                "mood":             "sad",
                "suggested_action": None,
                "risk_level":       "high",
                "nueva_memoria":    None,
            }

        memorias_sesion = []
        if perfil and "_memorias_sesion" in perfil:
            memorias_sesion = perfil.pop("_memorias_sesion", []) or []

        memorias_vigentes: List[str] = []
        ids_a_desactivar: List[str] = []
        patrones: List[dict] = []

        if body.user_id:
            try:
                m_db, ids_old = get_recent_memories(
                    user_id=body.user_id,
                    days=MEMORY_WINDOW_DAYS_DEFAULT,
                    max_items=12
                )
                memorias_vigentes = (memorias_sesion or []) + m_db
                ids_a_desactivar = ids_old
            except Exception as e:
                print(f"⚠️ No se pudieron cargar memorias: {e}")
                memorias_vigentes = memorias_sesion or []

            try:
                patrones = get_topic_patterns_cached(user_id=body.user_id)
                print(f"🔍 Patrones detectados: {patrones}")
            except Exception as e:
                print(f"⚠️ No se pudieron cargar patrones: {e}")

        es_inicio_sesion = len(body.conversation) == 1
        num_interacciones = len(body.conversation)

        # Primera vez: primer mensaje de la sesión Y sin memorias previas de otras sesiones
        es_primera_vez = (num_interacciones == 1 and not memorias_vigentes)

        system_prompt = construir_prompt(
            perfil=perfil,
            memorias=memorias_vigentes,
            patrones=patrones,
            es_inicio_sesion=es_inicio_sesion,
            num_interacciones=num_interacciones,
            es_primera_vez=es_primera_vez,
        )

        result = llm.generate_response(
            conversation=[m.dict() for m in body.conversation],
            system_prompt=system_prompt,
        )

        memoria_detectada = result.get("memory")

        # Respaldo: si el LLM no guardó memoria, intentar detectar evento próximo
        if not memoria_detectada:
            memoria_detectada = detectar_evento_proximo(ultimo_mensaje)

        risk_level = "none"
        if body.conversation:
            crisis_riesgo = detectar_crisis(body.conversation[-1].content)
            risk_level = crisis_riesgo["log_level"] if crisis_riesgo["detected"] else "none"

        # El usuario ya respondió al primer mensaje de Numa (que preguntó por el evento)
        # → desactivar memorias de eventos para que no vuelvan a aparecer
        if body.user_id and len(body.conversation) == 3:
            background_tasks.add_task(deactivate_event_memories, body.user_id)

        if body.user_id and body.conversation:
            background_tasks.add_task(
                conversation_repo.save,
                body.user_id,
                body.conversation[-1].content,
                result["message"],
                memoria_detectada,
                result.get("memory_category"),
                result.get("mood"),
            )
            if ids_a_desactivar:
                background_tasks.add_task(conversation_repo.deactivate_memories, ids_a_desactivar)
            # Si se guardó una memoria nueva, los patrones pueden haber cambiado
            if memoria_detectada:
                invalidate_patterns_cache(body.user_id)

        return {
            "message":          result["message"],
            "mood":             result["mood"],
            "suggested_action": result.get("suggested_action"),
            "risk_level":       risk_level,
            "nueva_memoria":    memoria_detectada,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))