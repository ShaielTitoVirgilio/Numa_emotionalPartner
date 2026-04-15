# app/memory_service.py
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict, Any
from app.core.db import supabase  

# Parámetros por defecto (podés ajustarlos)
MEMORY_WINDOW_DAYS_DEFAULT = 30
MAX_MEMORIES_DEFAULT = 20

# ── Detector de eventos próximos ─────────────────────────────────────────────
_PALABRAS_TIEMPO = [
    "mañana", "pasado mañana", "esta noche", "hoy a la tarde", "hoy a la noche",
    "el finde", "este finde", "el sábado", "el domingo", "el lunes", "el martes",
    "el miércoles", "el jueves", "el viernes", "esta semana", "la semana que viene",
    "la semana próxima", "el mes que viene", "en unos días", "en pocos días",
]

_PALABRAS_EVENTO = [
    "examen", "parcial", "final", "prueba", "entrevista", "entrevista de trabajo",
    "entrevista laboral", "partido", "cita", "turno", "reunión", "presentación",
    "exposición", "viaje", "mudanza", "cirugía", "operación", "cumpleaños",
    "evento", "competencia", "torneo", "audición", "entrega",
]

def detectar_evento_proximo(mensaje: str) -> str | None:
    """
    Retorna una memoria formateada si el mensaje menciona un evento próximo.
    Actúa como respaldo cuando el LLM no guarda la memoria por su cuenta.
    """
    texto = mensaje.lower()
    tiene_tiempo = any(p in texto for p in _PALABRAS_TIEMPO)
    tiene_evento = any(p in texto for p in _PALABRAS_EVENTO)

    if tiene_tiempo and tiene_evento:
        for evento in _PALABRAS_EVENTO:
            if evento in texto:
                for tiempo in _PALABRAS_TIEMPO:
                    if tiempo in texto:
                        return f"Tiene {evento} {tiempo}."
    return None

def _iso_utc(dt: datetime) -> str:
    # ISO8601 con tz para comparación en Supabase
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

def get_topic_patterns(
    user_id: str,
    days: int = 30,
    min_count: int = 2,
) -> List[Dict[str, Any]]:
    """
    Devuelve los temas que el usuario mencionó min_count o más veces en los últimos 'days' días.
    Incluye memorias activas e inactivas para capturar frecuencia real.
    """
    since_ts = _iso_utc(datetime.now(timezone.utc) - timedelta(days=days))

    res = (
        supabase.table("memories")
        .select("category")
        .eq("user_id", user_id)
        .gte("created_at", since_ts)
        .not_.eq("category", "chat")   # excluir memorias viejas sin categoría real
        .execute()
    )
    rows: List[Dict[str, Any]] = res.data or []

    from collections import Counter
    counts = Counter(
        r["category"].strip().lower()
        for r in rows
        if r.get("category")
    )

    return [
        {"topic": topic, "count": count}
        for topic, count in counts.most_common()
        if count >= min_count
    ]


def get_recent_memories(
    
    user_id: str,
    days: int = MEMORY_WINDOW_DAYS_DEFAULT,
    max_items: int = MAX_MEMORIES_DEFAULT,
) -> Tuple[List[str], List[str]]:
    """
    Devuelve:
      - memorias_vigentes: lista de strings (contenido) para el prompt
      - to_deactivate_ids: IDs de memorias viejas (duplicadas por category) a desactivar
    Lógica:
      1) Sólo memorias activas, dentro de la ventana de 'days'
      2) Ordenar por created_at DESC
      3) Por cada category, quedarnos con la más nueva; el resto se desactiva
      4) Limitar a 'max_items' para el prompt
    """
    since_ts = _iso_utc(datetime.now(timezone.utc) - timedelta(days=days))

    # Pull de memorias activas y recientes
    res = (
        supabase.table("memories")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .gte("created_at", since_ts)
        .order("created_at", desc=True)
        .execute()
    )
    rows: List[Dict[str, Any]] = res.data or []

    # Resolver duplicados por category (solo para categorías específicas)
    # "chat" y "otro" son demasiado genéricas para deduplicar — se guardan todas
    CATEGORIAS_DEDUPLICABLES = {"trabajo", "relaciones", "salud", "identidad", "emocional"}

    seen_categories = set()
    unique_rows: List[Dict[str, Any]] = []
    to_deactivate_ids: List[str] = []

    for row in rows:
        cat = (row.get("category") or "").strip().lower()
        if cat in CATEGORIAS_DEDUPLICABLES:
            if cat in seen_categories:
                if row.get("id"):
                    to_deactivate_ids.append(row["id"])
                continue
            seen_categories.add(cat)

        unique_rows.append(row)

    # Limitar las que van al prompt
    trimmed = unique_rows[:max_items]

    memorias_vigentes: List[str] = []
    for r in trimmed:
        content = (r.get("content") or "").strip()
        if content:
            memorias_vigentes.append(content)

    return memorias_vigentes, to_deactivate_ids