# app/memory_service.py
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict, Any

# Parámetros por defecto (podés ajustarlos)
MEMORY_WINDOW_DAYS_DEFAULT = 12
MAX_MEMORIES_DEFAULT = 8

def _iso_utc(dt: datetime) -> str:
    # ISO8601 con tz para comparación en Supabase
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

def get_recent_memories(
    supabase,
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

    # Resolver duplicados por category (nos quedamos con la más nueva)
    seen_categories = set()
    unique_rows: List[Dict[str, Any]] = []
    to_deactivate_ids: List[str] = []

    for row in rows:
        cat = (row.get("category") or "").strip().lower()
        if cat:
            if cat in seen_categories:
                # Duplicada por tema → se desactiva esta (es más vieja por el orden)
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