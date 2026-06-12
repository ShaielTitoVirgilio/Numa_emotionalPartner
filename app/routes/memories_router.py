# app/routes/memories_router.py
"""
Transparencia de memorias: el usuario puede ver y borrar lo que Numa
recuerda de él. El borrado es lógico (is_active=False, el mismo mecanismo
que usa el resto de la app) — no cambia el esquema de la base.
"""

from fastapi import APIRouter, HTTPException, Depends
from app.core.auth import get_current_user_id
from app.core.db import supabase
from app.memory_service import invalidate_patterns_cache

router = APIRouter(prefix="/memories", tags=["memories"])


@router.get("")
def listar_memorias(user_id: str = Depends(get_current_user_id)):
    """Memorias activas del usuario, las más recientes primero."""
    try:
        res = (
            supabase.table("memories")
            .select("id, content, category, priority, created_at")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        return {"memories": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{memory_id}")
def borrar_memoria(memory_id: str, user_id: str = Depends(get_current_user_id)):
    """Desactiva una memoria propia. El filtro por user_id evita borrar ajenas."""
    try:
        res = (
            supabase.table("memories")
            .update({"is_active": False})
            .eq("id", memory_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="Memoria no encontrada")
        invalidate_patterns_cache(user_id)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
