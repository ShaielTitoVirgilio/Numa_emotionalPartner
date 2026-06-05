from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.repositories.user_repository import UserRepository
from app.core.db import supabase

router = APIRouter()
user_repo = UserRepository()


class DeleteAccountRequest(BaseModel):
    user_id: str
    reason: Optional[str] = ""


@router.post("/account/delete")
def delete_account_endpoint(req: DeleteAccountRequest):
    if not req.user_id:
        raise HTTPException(status_code=400, detail="user_id requerido")
    try:
        # Guardar el motivo antes de borrar cualquier dato
        if req.reason and req.reason.strip():
            supabase.table("user_feedback").insert({
                "user_id":   req.user_id,
                "texto":     req.reason.strip(),
                "categoria": "account_deletion",
                "app_version": "mvp-1",
            }).execute()

        user_repo.delete_all_user_data(req.user_id)
        return {"ok": True}
    except Exception as e:
        print(f"Error eliminando cuenta {req.user_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo eliminar la cuenta. Intentá de nuevo.")
