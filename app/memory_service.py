# app/memory_service.py
from __future__ import annotations
import time
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple, Dict, Any
from app.core.db import supabase

# Parámetros por defecto (podés ajustarlos)
MEMORY_WINDOW_DAYS_DEFAULT = 30
MAX_MEMORIES_DEFAULT = 20

# Caché en memoria de patrones por usuario.
# Clave: user_id → (expires_at_epoch, lista_de_patrones)
_PATTERNS_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_PATTERNS_TTL_SECONDS = 300  # 5 minutos

# Caché del check-in del día por usuario.
# Clave: (user_id, fecha_iso) → (expires_at_epoch, mood_value | None)
_CHECKIN_CACHE: Dict[Tuple[str, str], Tuple[float, Optional[int]]] = {}
_CHECKIN_TTL_SECONDS = 300  # 5 minutos

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


# Formato exacto que produce detectar_evento_proximo: "Tiene <evento> <tiempo>."
_RE_MEMORIA_RESPALDO_EVENTO = None  # se compila lazy abajo


def _es_memoria_respaldo_evento(contenido: str) -> bool:
    global _RE_MEMORIA_RESPALDO_EVENTO
    if _RE_MEMORIA_RESPALDO_EVENTO is None:
        import re
        eventos = "|".join(re.escape(e) for e in _PALABRAS_EVENTO)
        tiempos = "|".join(re.escape(t) for t in _PALABRAS_TIEMPO)
        _RE_MEMORIA_RESPALDO_EVENTO = re.compile(
            rf"^tiene ({eventos}) ({tiempos})\.$", re.IGNORECASE
        )
    return bool(_RE_MEMORIA_RESPALDO_EVENTO.match(contenido.strip()))


def deactivate_event_memories(user_id: str) -> None:
    """
    Desactiva las memorias-respaldo de eventos próximos ("Tiene final este
    finde.") una vez que el usuario ya respondió sobre ellos.

    Solo toca memorias que tienen EXACTAMENTE el formato del respaldo
    (detectar_evento_proximo): antes alcanzaba con que una memoria de baja
    prioridad contuviera "viaje" o "cita" y se desactivaban memorias legítimas.
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
            if _es_memoria_respaldo_evento(r.get("content") or "")
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


def get_checkin_hoy_cached(user_id: str) -> Optional[int]:
    """
    Devuelve el mood_value (1-4) del check-in de hoy del usuario, o None si no hizo.
    Cacheado 5 min para no golpear Supabase en cada mensaje del chat.
    """
    hoy = date.today().isoformat()
    key = (user_id, hoy)
    now = time.time()
    cached = _CHECKIN_CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]

    res = (
        supabase.table("daily_checkins")
        .select("mood_value")
        .eq("user_id", user_id)
        .eq("checkin_date", hoy)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    valor = rows[0].get("mood_value") if rows else None
    _CHECKIN_CACHE[key] = (now + _CHECKIN_TTL_SECONDS, valor)
    return valor


def invalidate_checkin_cache(user_id: str) -> None:
    """Borra el caché del check-in de hoy (llamar al guardar un check-in nuevo)."""
    _CHECKIN_CACHE.pop((user_id, date.today().isoformat()), None)


def get_recent_memories(
    user_id: str,
    days: int = MEMORY_WINDOW_DAYS_DEFAULT,
    max_items: int = MAX_MEMORIES_DEFAULT,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Devuelve:
      - memorias_vigentes: lista de dicts {content, priority, category} para el prompt
      - to_deactivate_ids: IDs de memorias sobrantes a desactivar (se pasa como background task)
    Lógica:
      1) Sólo memorias activas, dentro de la ventana de 'days'
      2) Por cada categoría deduplicable, conservar hasta MAX_POR_CATEGORIA memorias
         (orden: mayor prioridad primero; empate → más reciente)
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
    MAX_POR_CATEGORIA = 3

    from collections import Counter
    category_counts: Counter = Counter()
    unique_rows: List[Dict[str, Any]] = []
    to_deactivate_ids: List[str] = []

    for row in rows:
        cat = (row.get("category") or "").strip().lower()
        if cat in CATEGORIAS_DEDUPLICABLES:
            if category_counts[cat] >= MAX_POR_CATEGORIA:
                # Ya hay MAX_POR_CATEGORIA memorias mejores de esta categoría
                if row.get("id"):
                    to_deactivate_ids.append(row["id"])
                continue
            category_counts[cat] += 1

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


def get_dias_inactivo(user_id: str) -> int:
    """
    Devuelve cuántos días lleva el usuario sin generar una conversación.
    Consulta el mensaje de assistant más reciente en la tabla conversations.
    Devuelve 0 si tuvo actividad hoy, o si no hay historial.
    """
    try:
        res = (
            supabase.table("conversations")
            .select("created_at")
            .eq("user_id", user_id)
            .eq("role", "assistant")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return 0
        ultima = rows[0].get("created_at", "")
        if not ultima:
            return 0
        # Parsear timestamp ISO (con o sin timezone)
        ultima_dt = datetime.fromisoformat(ultima.replace("Z", "+00:00"))
        ahora = datetime.now(timezone.utc)
        delta = ahora - ultima_dt
        return max(0, delta.days)
    except Exception as e:
        print(f"⚠️ get_dias_inactivo error: {e}")
        return 0


# ════════════════════════════════════════════════════════════════════
# MEMORIA PROACTIVA — eventos con fecha
# ════════════════════════════════════════════════════════════════════
# Un "event memory" es una fila de memories con event_date no nula. Esta sección
# resuelve fechas relativas a fechas reales, recupera los eventos relevantes para
# el contexto de hoy (get_proactive_memories), marca follow-ups y arma el texto de
# los push contextuales.

import re as _re

_DIAS_SEMANA = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}

# números escritos (para "en dos semanas", "dentro de un mes")
_NUMEROS_PALABRA = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}


def _next_weekday(hoy: date, target_wd: int) -> date:
    """Próxima ocurrencia de un día de la semana (1-7 días adelante; nunca hoy)."""
    delta = (target_wd - hoy.weekday()) % 7
    if delta == 0:
        delta = 7
    return hoy + timedelta(days=delta)


def _num_en_texto(texto: str) -> Optional[int]:
    """Extrae el primer número (dígito o palabra) de un fragmento como '2 semanas'."""
    m = _re.search(r"\b(\d{1,3})\b", texto)
    if m:
        return int(m.group(1))
    for palabra, valor in _NUMEROS_PALABRA.items():
        if _re.search(rf"\b{palabra}\b", texto):
            return valor
    return None


def resolver_fecha_relativa(texto: str, hoy: Optional[date] = None) -> Optional[date]:
    """
    Convierte expresiones temporales en español rioplatense a una fecha real.
    Entiende: hoy, mañana, pasado mañana, este/el <día>, el <día> que viene,
    la semana que viene, en N días/semanas, dentro de un mes, este finde, etc.
    Devuelve None si no encuentra una referencia temporal futura clara.
    """
    if hoy is None:
        hoy = date.today()
    t = (texto or "").lower()
    t = t.translate(str.maketrans("", "", ""))  # no-op, mantiene tildes

    # Orden importa: lo más específico primero.
    if "pasado mañana" in t or "pasado manana" in t:
        return hoy + timedelta(days=2)

    # "en/dentro de N días|semanas|mes(es)"
    m = _re.search(r"(?:en|dentro de)\s+([\wáéíóú]+)\s*(día|dia|días|dias|semana|semanas|mes|meses)", t)
    if m:
        n = _num_en_texto(m.group(1)) or (1 if m.group(1) in ("un", "una") else None)
        unidad = m.group(2)
        if n:
            if unidad.startswith("día") or unidad.startswith("dia"):
                return hoy + timedelta(days=n)
            if unidad.startswith("semana"):
                return hoy + timedelta(days=7 * n)
            if unidad.startswith("mes"):
                return hoy + timedelta(days=30 * n)
    # "en un mes" / "dentro de un mes" sin número explícito ya cubierto arriba.

    if _re.search(r"\b(la\s+)?(semana|finde|fin de semana)\s+(que viene|próxim|proxim|entrante)", t) \
       or "la semana que viene" in t or "la próxima semana" in t or "la proxima semana" in t:
        if "finde" in t or "fin de semana" in t:
            return _next_weekday(hoy, 5) + timedelta(days=7)  # sábado de la semana próxima
        return hoy + timedelta(days=7)

    if "este finde" in t or "el finde" in t or "este fin de semana" in t or "el fin de semana" in t:
        return _next_weekday(hoy, 5)  # próximo sábado

    # Día de la semana nombrado (con o sin "que viene")
    for nombre, wd in _DIAS_SEMANA.items():
        if _re.search(rf"\b{nombre}\b", t):
            fecha = _next_weekday(hoy, wd)
            if _re.search(rf"{nombre}\s+(que viene|próxim|proxim|entrante)", t):
                # "el viernes que viene" = el de la semana próxima
                if (fecha - hoy).days <= 7:
                    fecha += timedelta(days=7)
            return fecha

    if "mañana" in t or "manana" in t:
        return hoy + timedelta(days=1)

    if "esta semana" in t:
        # ambiguo: lo dejamos a 3 días vista como aproximación
        return hoy + timedelta(days=3)

    if "hoy" in t or "esta noche" in t or "esta tarde" in t:
        return hoy

    if "el mes que viene" in t or "el próximo mes" in t or "el proximo mes" in t:
        return hoy + timedelta(days=30)

    return None


def parse_fecha_llm(valor: Any) -> Optional[date]:
    """Parsea una fecha YYYY-MM-DD que el LLM puede haber devuelto. None si no es válida."""
    if not valor or not isinstance(valor, str):
        return None
    try:
        return date.fromisoformat(valor.strip()[:10])
    except (ValueError, TypeError):
        return None


def _titulo_evento(content: str, evento_kw: str) -> str:
    """Arma un título corto a partir del contenido de la memoria respaldo."""
    return content.rstrip(".").strip() or evento_kw


def detectar_evento_con_fecha(mensaje: str, hoy: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """
    Respaldo heurístico cuando el LLM no extrae el evento: detecta el tipo de
    evento + la fecha real. Devuelve {content, category, priority, event_title,
    event_date} o None.
    """
    if hoy is None:
        hoy = date.today()
    texto = mensaje.lower()
    if not any(p in texto for p in _PALABRAS_TIEMPO):
        return None
    fecha = resolver_fecha_relativa(mensaje, hoy)
    if not fecha:
        return None
    for evento, (categoria, prioridad) in _EVENTOS_CATEGORIA.items():
        if evento in texto:
            return {
                "content": f"Tiene {evento}.",
                "category": categoria,
                "priority": prioridad,
                "event_title": evento,
                "event_date": fecha.isoformat(),
            }
    return None


# ── Clasificación de proximidad ───────────────────────────────────────────────
# bucket → prioridad de surfacing (mayor = más urgente para mencionar)
def _clasificar_evento(days_until: int, followed_up: bool) -> Optional[Tuple[str, int]]:
    """
    Mapea la distancia en días a un bucket + prioridad. None = ignorar.
    days_until > 0 futuro, == 0 hoy, < 0 pasado.
    """
    # Si el usuario ya habló del evento (follow-up hecho), no se vuelve a traer nunca.
    if followed_up:
        return None
    if days_until == 0:
        return ("hoy", 100)
    if days_until == 1:
        return ("manana", 80)
    if 2 <= days_until <= 7:
        return ("proximo", 50)
    if days_until == -1:
        return ("ayer", 100)
    if -3 <= days_until <= -2:
        return ("reciente", 50)
    return None  # futuro lejano (>7) o pasado viejo (<-3)


def get_proactive_memories(
    user_id: str,
    hoy: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """
    Devuelve los eventos relevantes para el contexto de HOY, ordenados por
    prioridad de surfacing (más urgente primero). Cada item:
    {id, event_title, content, event_date, days_until, bucket, prioridad,
     followed_up, importance}.

    Reglas (req. 4):
      hoy → máxima · mañana → alta · 2-7 días → media ·
      ayer (sin follow-up) → máxima · 2-3 días atrás (sin follow-up) → media ·
      evento viejo o ya seguido → se ignora.
    """
    if hoy is None:
        hoy = date.today()
    desde = (hoy - timedelta(days=4)).isoformat()   # margen para follow-ups
    hasta = (hoy + timedelta(days=8)).isoformat()   # margen para eventos próximos

    try:
        res = (
            supabase.table("memories")
            .select("id, content, event_title, event_date, followed_up, priority, category")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .not_.is_("event_date", "null")
            .gte("event_date", desde)
            .lte("event_date", hasta)
            .execute()
        )
    except Exception as e:
        print(f"⚠️ get_proactive_memories error: {e}")
        return []

    eventos: List[Dict[str, Any]] = []
    for r in res.data or []:
        ev_date = parse_fecha_llm(r.get("event_date"))
        if not ev_date:
            continue
        days_until = (ev_date - hoy).days
        followed_up = bool(r.get("followed_up"))
        clasif = _clasificar_evento(days_until, followed_up)
        if not clasif:
            continue
        bucket, prioridad = clasif
        eventos.append({
            "id":          r["id"],
            "event_title": (r.get("event_title") or r.get("content") or "").strip().rstrip("."),
            "content":     (r.get("content") or "").strip(),
            "event_date":  ev_date.isoformat(),
            "days_until":  days_until,
            "bucket":      bucket,
            "prioridad":   prioridad,
            "followed_up": followed_up,
            "importance":  r.get("priority") or 3,
        })

    # Más urgente primero; a igual urgencia, el de mayor importancia.
    eventos.sort(key=lambda e: (e["prioridad"], e["importance"]), reverse=True)
    return eventos


def marcar_evento_followup(user_id: str, mensaje: str, hoy: Optional[date] = None) -> None:
    """
    Si el usuario habló de un evento que ya ocurrió (o de hoy), lo marca como
    followed_up=true para no volver a preguntar (req. 6). Background-task.

    Detección: solapamiento de palabras entre el mensaje y el título del evento.
    """
    if hoy is None:
        hoy = date.today()
    try:
        res = (
            supabase.table("memories")
            .select("id, event_title, content, event_date")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .eq("followed_up", False)
            .not_.is_("event_date", "null")
            .lte("event_date", hoy.isoformat())  # solo eventos ya ocurridos o de hoy
            .gte("event_date", (hoy - timedelta(days=4)).isoformat())
            .execute()
        )
    except Exception as e:
        print(f"⚠️ marcar_evento_followup error: {e}")
        return

    palabras_msg = {
        w for w in _re.sub(r"[^\wáéíóúñ ]", " ", mensaje.lower()).split()
        if len(w) > 3
    }
    if not palabras_msg:
        return

    ids: List[str] = []
    for r in res.data or []:
        titulo = (r.get("event_title") or r.get("content") or "").lower()
        palabras_ev = {w for w in _re.sub(r"[^\wáéíóúñ ]", " ", titulo).split() if len(w) > 3}
        if palabras_ev and (palabras_ev & palabras_msg):
            ids.append(r["id"])

    if ids:
        try:
            supabase.table("memories").update({"followed_up": True}).in_("id", ids).execute()
        except Exception as e:
            print(f"⚠️ no se pudo marcar followed_up: {e}")


def marcar_proactivo_insertado(memory_id: str) -> None:
    """Registra que un evento se insertó en el prompt como mención proactiva (cooldown)."""
    if not memory_id:
        return
    try:
        supabase.table("memories").update(
            {"last_proactive_at": _iso_utc(datetime.now(timezone.utc))}
        ).eq("id", memory_id).execute()
    except Exception as e:
        print(f"⚠️ no se pudo marcar last_proactive_at: {e}")


# ── Push contextual ───────────────────────────────────────────────────────────
_PUSH_COOLDOWN_HORAS = 20  # un push por evento por ventana, anti-spam (req. 8)


def _texto_push_evento(ev: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Arma (push_type, body) para un evento según su bucket. None si no aplica."""
    titulo = ev["event_title"]
    bucket = ev["bucket"]
    if bucket == "hoy":
        return ("reminder", f"Hoy tenés {titulo}. Mucha suerte 🍀")
    if bucket == "manana":
        return ("reminder", f"Mañana tenés {titulo}. ¿Cómo te sentís?")
    if bucket == "ayer":
        return ("followup", f"¿Cómo te fue con {titulo}?")
    if bucket == "proximo" and ev["importance"] >= 4:
        return ("reminder", f"Me acordé de que esta semana tenías {titulo}. Te deseo lo mejor.")
    if bucket == "reciente":
        return ("followup", f"Me quedó la duda… ¿cómo salió {titulo}?")
    return None


def construir_push_contextual(user_id: str, hoy: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """
    Devuelve {title, body, memory_id, push_type} para el evento más relevante del
    usuario, respetando anti-spam (no reenvía el mismo tipo de push por evento).
    None → no hay evento contextual; el caller usa el push genérico.
    """
    if hoy is None:
        hoy = date.today()
    eventos = get_proactive_memories(user_id, hoy)
    if not eventos:
        return None

    # Necesitamos las flags de push para no repetir.
    ids = [e["id"] for e in eventos]
    try:
        res = (
            supabase.table("memories")
            .select("id, reminder_push_sent, followup_push_sent")
            .in_("id", ids)
            .execute()
        )
        flags = {r["id"]: r for r in (res.data or [])}
    except Exception as e:
        print(f"⚠️ construir_push_contextual flags error: {e}")
        flags = {}

    for ev in eventos:  # ya vienen ordenados por urgencia
        texto = _texto_push_evento(ev)
        if not texto:
            continue
        push_type, body = texto
        f = flags.get(ev["id"], {})
        if push_type == "reminder" and f.get("reminder_push_sent"):
            continue
        if push_type == "followup" and f.get("followup_push_sent"):
            continue
        return {
            "title":     "Numa 🐼",
            "body":      body,
            "memory_id": ev["id"],
            "push_type": push_type,
        }
    return None


def marcar_push_enviado(memory_id: str, push_type: str) -> None:
    """Marca reminder_push_sent / followup_push_sent tras enviar el push (anti-spam)."""
    if not memory_id:
        return
    campo = "reminder_push_sent" if push_type == "reminder" else "followup_push_sent"
    try:
        supabase.table("memories").update({campo: True}).eq("id", memory_id).execute()
    except Exception as e:
        print(f"⚠️ no se pudo marcar {campo}: {e}")