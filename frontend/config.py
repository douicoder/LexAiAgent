import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "lexagent-dev-secret-change-in-production")
    API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1/demo")
    DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 7
