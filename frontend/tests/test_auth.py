import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app


def test_login_page_loads():
    app = create_app()
    client = app.test_client()
    response = client.get("/auth/login")
    assert response.status_code == 200
    assert b"Sign In" in response.data


def test_register_page_loads():
    app = create_app()
    client = app.test_client()
    response = client.get("/auth/register")
    assert response.status_code == 200
    assert b"Create Account" in response.data


def test_root_redirects_to_login():
    app = create_app()
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 302
    assert "/auth/login" in response.location
