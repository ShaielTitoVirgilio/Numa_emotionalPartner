# app/routes/dashboard_router.py
from datetime import date, timedelta, datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from openai import OpenAI
import os
from app.core.db import supabase
from app.memory_service import get_topic_patterns_cached

# Cliente Groq para generar el insight (reutiliza la misma key)
_groq = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

# Cache en memoria: { user_id: (fecha_str, insight_dict) }
_insight_cache: dict = {}

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

        insight_ia = _generar_insight_ia(
            checkins=checkins,
            patrones=patrones,
            comparacion=comparacion,
            dias_activos=dias_activos_semana,
            user_id=user_id,
        )

        return {
            "mood_semanal":         mood_semanal,
            "dias_activos_semana":  dias_activos_semana,
            "comparacion_semana":   comparacion,
            "checkins":             checkins,
            "patrones":             patrones,
            "resumen":              resumen,
            "insight_ia":           insight_ia,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _generar_insight_ia(
    checkins: list,
    patrones: list,
    comparacion: Optional[str],
    dias_activos: int,
    user_id: str,
) -> Optional[dict]:
    """
    Llama al LLM para generar una observación nueva — algo que el usuario
    probablemente no notó conscientemente. Se cachea por día para no gastar
    tokens en cada apertura del dashboard.
    """
    hoy = date.today().isoformat()

    # Devolver desde cache si ya se generó hoy
    cached = _insight_cache.get(user_id)
    if cached and cached[0] == hoy:
        return cached[1]

    # No generar si no hay datos suficientes
    if not checkins and not patrones:
        return None

    # Armar resumen de datos para el prompt
    total = len(checkins)
    if total == 0:
        return None

    dias_bien = sum(1 for c in checkins if c["mood_value"] >= 3)
    dias_mal  = sum(1 for c in checkins if c["mood_value"] <= 2)

    checkin_desc = f"{total} check-ins este mes: {dias_bien} días bien/genial, {dias_mal} días mal/regular."

    comparacion_desc = {
        "muy_mejor":    "Esta semana estuvo bastante mejor que la anterior.",
        "un_poco_mejor":"Esta semana un poco mejor que la anterior.",
        "similar":      "Esta semana fue parecida a la anterior.",
        "un_poco_peor": "Esta semana un poco más difícil que la anterior.",
        "muy_peor":     "Esta semana fue bastante más difícil que la anterior.",
    }.get(comparacion or "", "")

    patrones_desc = ""
    if patrones:
        tops = [f"'{p['topic']}' ({p['count']} veces)" for p in patrones[:4]]
        patrones_desc = "Temas más hablados: " + ", ".join(tops) + "."

    dias_activos_desc = f"Días que usó la app esta semana: {dias_activos}."

    prompt = f"""Sos Numa, el compañero emocional. Tenés los siguientes datos del usuario del último mes:

{checkin_desc}
{comparacion_desc}
{patrones_desc}
{dias_activos_desc}

Tu tarea: escribir UNA observación corta (2-3 oraciones máximo) para el usuario que:
- Diga algo que probablemente NO notó conscientemente sobre sí mismo
- Conecte patrones entre temas y estado de ánimo si es posible
- Sea específica con los datos, no genérica
- Suene como Numa: cercana, directa, sin análisis clínico
- NO empiece con "Según los datos" ni "Noté que" ni "Basándome en"
- NO sea un resumen de lo que ya sabe
- Puede señalar una fortaleza, una tendencia o algo que vale la pena explorar

También devolvé un campo "tipo" con uno de estos valores:
- "fortaleza" — si destacás algo positivo o resiliente
- "patron" — si conectás temas con estado de ánimo
- "tendencia" — si señalás un cambio o dirección
- "reflexion" — si proponés algo para pensar

Devolvé JSON con este formato exacto:
{{"texto": "...", "tipo": "..."}}"""

    try:
        resp = _groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.75,
            max_tokens=200,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        data = json.loads(resp.choices[0].message.content or "{}")
        texto = data.get("texto", "").strip()
        tipo  = data.get("tipo", "reflexion")
        if not texto:
            return None
        result = {"texto": texto, "tipo": tipo}
        _insight_cache[user_id] = (hoy, result)
        return result
    except Exception as e:
        print(f"⚠️ insight_ia error: {e}")
        return None


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
