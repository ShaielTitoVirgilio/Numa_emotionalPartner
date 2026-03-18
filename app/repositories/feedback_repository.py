from typing import Optional
from app.core.db import supabase


class FeedbackRepository:

    def save_feedback(self, data: dict) -> None:
        row = {k: v for k, v in data.items() if v is not None}
        supabase.table("user_feedback").insert(row).execute()

    def save_survey(self, data: dict) -> None:
        supabase.table("surveys").insert(data).execute()

    def get_feedback(self, limit: int, categoria: Optional[str]) -> list:
        query = supabase.table("user_feedback") \
            .select("id, created_at, user_id, texto, categoria, rating, audio_mime, app_version") \
            .order("created_at", desc=True) \
            .limit(limit)

        if categoria:
            query = query.eq("categoria", categoria)

        return query.execute().data

    def save_crisis_log(self, user_id: Optional[str], mensaje: str, category: str, log_level: str) -> None:
        supabase.table("crisis_logs").insert({
            "user_id":         user_id,
            "mensaje_usuario": mensaje[:500],
            "categoria":       category,
            "log_level":       log_level,
        }).execute()



    def get_feedback_audio(self, feedback_id: str) -> dict:
        res = supabase.table("user_feedback") \
            .select("audio_base64, audio_mime") \
            .eq("id", feedback_id) \
            .single() \
            .execute()
        return res.data

    def get_crisis_logs(self, limit: int, solo_pendientes: bool) -> list:
        query = supabase.table("crisis_logs") \
            .select("id, created_at, user_id, categoria, log_level, revisado") \
            .order("created_at", desc=True) \
            .limit(limit)
        if solo_pendientes:
            query = query.eq("revisado", False)
        return query.execute().data

    def marcar_crisis_revisada(self, crisis_id: str) -> None:
        supabase.table("crisis_logs").update({"revisado": True}).eq("id", crisis_id).execute()
