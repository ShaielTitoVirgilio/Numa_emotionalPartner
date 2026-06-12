from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.core.auth import get_current_user_id
from app.repositories.user_repository import UserRepository
from app.core.db import supabase

router = APIRouter()
user_repo = UserRepository()


class DeleteAccountRequest(BaseModel):
    user_id: Optional[str] = None  # ignorado: el user_id sale del token
    reason: Optional[str] = ""


@router.post("/account/delete")
def delete_account_endpoint(req: DeleteAccountRequest, user_id: str = Depends(get_current_user_id)):
    # Solo se puede borrar la cuenta propia: el user_id sale del token.
    # Antes cualquiera podía borrar la cuenta de cualquiera con su UUID.
    try:
        # Guardar el motivo antes de borrar cualquier dato
        if req.reason and req.reason.strip():
            supabase.table("user_feedback").insert({
                "user_id":   user_id,
                "texto":     req.reason.strip()[:2000],
                "categoria": "account_deletion",
                "app_version": "mvp-1",
            }).execute()

        user_repo.delete_all_user_data(user_id)
        return {"ok": True}
    except Exception as e:
        print(f"Error eliminando una cuenta: {e}")
        raise HTTPException(status_code=500, detail="No se pudo eliminar la cuenta. Intentá de nuevo.")
