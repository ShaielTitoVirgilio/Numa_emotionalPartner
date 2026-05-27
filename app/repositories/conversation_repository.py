import re
from typing import List, Dict, Any, Optional
from app.core.db import supabase

_MINIMO_CHARS = 20

_PATRONES_INVALIDOS = [
    # Estado emocional puro sin contexto adicional
    r"^(el usuario |la persona )?(está|se siente|parece|se ve) (triste|mal|bien|cansad[oa]|ansios[oa]|angustiad[oa]|preocupad[oa]|deprimid[oa]|abrumad[oa])\.?$",
    # Menciones vagas sin hecho concreto
    r"^(mencionó|dijo|comentó|expresó) (algo|problemas|cosas|temas|situaciones|que está)",
    # Fragmentos sin verbo ni sujeto
    r"^[a-záéíóúñü\s]+$",  # solo palabras sueltas sin puntuación ni estructura
]

_RE_INVALIDOS = [re.compile(p, re.IGNORECASE) for p in _PATRONES_INVALIDOS]


def _es_memoria_valida(contenido: str) -> bool:
    texto = contenido.strip()
    if len(texto) < _MINIMO_CHARS:
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

        rows = [
            {
                "user_id":   user_id,
                "content":   m["content"],
                "category":  m.get("category") or "otro",
                "source":    "chat",
                "is_active": True,
                "priority":  m.get("priority") or 3,
            }
            for m in (memorias or [])
            if _es_memoria_valida(m.get("content") or "")
        ]
        if rows:
            supabase.table("memories").insert(rows).execute()

    def deactivate_memories(self, ids: list[str]) -> None:
        if not ids:
            return
        supabase.table("memories").update({"is_active": False}).in_("id", ids).execute()
