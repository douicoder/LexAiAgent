import os

from pydantic_settings import BaseSettings, SettingsConfigDict

env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

class Settings(BaseSettings):
    GITHUB_TOKEN: str | None = None
    GITHUB_TOKEN_2: str | None = None
    SUPABASE_URL: str | None = None
    SUPABASE_KEY: str | None = None
    SUPABASE_SERVICE_KEY: str
    DATABASE_URL: str = "sqlite+aiosqlite:///./lexagent.db"
    JWT_SECRET: str = "change-this-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000"
    EMBEDDING_MODEL: str = "jina-embeddings-v5-text-small"
    EMBEDDING_BASE_URL: str = "https://api.jina.ai/v1"
    EMBEDDING_API_KEY: str | None = None
    LLM_PROVIDER: str = "openrouter"
    LLM_MODEL: str = "openai/gpt-oss-120b"
    FAST_MODEL: str = "openai/gpt-oss-120b"
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_API_KEY: str | None = None
    WHISPER_MODEL: str = "openai/whisper-base"
    SUPABASE_STORAGE_BUCKET: str = "legal-notices"
    DATABASE: str = "supabase"  # "supabase" | "sqlite"

    model_config = SettingsConfigDict(env_file=env_path, extra="ignore")

settings = Settings()
