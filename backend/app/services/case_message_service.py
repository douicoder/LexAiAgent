from fastapi import HTTPException

from app.services.supabase_db import SupabaseService


class CaseMessageService:
    def __init__(self, supabase: SupabaseService):
        self.supabase = supabase

    def add_message(self, case_id: str, role: str, content: str, extra_data: dict | None = None) -> dict:
        return self.supabase.add_message(case_id, role, content, extra_data)

    def get_messages(self, case_id: str, user_id: str) -> list[dict]:
        case = self.supabase.get_case(case_id, user_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        return self.supabase.get_messages(case_id)
