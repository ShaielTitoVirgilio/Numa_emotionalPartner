from typing import Optional
from app.core.db import supabase


class ConversationRepository:

    def save(
        self,
        user_id: str,
        user_msg: str,
        assistant_msg: str,
        memoria: Optional[str],
        memory_category: Optional[str] = None,
        mood: Optional[str] = None,
    ) -> None:
        supabase.table("conversations").insert([
            {"user_id": user_id, "role": "user",      "content": user_msg},
            {"user_id": user_id, "role": "assistant", "content": assistant_msg, "mood": mood},
        ]).execute()

        if memoria:
            supabase.table("memories").insert({
                "user_id":   user_id,
                "content":   memoria,
                "category":  memory_category or "otro",
                "source":    "chat",
                "is_active": True,
            }).execute()

    def deactivate_memories(self, ids: list[str]) -> None:
        if not ids:
            return
        supabase.table("memories").update({"is_active": False}).in_("id", ids).execute()