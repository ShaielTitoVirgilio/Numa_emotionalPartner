from typing import Optional
from app.core.db import supabase

CATEGORIAS_DEDUPLICABLES = {"trabajo", "estudios", "relaciones", "salud", "identidad", "emocional", "hobbies", "vida_cotidiana"}


class ConversationRepository:

    def save(
        self,
        user_id: str,
        user_msg: str,
        assistant_msg: str,
        memoria: Optional[str],
        memory_category: Optional[str] = None,
        mood: Optional[str] = None,
        memory_priority: Optional[int] = None,
    ) -> None:
        supabase.table("conversations").insert([
            {"user_id": user_id, "role": "user",      "content": user_msg},
            {"user_id": user_id, "role": "assistant", "content": assistant_msg, "mood": mood},
        ]).execute()

        if memoria:
            priority = memory_priority or 3
            category = memory_category or "otro"

            if category in CATEGORIAS_DEDUPLICABLES:
                try:
                    existing = (
                        supabase.table("memories")
                        .select("id, priority")
                        .eq("user_id", user_id)
                        .eq("category", category)
                        .eq("is_active", True)
                        .order("priority", desc=True)
                        .limit(1)
                        .execute()
                    )
                    if existing.data:
                        existing_priority = existing.data[0].get("priority") or 3
                        if priority > existing_priority:
                            supabase.table("memories").update({"is_active": False}).eq("id", existing.data[0]["id"]).execute()
                except Exception as e:
                    print(f"⚠️ Error al verificar prioridad de memoria existente: {e}")

            supabase.table("memories").insert({
                "user_id":   user_id,
                "content":   memoria,
                "category":  category,
                "source":    "chat",
                "is_active": True,
                "priority":  priority,
            }).execute()

    def deactivate_memories(self, ids: list[str]) -> None:
        if not ids:
            return
        supabase.table("memories").update({"is_active": False}).in_("id", ids).execute()
