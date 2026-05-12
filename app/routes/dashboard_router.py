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
        from collections import Counter, defaultdict

        hoy = date.today()
        hace_30 = (hoy - timedelta(days=30)).isoformat()
        hace_14 = (hoy - timedelta(days=14)).isoformat()

        # ── 1. Mood últimas 2 semanas (para comparación) ──────────────────────
        res_mood = (
            supabase.table("conversations")
            .select("mood, created_at")
            .eq("user_id", user_id)
            .eq("role", "assistant")
            .gte("created_at", hace_14)
            .not_.is_("mood", "null")
            .order("created_at", desc=False)
            .execute()
        )

        dias_mood: dict[str, Counter] = defaultdict(Counter)
        for row in (res_mood.data or []):
            dia = row["created_at"][:10]
            mood_norm = _normalizar_mood(row["mood"])
            if mood_norm:
                dias_mood[dia][mood_norm] += 1

        def _semana_valores(offset_inicio: int, offset_fin: int) -> list:
            resultado = []
            for i in range(offset_inicio, offset_fin + 1):
                dia = (hoy - timedelta(days=offset_fin - (i - offset_inicio))).isoformat()
                if dia in dias_mood:
                    mood_ganador = dias_mood[dia].most_common(1)[0][0]
                    resultado.append({
                        "fecha": dia,
                        "mood":  mood_ganador,
                        "value": MOOD_VALUE.get(mood_ganador, 2),
                    })
                else:
                    resultado.append({"fecha": dia, "mood": None, "value": None})
            return resultado

        mood_semanal          = _semana_valores(0, 6)   # últimos 7 días
        mood_semana_anterior  = _semana_valores(7, 13)  # 7 días previos

        def _promedio(semana: list) -> Optional[float]:
            vals = [d["value"] for d in semana if d["value"] is not None]
            return sum(vals) / len(vals) if vals else None

        avg_actual   = _promedio(mood_semanal)
        avg_anterior = _promedio(mood_semana_anterior)

        if avg_actual is None or avg_anterior is None:
            comparacion = None
        else:
            diff = avg_actual - avg_anterior
            if diff > 0.6:
                comparacion = "muy_mejor"
            elif diff > 0.15:
                comparacion = "un_poco_mejor"
            elif diff < -0.6:
                comparacion = "muy_peor"
            elif diff < -0.15:
                comparacion = "un_poco_peor"
            else:
                comparacion = "similar"

        dias_activos_semana = sum(1 for d in mood_semanal if d["value"] is not None)

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
            "mood_semanal":         mood_semanal,
            "dias_activos_semana":  dias_activos_semana,
            "comparacion_semana":   comparacion,
            "checkins":             checkins,
            "patrones":             patrones,
            "resumen":              resumen,
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
