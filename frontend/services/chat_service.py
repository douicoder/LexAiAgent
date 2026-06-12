from utils.api_client import APIClient


class ChatService:
    def __init__(self, token: str):
        self.client = APIClient(token=token)

    def send_message(
        self,
        case_id: str,
        message: str,
        history: list[dict] | None = None,
        current_notice_draft: str = "",
    ) -> dict:
        return self.client.post(
            "/agent/chat",
            {
                "case_id": case_id,
                "message": message,
                "history": history or [],
                "current_notice_draft": current_notice_draft,
            },
        )

    def execute_action(
        self,
        case_id: str,
        step_number: int,
        collected_info: dict | None = None,
    ) -> dict:
        return self.client.post(
            "/agent/execute",
            {
                "case_id": case_id,
                "step_number": step_number,
                "collected_info": collected_info or {},
                "message": "",
            },
        )
