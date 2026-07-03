from datetime import datetime, timedelta, timezone
from typing import Optional
from app.core.db import supabase


class FeedbackRepository:

    def save_feedback(self, data: dict) -> None:
        row = {k: v for k, v in data.items() if v is not None}
        supabase.table("user_feedback").insert(row).execute()

    def get_feedback(self, limit: int) -> list:
        return supabase.table("user_feedback") \
            .select("id, created_at, user_id, texto, rating, rating_recomendaria") \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute().data

    def save_exercise_rating(self, user_id: str, exercise_id: str, rating: int, valor_texto: Optional[str]) -> None:
        supabase.table("exercise_ratings").insert({
            "user_id":     user_id,
            "exercise_id": exercise_id,
            "rating":      rating,
            "valor_texto": valor_texto,
        }).execute()

    def save_crisis_log(self, user_id: Optional[str], mensaje: str, category: str, log_level: str) -> None:
        supabase.table("crisis_logs").insert({
            "user_id":         user_id,
            "mensaje_usuario": mensaje[:500],
            "categoria":       category,
            "log_level":       log_level,
        }).execute()



    def hay_crisis_reciente(self, user_id: str, minutos: int = 45) -> bool:
        """True si el usuario tuvo un evento de crisis logueado hace poco.

        Respaldo para el modo post-contención (M21): la señal por historial del
        request es stateless y se pierde si el usuario recarga la app en medio
        de una conversación difícil. Esta consulta la recupera desde crisis_logs.
        """
        try:
            desde = (datetime.now(timezone.utc) - timedelta(minutes=minutos)).isoformat()
            res = (
                supabase.table("crisis_logs")
                .select("id")
                .eq("user_id", user_id)
                .gte("created_at", desde)
                .limit(1)
                .execute()
            )
            return bool(res.data)
        except Exception:
            return False

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
