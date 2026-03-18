import base64
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from app.repositories.feedback_repository import FeedbackRepository
from app.core.config import config

router = APIRouter()
feedback_repo = FeedbackRepository()


class SurveyAnswers(BaseModel):
    nps: int
    utilidad: Optional[str] = None
    opinion: Optional[str] = None
    features: Optional[str] = None
    fallas: Optional[str] = None


class SurveyRequest(BaseModel):
    user_id: Optional[str] = None
    session_length_s: int
    message_count: int
    answers: SurveyAnswers


class FeedbackRequest(BaseModel):
    user_id: Optional[str] = None
    texto: Optional[str] = None
    categoria: Optional[str] = "general"
    rating: Optional[int] = None
    audio_base64: Optional[str] = None
    audio_mime: Optional[str] = None


@router.post("/survey")
def survey_endpoint(req: SurveyRequest):
    try:
        feedback_repo.save_survey({
            "user_id":         req.user_id,
            "session_length_s": req.session_length_s,
            "message_count":   req.message_count,
            "nps":             req.answers.nps,
            "utilidad":        req.answers.utilidad,
            "opinion":         req.answers.opinion,
            "features":        req.answers.features,
            "fallas":          req.answers.fallas,
        })
        return {"ok": True}
    except Exception as e:
        print("Survey error:", e)
        return {"ok": True}


@router.post("/feedback")
def feedback_endpoint(req: FeedbackRequest):
    try:
        feedback_repo.save_feedback({
            "user_id":      req.user_id,
            "texto":        req.texto,
            "categoria":    req.categoria or "general",
            "rating":       req.rating,
            "audio_base64": req.audio_base64,
            "audio_mime":   req.audio_mime,
            "app_version":  "mvp-1",
        })
        return {"ok": True}
    except Exception as e:
        print(f"⚠️ Error guardando feedback: {e}")
        return {"ok": True, "warning": str(e)}


@router.get("/admin/feedback")
def admin_feedback(
    limit: int = 50,
    categoria: Optional[str] = None,
    x_admin_key: Optional[str] = None,
):
    if x_admin_key != config.ADMIN_KEY:
        raise HTTPException(status_code=401, detail="No autorizado")
    try:
        data = feedback_repo.get_feedback(limit, categoria)
        return {"total": len(data), "feedbacks": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/feedback/{feedback_id}/audio")
def admin_feedback_audio(feedback_id: str, x_admin_key: Optional[str] = None):
    if x_admin_key != config.ADMIN_KEY:
        raise HTTPException(status_code=401, detail="No autorizado")
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
    if x_admin_key != config.ADMIN_KEY:
        raise HTTPException(status_code=401, detail="No autorizado")
    try:
        data = feedback_repo.get_crisis_logs(limit, solo_pendientes)
        return {"total": len(data), "eventos": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/admin/crisis/{crisis_id}/revisar")
def admin_marcar_revisado(crisis_id: str, x_admin_key: Optional[str] = None):
    if x_admin_key != config.ADMIN_KEY:
        raise HTTPException(status_code=401, detail="No autorizado")
    try:
        feedback_repo.marcar_crisis_revisada(crisis_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))