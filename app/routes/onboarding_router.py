from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from app.repositories.user_repository import UserRepository

router = APIRouter()
user_repo = UserRepository()


class OnboardingAnswer(BaseModel):
    pregunta_numero: int
    pregunta: str
    respuesta: str


class OnboardingRequest(BaseModel):
    user_id: str
    answers: List[OnboardingAnswer]


@router.post("/onboarding")
def onboarding_endpoint(request: OnboardingRequest):
    try:
        user_repo.create_profile_if_missing(request.user_id)

        rows = [
            {
                "user_id":         request.user_id,
                "pregunta_numero": a.pregunta_numero,
                "pregunta":        a.pregunta,
                "respuesta":       a.respuesta,
            }
            for a in request.answers
        ]
        user_repo.save_onboarding_answers(request.user_id, rows)

        resp = {a.pregunta_numero: a.respuesta for a in request.answers}
        perfil_update = {
            "onboarding_completo": True,
            "nombre":              resp.get(1, ""),
            "pronombres":          resp.get(2),
            "etapa_vida":          resp.get(3),
            "que_le_pesa":         resp.get(4),
            "como_reacciona":      resp.get(5),
            "prefiere_respuestas": resp.get(6),
            "preferencias_extra":  resp.get(7),
        }
        user_repo.upsert_profile(request.user_id, perfil_update)

        return {"message": "Onboarding guardado correctamente"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))