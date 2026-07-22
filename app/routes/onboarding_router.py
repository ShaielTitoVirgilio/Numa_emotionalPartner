from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.core.observability import capturar_error
from app.core.errors import NumaError, MENSAJE_GENERICO
from app.core.auth import get_current_user_id
from app.repositories.user_repository import UserRepository

router = APIRouter()
user_repo = UserRepository()

MAX_RESPUESTA_CHARS = 1000


class OnboardingAnswer(BaseModel):
    pregunta_numero: int
    pregunta: str
    respuesta: str


class OnboardingRequest(BaseModel):
    user_id: Optional[str] = None  # ignorado: el user_id sale del token
    answers: List[OnboardingAnswer]


@router.post("/onboarding")
def onboarding_endpoint(request: OnboardingRequest, user_id: str = Depends(get_current_user_id)):
    try:
        user_repo.create_profile_if_missing(user_id)

        for a in request.answers:
            if len(a.respuesta) > MAX_RESPUESTA_CHARS:
                a.respuesta = a.respuesta[:MAX_RESPUESTA_CHARS]

        rows = [
            {
                "user_id":         user_id,
                "pregunta_numero": a.pregunta_numero,
                "pregunta":        a.pregunta,
                "respuesta":       a.respuesta,
            }
            for a in request.answers
        ]
        user_repo.save_onboarding_answers(user_id, rows)

        resp = {a.pregunta_numero: a.respuesta for a in request.answers}
        perfil_update = {
            "onboarding_completo": True,
            "nombre":              resp.get(1, ""),
            "pronombres":          resp.get(2),
            "etapa_vida":          resp.get(3),
            "que_le_pesa":         resp.get(4),
            "como_reacciona":      resp.get(5),
            "preferencias_extra":  resp.get(6),
        }
        user_repo.upsert_profile(user_id, perfil_update)

        return {"message": "Onboarding guardado correctamente"}
    except Exception as e:
        capturar_error(e, contexto="onboarding")
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)