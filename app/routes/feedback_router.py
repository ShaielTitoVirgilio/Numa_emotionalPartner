import base64
import hmac
from fastapi import APIRouter, HTTPException, Header, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Optional
from app.core.auth import get_current_user_id
from app.repositories.feedback_repository import FeedbackRepository
from app.memory_service import invalidate_patterns_cache
from app.core.config import config

router = APIRouter()
feedback_repo = FeedbackRepository()

MAX_TEXTO_CHARS = 5000
# ~10 MB de audio en base64 (4/3 de overhead)
MAX_AUDIO_B64_CHARS = 14_000_000


def _validar_admin_key(provided: Optional[str]) -> None:
    """Valida la admin key en tiempo constante. La key viaja SIEMPRE por
    header (nunca query string: quedaba en logs de acceso, historial y
    referers) y se rechaza si el server no tiene ADMIN_KEY configurada."""
    expected = config.ADMIN_KEY or ""
    if not expected or not provided or not hmac.compare_digest(str(provided), expected):
        raise HTTPException(status_code=401, detail="No autorizado")


class FeedbackRequest(BaseModel):
    user_id: Optional[str] = None  # ignorado: el user_id sale del token
    texto: Optional[str] = None
    categoria: Optional[str] = "general"
    rating: Optional[int] = Field(None, ge=1, le=5)
    rating_recomendaria: Optional[int] = Field(None, ge=1, le=5)  # ¿recomendarías/usarías Numa?
    audio_base64: Optional[str] = None
    audio_mime: Optional[str] = None


class ExerciseRatingRequest(BaseModel):
    user_id: Optional[str] = None  # ignorado: el user_id sale del token
    exercise_id: str
    rating: int = Field(..., ge=1, le=5)
    valor_texto: Optional[str] = None  # "positive_high" | "positive_low" | "neutral" | "negative"


def _truncar(valor: Optional[str], max_chars: int = MAX_TEXTO_CHARS) -> Optional[str]:
    if valor is None:
        return None
    return valor[:max_chars]


@router.post("/feedback")
def feedback_endpoint(req: FeedbackRequest, user_id: str = Depends(get_current_user_id)):
    if req.audio_base64 and len(req.audio_base64) > MAX_AUDIO_B64_CHARS:
        raise HTTPException(status_code=413, detail="Audio demasiado largo")
    try:
        feedback_repo.save_feedback({
            "user_id":             user_id,
            "texto":               _truncar(req.texto),
            "categoria":           req.categoria or "general",
            "rating":              req.rating,
            "rating_recomendaria": req.rating_recomendaria,
            "audio_base64":        req.audio_base64,
            "audio_mime":          req.audio_mime,
            "app_version":         "mvp-1",
        })
        return {"ok": True}
    except Exception as e:
        print(f"⚠️ Error guardando feedback: {e}")
        return {"ok": True, "warning": str(e)}


@router.post("/exercise-rating")
def exercise_rating_endpoint(req: ExerciseRatingRequest, user_id: str = Depends(get_current_user_id)):
    try:
        feedback_repo.save_exercise_rating(
            user_id=user_id,
            exercise_id=req.exercise_id,
            rating=req.rating,
            valor_texto=req.valor_texto,
        )
        # El rating es información de preferencia del usuario
        invalidate_patterns_cache(user_id)
        return {"ok": True}
    except Exception as e:
        print(f"⚠️ Error guardando exercise rating: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/feedback")
def admin_feedback(
    limit: int = 50,
    categoria: Optional[str] = None,
    x_admin_key: Optional[str] = Header(None),
):
    _validar_admin_key(x_admin_key)
    try:
        data = feedback_repo.get_feedback(limit, categoria)
        return {"total": len(data), "feedbacks": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/feedback/{feedback_id}/audio")
def admin_feedback_audio(feedback_id: str, x_admin_key: Optional[str] = Header(None)):
    _validar_admin_key(x_admin_key)
    try:
        data = feedback_repo.get_feedback_audio(feedback_id)
        if not data or not data.get("audio_base64"):
            raise HTTPException(status_code=404, detail="Audio no encontrado")
        audio_bytes = base64.b64decode(data["audio_base64"])
        mime = data.get("audio_mime", "audio/webm")
        return Response(content=audio_bytes, media_type=mime)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/crisis")
def admin_crisis(
    limit: int = 50,
    solo_pendientes: bool = True,
    x_admin_key: Optional[str] = Header(None),
):
    _validar_admin_key(x_admin_key)
    try:
        data = feedback_repo.get_crisis_logs(limit, solo_pendientes)
        return {"total": len(data), "eventos": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/admin/crisis/{crisis_id}/revisar")
def admin_marcar_revisado(crisis_id: str, x_admin_key: Optional[str] = Header(None)):
    _validar_admin_key(x_admin_key)
    try:
        feedback_repo.marcar_crisis_revisada(crisis_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
