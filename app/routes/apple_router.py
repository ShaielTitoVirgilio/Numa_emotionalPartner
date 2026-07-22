from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.observability import capturar_error
from app.core.errors import NumaError, MENSAJE_GENERICO
from app.apple_auth_service import verify_apple_token, find_or_create_apple_user

router = APIRouter()


class AppleAuthRequest(BaseModel):
    identity_token: str
    full_name: Optional[str] = None


@router.post("/auth/apple")
def apple_auth_endpoint(req: AppleAuthRequest):
    try:
        apple_data = verify_apple_token(req.identity_token)
        result = find_or_create_apple_user(
            apple_sub=apple_data["sub"],
            email=apple_data.get("email"),
            full_name=req.full_name,
        )
        return result
    except NumaError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        capturar_error(e, contexto="apple_auth")
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)
