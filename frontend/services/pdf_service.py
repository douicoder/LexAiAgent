from utils.api_client import APIClient


class PdfService:
    def __init__(self, token: str):
        self.client = APIClient(token=token)

    def generate(self, case_id: str) -> dict:
        return self.client.post(f"/cases/{case_id}/pdf")
