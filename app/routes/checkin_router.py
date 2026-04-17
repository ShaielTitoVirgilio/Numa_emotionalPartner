# app/routes/checkin_router.py
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.core.db import supabase

router = APIRouter(prefix="/checkin", tags=["checkin"])

MOOD_OPTIONS = {
    1: "😔",
    2: "😐",
    3: "🙂",
    4: "😄",
}


class CheckinRequest(BaseModel):
    user_id: str
    mood_value: int = Field(..., ge=1, le=4)


@router.post("")
def crear_checkin(body: CheckinRequest):
    """Guarda el check-in diario del usuario. Un solo check-in por día."""
    emoji = MOOD_OPTIONS.get(body.mood_value)
    if not emoji:
        raise HTTPException(status_code=400, detail="mood_value debe ser entre 1 y 4")

    today = date.today().isoformat()

    try:
        supabase.table("daily_checkins").upsert(
            {
                "user_id":     body.user_id,
                "mood_value":  body.mood_value,
                "mood_emoji":  emoji,
                "checkin_date": today,
            },
            on_conflict="user_id,checkin_date",
        ).execute()
        return {"ok": True, "mood_emoji": emoji}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/today")
def checkin_hoy(user_id: str):
    """Devuelve el check-in de hoy si ya existe, o null si no."""
    today = date.today().isoformat()
    try:
        res = (
            supabase.table("daily_checkins")
            .select("mood_value, mood_emoji, created_at")
            .eq("user_id", user_id)
            .eq("checkin_date", today)
            .limit(1)
            .execute()
        )
        data = res.data
        return {"checkin": data[0] if data else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
def historial_checkins(user_id: str, days: int = 30):
    """Devuelve los check-ins de los últimos N días para el dashboard."""
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        res = (
            supabase.table("daily_checkins")
            .select("mood_value, mood_emoji, checkin_date")
            .eq("user_id", user_id)
            .gte("checkin_date", since)
            .order("checkin_date", desc=False)
            .execute()
        )
        return {"checkins": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
