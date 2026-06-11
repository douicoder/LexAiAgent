import uuid

from fastapi import HTTPException, status
from supabase import create_client

from app.config import settings


class SupabaseService:
    def __init__(self):
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Supabase not configured",
            )
        self.client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

    # ── Users ────────────────────────────────────────────────

    def get_user(self, user_id: str) -> dict | None:
        result = self.client.table("users").select("*").eq("id", user_id).execute()
        return result.data[0] if result.data else None

    def create_user(self, user_id: str, email: str, hashed_password: str, full_name: str, preferred_language: str) -> dict:
        data = {
            "id": user_id,
            "email": email,
            "hashed_password": hashed_password,
            "full_name": full_name,
            "preferred_language": preferred_language,
        }
        result = self.client.table("users").insert(data).execute()
        return result.data[0]

    def get_user_by_email(self, email: str) -> dict | None:
        result = self.client.table("users").select("id").eq("email", email).execute()
        return result.data[0] if result.data else None

    # ── Cases ────────────────────────────────────────────────

    def create_case(self, data: dict) -> dict:
        result = self.client.table("cases").insert(data).execute()
        return result.data[0]

    def get_case(self, case_id: str, user_id: str) -> dict | None:
        result = (
            self.client.table("cases")
            .select("*")
            .eq("id", case_id)
            .eq("user_id", user_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_case_by_id(self, case_id: str) -> dict | None:
        result = self.client.table("cases").select("*").eq("id", case_id).execute()
        return result.data[0] if result.data else None

    def update_case(self, case_id: str, data: dict) -> dict:
        result = self.client.table("cases").update(data).eq("id", case_id).execute()
        return result.data[0]

    def list_cases(self, user_id: str) -> list[dict]:
        result = (
            self.client.table("cases")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data

    def delete_case(self, case_id: str, user_id: str) -> bool:
        result = (
            self.client.table("cases")
            .delete()
            .eq("id", case_id)
            .eq("user_id", user_id)
            .execute()
        )
        return len(result.data) > 0

    def count_cases(self, user_id: str) -> int:
        result = (
            self.client.table("cases")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        return result.count if hasattr(result, "count") else len(result.data)

    # ── Case Messages ────────────────────────────────────────

    def add_message(self, case_id: str, role: str, content: str, extra_data: dict | None = None) -> dict:
        data = {
            "id": str(uuid.uuid4()),
            "case_id": case_id,
            "role": role,
            "content": content,
            "extra_data": extra_data or {},
        }
        result = self.client.table("case_messages").insert(data).execute()
        return result.data[0]

    def get_messages(self, case_id: str) -> list[dict]:
        result = (
            self.client.table("case_messages")
            .select("*")
            .eq("case_id", case_id)
            .order("created_at", desc=False)
            .execute()
        )
        return result.data
