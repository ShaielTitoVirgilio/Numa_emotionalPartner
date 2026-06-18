import re
from typing import List, Dict, Any, Optional
from app.core.db import supabase

_MINIMO_CHARS = 20
_MINIMO_PALABRAS = 4

_PATRONES_INVALIDOS = [
    # Estado emocional puro sin contexto adicional
    r"^(el usuario |la usuaria |la persona )?(está|esta|se siente|parece|se ve) (muy |un poco |bastante )?(triste|mal|bien|cansad[oa]|ansios[oa]|angustiad[oa]|preocupad[oa]|deprimid[oa]|abrumad[oa])\.?$",
    # Menciones vagas sin hecho concreto
    r"^(mencionó|menciono|dijo|comentó|comento|expresó|expreso) (algo|problemas|cosas|temas|situaciones|que está|que esta)",
]

_RE_INVALIDOS = [re.compile(p, re.IGNORECASE) for p in _PATRONES_INVALIDOS]


def _es_memoria_valida(contenido: str) -> bool:
    """Filtra memorias basura sin descartar oraciones válidas.

    El filtro anterior incluía el patrón ^[a-záéíóúñü\\s]+$ que rechazaba
    CUALQUIER oración sin puntuación interna ("Vive sola con su gata Mora")
    → las memorias llegaban al cliente pero nunca se persistían. Ahora se
    exige longitud y cantidad mínima de palabras, sin penalizar la falta
    de puntuación.
    """
    texto = contenido.strip()
    if len(texto) < _MINIMO_CHARS:
        return False
    if len(texto.split()) < _MINIMO_PALABRAS:
        return False
    if any(r.search(texto) for r in _RE_INVALIDOS):
        return False
    return True


class ConversationRepository:

    def save(
        self,
        user_id: str,
        user_msg: str,
        assistant_msg: str,
        memorias: List[Dict[str, Any]],
        mood: Optional[str] = None,
    ) -> None:
        supabase.table("conversations").insert([
            {"user_id": user_id, "role": "user",      "content": user_msg},
            {"user_id": user_id, "role": "assistant", "content": assistant_msg, "mood": mood},
        ]).execute()

        rows = []
        for m in (memorias or []):
            tiene_evento = bool(m.get("event_date") and m.get("event_title"))
            # Las memorias de evento valen por su fecha aunque el content sea corto
            # ("Tiene examen."); el resto pasa por el filtro anti-basura habitual.
            if not tiene_evento and not _es_memoria_valida(m.get("content") or ""):
                continue
            row = {
                "user_id":   user_id,
                "content":   m["content"],
                "category":  m.get("category") or "otro",
                "source":    "chat",
                "is_active": True,
                "priority":  m.get("priority") or 3,
            }
            # Memoria proactiva: si trae un evento con fecha, persistimos sus campos.
            if m.get("event_date") and m.get("event_title"):
                row["event_date"] = m["event_date"]
                row["event_title"] = m["event_title"]
            rows.append(row)
        if rows:
            supabase.table("memories").insert(rows).execute()

    def deactivate_memories(self, ids: list[str]) -> None:
        if not ids:
            return
        supabase.table("memories").update({"is_active": False}).in_("id", ids).execute()

    def get_recent_messages(self, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Últimos mensajes del usuario para rehidratar el chat al abrir la app.
        Excluye los mensajes técnicos de feedback post-ejercicio."""
        res = (
            supabase.table("conversations")
            .select("role, content, mood, created_at")
            .eq("user_id", user_id)
            .not_.like("content", "[Post-ejercicio%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = res.data or []
        rows.reverse()  # devolver en orden cronológico
        return rows
