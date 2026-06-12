from typing import Any

import requests
from flask import current_app


class APIError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class APIClient:
    def __init__(self, token: str | None = None):
        self.base_url = current_app.config["API_BASE_URL"]
        self.token = token

    def _headers(self, auth: bool = True) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _handle_response(self, response: requests.Response) -> Any:
        if response.status_code >= 400:
            detail = "Request failed"
            try:
                body = response.json()
                detail = body.get("detail", detail)
                if isinstance(detail, list):
                    detail = "; ".join(str(d) for d in detail)
            except ValueError:
                detail = response.text or detail
            raise APIError(detail, response.status_code)
        if response.status_code == 204:
            return None
        if not response.content:
            return {}
        return response.json()

    def get(self, path: str, params: dict | None = None, auth: bool = True) -> Any:
        response = requests.get(
            f"{self.base_url}{path}",
            headers=self._headers(auth=auth),
            params=params,
            timeout=120,
        )
        return self._handle_response(response)

    def post(self, path: str, data: dict | None = None, auth: bool = True) -> Any:
        response = requests.post(
            f"{self.base_url}{path}",
            headers=self._headers(auth=auth),
            json=data or {},
            timeout=300,
        )
        return self._handle_response(response)

    def delete(self, path: str, auth: bool = True) -> Any:
        response = requests.delete(
            f"{self.base_url}{path}",
            headers=self._headers(auth=auth),
            timeout=60,
        )
        return self._handle_response(response)

    def get_raw(self, path: str, auth: bool = True) -> bytes:
        response = requests.get(
            f"{self.base_url}{path}",
            headers=self._headers(auth=auth),
            timeout=60,
        )
        if response.status_code >= 400:
            raise APIError("Request failed", response.status_code)
        return response.content

    def post_multipart(
        self,
        path: str,
        files: dict,
        data: dict | None = None,
        auth: bool = False,
    ) -> Any:
        headers = {}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = requests.post(
            f"{self.base_url}{path}",
            headers=headers,
            files=files,
            data=data or {},
            timeout=120,
        )
        return self._handle_response(response)
