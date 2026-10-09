from app.core.db import supabase
from app.core.retry import with_retry


class UserRepository:

    def get_profile(self, user_id: str) -> dict:
        response = supabase.table("users_profiles") \
            .select("*") \
            .eq("id", user_id) \
            .execute()

        if not response.data:
            return {"onboarding_completo": False}

        return response.data[0]

    def upsert_profile(self, user_id: str, data: dict) -> None:
        with_retry(lambda: supabase.table("users_profiles").upsert({
            "id": user_id,
            **data,
        }).execute())

    def create_profile_if_missing(self, user_id: str) -> None:
        existing = supabase.table("users_profiles") \
            .select("id") \
            .eq("id", user_id) \
            .execute()

        if not existing.data:
            with_retry(lambda: supabase.table("users_profiles").insert({
                "id": user_id,
                "onboarding_completo": False,
                "nombre": "",
            }).execute())

    def save_onboarding_answers(self, user_id: str, answers: list[dict]) -> None:
        supabase.table("onboarding_answers").insert(answers).execute()

    def delete_all_user_data(self, user_id: str) -> None:
        # Datos del usuario: se borran por completo. (memories, conversations,
        # onboarding_answers y exercise_ratings también caerían por ON DELETE
        # CASCADE al borrar el perfil, pero los borramos explícito igual;
        # daily_checkins, user_notifications, crisis_logs y crisis_pendientes NO
        # tienen cascade, así que acá es la única vía.)
        supabase.table("memories").delete().eq("user_id", user_id).execute()
        supabase.table("conversations").delete().eq("user_id", user_id).execute()
        supabase.table("daily_checkins").delete().eq("user_id", user_id).execute()
        supabase.table("onboarding_answers").delete().eq("user_id", user_id).execute()
        supabase.table("user_notifications").delete().eq("user_id", user_id).execute()
        supabase.table("crisis_logs").delete().eq("user_id", user_id).execute()
        supabase.table("crisis_pendientes").delete().eq("user_id", user_id).execute()

        # Feedback: se conserva para métricas pero desvinculado del usuario
        # (user_id → NULL). Ya no queda ningún dato identificable.
        supabase.table("user_feedback").update({"user_id": None}).eq("user_id", user_id).execute()

        # Perfil (dispara el CASCADE de las tablas con FK).
        supabase.table("users_profiles").delete().eq("id", user_id).execute()

        # Registro de Supabase Auth: saca el email y el UUID de auth.users.
        # Requiere service key. Va al final para que un fallo acá no deje datos
        # del usuario sin borrar (el resto ya se limpió).
        supabase.auth.admin.delete_user(user_id)