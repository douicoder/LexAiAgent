from utils.api_client import APIClient


class CaseService:
    def __init__(self, token: str):
        self.client = APIClient(token=token)

    def create_case(self, description: str, language: str = "en") -> dict:
        return self.client.post(
            "/cases",
            {"description": description, "language": language},
        )

    def list_cases(self) -> dict:
        return self.client.get("/cases")

    def get_case(self, case_id: str) -> dict:
        return self.client.get(f"/cases/{case_id}")

    def delete_case(self, case_id: str) -> dict:
        return self.client.delete(f"/cases/{case_id}")

    def get_messages(self, case_id: str) -> list:
        return self.client.get(f"/cases/{case_id}/messages")

    def get_documents(self, case_id: str) -> list:
        return self.client.get(f"/cases/{case_id}/documents")

    def update_document(self, case_id: str, doc_id: str, content: str, status: str = "draft") -> dict:
        return self.client.put(f"/cases/{case_id}/documents/{doc_id}", {"content": content, "status": status})

    def preview_document(self, case_id: str, doc_id: str) -> bytes:
        return self.client.get_raw(f"/cases/{case_id}/documents/{doc_id}/preview")
