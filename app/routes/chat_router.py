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
    get_dias_inactivo,
    get_checkin_hoy_cached,
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

CATEGORIAS_VALIDAS = {
    "trabajo", "estudios", "relaciones", "salud", "identidad",
    "emocional", "hobbies", "vida_cotidiana", "otro",
}


def _validar_priority(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 3
    return max(1, min(5, n))


def _validar_category(value) -> str:
    if not value:
        return "otro"
    v = str(value).strip().lower()
    return v if v in CATEGORIAS_VALIDAS else "otro"


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class UbicacionData(BaseModel):
    ciudad: Optional[str] = None
    pais: Optional[str] = None
    countryCode: Optional[str] = None


class ChatRequest(BaseModel):
    conversation: List[Message]
    user_id: Optional[str] = None
    perfil: Optional[Dict[str, Any]] = None
    ubicacion: Optional[UbicacionData] = None
    ultimo_mood: Optional[str] = None
    checkin_recien_hecho: Optional[bool] = False


class ChatResponse(BaseModel):
    message: str
    mood: str
    suggested_action: Optional[str] = None
    risk_level: Optional[str] = None
    nuevas_memorias: Optional[List[Dict[str, Any]]] = None


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
        crisis_score = crisis.get("score", 0.0)

        if crisis["detected"]:
            # Solo critical/high llegan acá (método, ideación, autolesión):
            # respuesta determinística, sin LLM.
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
                "nuevas_memorias":  None,
            }

        # Señal media (desborde/implícitas): va al LLM con el módulo de crisis activado.
        # Se loguea igual para trazabilidad del equipo.
        if crisis_score >= 0.35 and crisis.get("category"):
            background_tasks.add_task(
                feedback_repo.save_crisis_log,
                body.user_id,
                ultimo_mensaje,
                crisis["category"],
                crisis["log_level"],
            )

        memorias_sesion: List[Dict[str, Any]] = []
        if perfil and "_memorias_sesion" in perfil:
            raw = perfil.pop("_memorias_sesion", []) or []
            memorias_sesion = [
                m if isinstance(m, dict)
                else {"content": str(m), "priority": 3, "category": "otro"}
                for m in raw
            ]

        memorias_vigentes: List[Dict[str, Any]] = []
        ids_a_desactivar: List[str] = []
        patrones: List[dict] = []

        if body.user_id:
            try:
                m_db, ids_old = get_recent_memories(
                    user_id=body.user_id,
                    days=MEMORY_WINDOW_DAYS_DEFAULT,
                    max_items=12
                )
                seen = set()
                merged = []
                for m in (memorias_sesion or []) + m_db:
                    key = (m.get("content") or "").strip()
                    if key and key not in seen:
                        seen.add(key)
                        merged.append(m)
                memorias_vigentes = merged[:15]
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

        # Detectar reenganche: >5 días sin actividad
        dias_inactivo = 0
        if body.user_id and num_interacciones <= 4:
            # Solo consultamos al principio de la sesión para no repetir la llamada
            dias_inactivo = get_dias_inactivo(body.user_id)

        # ¿El turno anterior estuvo en territorio de crisis? (stateless: se mira el
        # score de los últimos 2 mensajes previos del usuario que vienen en el request)
        ultimo_modulo_critico = False
        previos_usuario = [m.content for m in body.conversation[:-1] if m.role == "user"][-2:]
        for msg_previo in previos_usuario:
            if detectar_crisis(msg_previo).get("score", 0.0) >= 0.35:
                ultimo_modulo_critico = True
                break

        # Check-in del día (1-4) — cacheado 5 min en memory_service
        checkin_hoy = None
        if body.user_id:
            try:
                checkin_hoy = get_checkin_hoy_cached(body.user_id)
            except Exception as e:
                print(f"⚠️ No se pudo cargar el check-in: {e}")

        # Últimos 4 mensajes para las detecciones del router de módulos
        historial_reciente = [m.model_dump() for m in body.conversation[-4:]]

        # Racha de mensajes de Numa terminados en "?": el servidor la cuenta
        # (el modelo no sabe auditar su propio historial) y el prompt recibe
        # la señal ya calculada. Se recalcula en cada turno, así el bloqueo
        # se levanta solo apenas Numa responde sin pregunta.
        mensajes_numa = [m.content for m in body.conversation if m.role == "assistant"]
        preguntas_seguidas = 0
        for contenido in reversed(mensajes_numa):
            if contenido.rstrip().rstrip('"\'').endswith("?"):
                preguntas_seguidas += 1
            else:
                break

        system_prompt = construir_prompt(
            perfil=perfil,
            memorias=memorias_vigentes,
            patrones=patrones,
            es_inicio_sesion=es_inicio_sesion,
            num_interacciones=num_interacciones,
            es_primera_vez=es_primera_vez,
            ubicacion=body.ubicacion.model_dump() if body.ubicacion else None,
            dias_inactivo=dias_inactivo,
            checkin_hoy=checkin_hoy,
            checkin_recien_hecho=bool(body.checkin_recien_hecho),
            crisis_score=crisis_score,
            ultimo_modulo_critico=ultimo_modulo_critico,
            historial_reciente=historial_reciente,
            mood_actual=body.ultimo_mood,
            ultimo_mensaje=ultimo_mensaje,
            preguntas_seguidas=preguntas_seguidas,
        )

        result = llm.generate_response(
            conversation=[m.model_dump() for m in body.conversation],
            system_prompt=system_prompt,
        )

        memorias_llm: List[Dict[str, Any]] = result.get("memories") or []

        # Validar/clampear metadata de cada memoria antes de persistir
        memorias_validadas: List[Dict[str, Any]] = []
        for m in memorias_llm:
            content = (m.get("content") or "").strip()
            if content:
                memorias_validadas.append({
                    "content":  content,
                    "category": _validar_category(m.get("category")),
                    "priority": _validar_priority(m.get("priority")),
                })

        # Respaldo: si el LLM no guardó ninguna memoria, intentar detectar evento próximo
        if not memorias_validadas:
            evento = detectar_evento_proximo(ultimo_mensaje)
            if evento:
                content_ev, cat_ev, prio_ev = evento
                memorias_validadas.append({"content": content_ev, "category": cat_ev, "priority": prio_ev})

        # Sin early-return: reportar el nivel real de señal detectada
        risk_level = "medium" if crisis_score >= 0.35 else "none"

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
                memorias_validadas,
                result.get("mood"),
            )
            if ids_a_desactivar:
                background_tasks.add_task(conversation_repo.deactivate_memories, ids_a_desactivar)
            if memorias_validadas:
                invalidate_patterns_cache(body.user_id)

        return {
            "message":          result["message"],
            "mood":             result["mood"],
            "suggested_action": result.get("suggested_action"),
            "risk_level":       risk_level,
            "nuevas_memorias":  memorias_validadas,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))