import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app


def test_research_requires_auth():
    app = create_app()
    client = app.test_client()
    response = client.get("/research")
    assert response.status_code == 302
    assert "/auth/login" in response.location
