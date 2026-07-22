import hmac
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field
from typing import Optional
from app.core.auth import get_current_user_id
from app.repositories.feedback_repository import FeedbackRepository
from app.memory_service import invalidate_patterns_cache
from app.core.config import config
from app.core.errors import NumaError, MENSAJE_GENERICO

router = APIRouter()
feedback_repo = FeedbackRepository()

MAX_TEXTO_CHARS = 5000


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
    rating: Optional[int] = Field(None, ge=1, le=5)
    rating_recomendaria: Optional[int] = Field(None, ge=1, le=5)  # ¿recomendarías/usarías Numa?


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
    try:
        feedback_repo.save_feedback({
            "user_id":             user_id,
            "texto":               _truncar(req.texto),
            "rating":              req.rating,
            "rating_recomendaria": req.rating_recomendaria,
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
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)


@router.get("/admin/feedback")
def admin_feedback(
    limit: int = 50,
    x_admin_key: Optional[str] = Header(None),
):
    _validar_admin_key(x_admin_key)
    try:
        data = feedback_repo.get_feedback(limit)
        return {"total": len(data), "feedbacks": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)


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
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)


@router.patch("/admin/crisis/{crisis_id}/revisar")
def admin_marcar_revisado(crisis_id: str, x_admin_key: Optional[str] = Header(None)):
    _validar_admin_key(x_admin_key)
    try:
        feedback_repo.marcar_crisis_revisada(crisis_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)
