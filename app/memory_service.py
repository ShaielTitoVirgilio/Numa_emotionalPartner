# app/memory_service.py
from __future__ import annotations
import time
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict, Any
from app.core.db import supabase

# Parámetros por defecto (podés ajustarlos)
MEMORY_WINDOW_DAYS_DEFAULT = 30
MAX_MEMORIES_DEFAULT = 20

# Caché en memoria de patrones por usuario.
# Clave: user_id → (expires_at_epoch, lista_de_patrones)
_PATTERNS_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_PATTERNS_TTL_SECONDS = 300  # 5 minutos

# ── Detector de eventos próximos ─────────────────────────────────────────────
_PALABRAS_TIEMPO = [
    "mañana", "pasado mañana", "esta noche", "hoy a la tarde", "hoy a la noche",
    "el finde", "este finde", "el sábado", "el domingo", "el lunes", "el martes",
    "el miércoles", "el jueves", "el viernes", "esta semana", "la semana que viene",
    "la semana próxima", "el mes que viene", "en unos días", "en pocos días",
]

# evento → (categoría, prioridad sugerida)
_EVENTOS_CATEGORIA: Dict[str, Tuple[str, int]] = {
    "examen":                ("estudios", 2),
    "parcial":               ("estudios", 2),
    "final":                 ("estudios", 2),
    "prueba":                ("estudios", 2),
    "entrega":               ("estudios", 2),
    "entrevista":            ("trabajo", 2),
    "entrevista de trabajo": ("trabajo", 2),
    "entrevista laboral":    ("trabajo", 2),
    "reunión":               ("trabajo", 2),
    "presentación":          ("trabajo", 2),
    "exposición":            ("trabajo", 2),
    "cirugía":               ("salud", 3),
    "operación":             ("salud", 3),
    "turno":                 ("salud", 2),
    "partido":               ("hobbies", 1),
    "competencia":           ("hobbies", 2),
    "torneo":                ("hobbies", 2),
    "audición":              ("hobbies", 2),
    "cita":                  ("vida_cotidiana", 2),
    "cumpleaños":            ("vida_cotidiana", 2),
    "evento":                ("vida_cotidiana", 2),
    "viaje":                 ("vida_cotidiana", 2),
    "mudanza":               ("vida_cotidiana", 3),
}

_PALABRAS_EVENTO = list(_EVENTOS_CATEGORIA.keys())

def detectar_evento_proximo(mensaje: str) -> Tuple[str, str, int] | None:
    """
    Retorna (texto_memoria, categoría, prioridad) si el mensaje menciona un evento próximo.
    Actúa como respaldo cuando el LLM no guarda la memoria por su cuenta.
    """
    texto = mensaje.lower()
    if not any(p in texto for p in _PALABRAS_TIEMPO):
        return None

    for evento, (categoria, prioridad) in _EVENTOS_CATEGORIA.items():
        if evento in texto:
            for tiempo in _PALABRAS_TIEMPO:
                if tiempo in texto:
                    return (f"Tiene {evento} {tiempo}.", categoria, prioridad)
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
        .select("category, content, created_at")
        .eq("user_id", user_id)
        .gte("created_at", since_ts)
        .not_.eq("category", "chat")   # excluir categorías genéricas sin valor como patrón
        .not_.eq("category", "otro")
        .execute()
    )
    rows: List[Dict[str, Any]] = res.data or []

    from collections import Counter

    counts: Counter = Counter()
    latest_content: Dict[str, tuple] = {}  # topic -> (created_at, content)

    for r in rows:
        cat = (r.get("category") or "").strip().lower()
        if not cat:
            continue
        counts[cat] += 1
        content = (r.get("content") or "").strip()
        created_at = r.get("created_at") or ""
        if content:
            prev = latest_content.get(cat)
            if prev is None or created_at > prev[0]:
                latest_content[cat] = (created_at, content)

    return [
        {
            "topic": topic,
            "count": count,
            "ultimo_contenido": latest_content[topic][1] if topic in latest_content else None,
        }
        for topic, count in counts.most_common()
        if count >= min_count
    ]


def deactivate_event_memories(user_id: str) -> None:
    """
    Desactiva memorias de eventos próximos de BAJA prioridad una vez que el usuario
    ya respondió sobre ellos. NO toca memorias importantes (prioridad ≥ 3), aunque
    contengan palabras como "viaje" o "cita" (ej: "Tuvo un ataque de pánico en un viaje").
    """
    try:
        res = (
            supabase.table("memories")
            .select("id, content, priority")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .lte("priority", 2)
            .execute()
        )
        rows = res.data or []
        ids_a_desactivar = [
            r["id"]
            for r in rows
            if any(p in (r.get("content") or "").lower() for p in _PALABRAS_EVENTO)
        ]
        if ids_a_desactivar:
            supabase.table("memories").update({"is_active": False}).in_("id", ids_a_desactivar).execute()
    except Exception as e:
        print(f"⚠️ No se pudieron desactivar memorias de eventos: {e}")


def get_topic_patterns_cached(
    user_id: str,
    days: int = 30,
    min_count: int = 2,
) -> List[Dict[str, Any]]:
    """
    Versión cacheada de get_topic_patterns. Evita golpear Supabase en cada mensaje.
    El caché se invalida cuando se guarda una memoria nueva (ver invalidate_patterns_cache).
    """
    now = time.time()
    cached = _PATTERNS_CACHE.get(user_id)
    if cached and cached[0] > now:
        return cached[1]

    patrones = get_topic_patterns(user_id=user_id, days=days, min_count=min_count)
    _PATTERNS_CACHE[user_id] = (now + _PATTERNS_TTL_SECONDS, patrones)
    return patrones


def invalidate_patterns_cache(user_id: str) -> None:
    """Borra el caché de patrones de un usuario (llamar al guardar una memoria nueva)."""
    _PATTERNS_CACHE.pop(user_id, None)


def get_recent_memories(
    user_id: str,
    days: int = MEMORY_WINDOW_DAYS_DEFAULT,
    max_items: int = MAX_MEMORIES_DEFAULT,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Devuelve:
      - memorias_vigentes: lista de dicts {content, priority, category} para el prompt
      - to_deactivate_ids: IDs de memorias duplicadas a desactivar (se pasa como background task)
    Lógica:
      1) Sólo memorias activas, dentro de la ventana de 'days'
      2) Por cada categoría deduplicable, conservar la de MAYOR PRIORIDAD (empate: más reciente)
      3) Categorías no deduplicables (otro) se incluyen todas
      4) Limitar a 'max_items' para el prompt
    """
    since_ts = _iso_utc(datetime.now(timezone.utc) - timedelta(days=days))

    res = (
        supabase.table("memories")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .gte("created_at", since_ts)
        .execute()
    )
    rows: List[Dict[str, Any]] = res.data or []

    # Ordenar: mayor prioridad primero; empate → más reciente primero
    rows.sort(
        key=lambda r: (r.get("priority") or 3, r.get("created_at") or ""),
        reverse=True,
    )

    CATEGORIAS_DEDUPLICABLES = {"trabajo", "estudios", "relaciones", "salud", "identidad", "emocional", "hobbies", "vida_cotidiana"}

    seen_categories: set = set()
    unique_rows: List[Dict[str, Any]] = []
    to_deactivate_ids: List[str] = []

    for row in rows:
        cat = (row.get("category") or "").strip().lower()
        if cat in CATEGORIAS_DEDUPLICABLES:
            if cat in seen_categories:
                # Perdedora (prioridad menor o más antigua): desactivar
                if row.get("id"):
                    to_deactivate_ids.append(row["id"])
                continue
            seen_categories.add(cat)

        unique_rows.append(row)

    trimmed = unique_rows[:max_items]

    memorias_vigentes: List[Dict[str, Any]] = []
    for r in trimmed:
        content = (r.get("content") or "").strip()
        if content:
            memorias_vigentes.append({
                "content":  content,
                "priority": r.get("priority") or 3,
                "category": (r.get("category") or "otro").strip().lower(),
            })

    return memorias_vigentes, to_deactivate_ids