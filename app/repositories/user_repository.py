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