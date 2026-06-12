from utils.api_client import APIClient, APIError


class AuthService:
    def __init__(self, token: str | None = None):
        self.client = APIClient(token=token)

    def register(
        self,
        email: str,
        password: str,
        full_name: str,
        preferred_language: str = "en",
    ) -> dict:
        return self.client.post(
            "/auth/register",
            {
                "email": email,
                "password": password,
                "full_name": full_name,
                "preferred_language": preferred_language,
            },
            auth=False,
        )

    def login(self, email: str, password: str) -> dict:
        return self.client.post(
            "/auth/login",
            {"email": email, "password": password},
            auth=False,
        )

    def get_profile(self) -> dict:
        return self.client.get("/auth/me")
