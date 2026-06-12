import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app


def test_create_case_requires_auth():
    app = create_app()
    client = app.test_client()
    response = client.post("/api/cases/create", data={"description": "Test case"})
    assert response.status_code == 302


def test_create_case_accepts_message_field():
    app = create_app()
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["access_token"] = "fake-token"
            sess["email"] = "test@example.com"
            sess["full_name"] = "Test User"
        response = client.post("/api/cases/create", data={"message": ""})
        assert response.status_code == 400
        assert b"Please describe your legal issue" in response.data
