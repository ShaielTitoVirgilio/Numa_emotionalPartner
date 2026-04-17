# app/routes/dashboard_router.py
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException
from app.core.db import supabase
from app.memory_service import get_topic_patterns_cached

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

MOOD_ORDER = ["muy_bien", "bien", "neutral", "triste", "mal", "overwhelmed", "stressed", "sad", "contento", "happy"]

MOOD_LABEL = {
    "positive":    "Bien",
    "happy":       "Bien",
    "contento":    "Bien",
    "bien":        "Bien",
    "calm":        "Bien",
    "neutral":     "Regular",
    "sad":         "Mal",
    "triste":      "Mal",
    "mal":         "Mal",
    "stressed":    "Mal",
    "overwhelmed": "Mal",
    "anxious":     "Mal",
    "negative":    "Mal",
}

MOOD_VALUE = {
    "Bien":    3,
    "Regular": 2,
    "Mal":     1,
}


def _normalizar_mood(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return MOOD_LABEL.get(raw.lower().strip())


@router.get("")
def get_dashboard(user_id: str):
    """Devuelve todos los datos necesarios para el dashboard del usuario."""
    try:
        hoy = date.today()
        hace_30 = (hoy - timedelta(days=30)).isoformat()
        hace_7  = (hoy - timedelta(days=7)).isoformat()

        # ── 1. Mood semanal (últimos 7 días, desde conversations) ─────────────
        res_mood = (
            supabase.table("conversations")
            .select("mood, created_at")
            .eq("user_id", user_id)
            .eq("role", "assistant")
            .gte("created_at", hace_7)
            .not_.is_("mood", "null")
            .order("created_at", desc=False)
            .execute()
        )

        # Agrupar por día: quedarse con el mood más frecuente del día
        from collections import Counter, defaultdict
        dias_mood: dict[str, Counter] = defaultdict(Counter)
        for row in (res_mood.data or []):
            dia = row["created_at"][:10]  # "2026-04-15"
            mood_norm = _normalizar_mood(row["mood"])
            if mood_norm:
                dias_mood[dia][mood_norm] += 1

        mood_semanal = []
        for i in range(7):
            dia = (hoy - timedelta(days=6 - i)).isoformat()
            if dia in dias_mood:
                mood_ganador = dias_mood[dia].most_common(1)[0][0]
                mood_semanal.append({
                    "fecha": dia,
                    "mood":  mood_ganador,
                    "value": MOOD_VALUE.get(mood_ganador, 2),
                })
            else:
                mood_semanal.append({"fecha": dia, "mood": None, "value": None})

        # ── 2. Check-ins diarios (últimos 30 días) ────────────────────────────
        res_checkins = (
            supabase.table("daily_checkins")
            .select("mood_value, mood_emoji, checkin_date")
            .eq("user_id", user_id)
            .gte("checkin_date", hace_30)
            .order("checkin_date", desc=False)
            .execute()
        )
        checkins = res_checkins.data or []

        # ── 3. Patrones del último mes ────────────────────────────────────────
        patrones = get_topic_patterns_cached(user_id=user_id)

        # ── 4. Resumen simple ─────────────────────────────────────────────────
        total_checkins = len(checkins)
        dias_bien = sum(1 for c in checkins if c["mood_value"] >= 3)
        dias_mal  = sum(1 for c in checkins if c["mood_value"] <= 2)
        top_patron = patrones[0]["topic"] if patrones else None

        resumen = _construir_resumen(dias_bien, dias_mal, total_checkins, top_patron)

        return {
            "mood_semanal": mood_semanal,
            "checkins":     checkins,
            "patrones":     patrones,
            "resumen":      resumen,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _construir_resumen(dias_bien: int, dias_mal: int, total: int, top_patron: Optional[str]) -> str:
    if total == 0:
        return "Todavía no hay suficientes datos. Seguí usando Numa y acá vas a ver cómo te fuiste sintiendo."

    partes = []
    if dias_bien > dias_mal:
        partes.append(f"Este mes tuviste más días buenos que difíciles ({dias_bien} vs {dias_mal}).")
    elif dias_mal > dias_bien:
        partes.append(f"Este mes fue bastante movido — tuviste {dias_mal} días difíciles.")
    else:
        partes.append("Este mes estuvo bastante parejo entre días buenos y difíciles.")

    if top_patron:
        partes.append(f"El tema que más apareció fue '{top_patron}'.")

    return " ".join(partes)
