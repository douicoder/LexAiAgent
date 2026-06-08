from pydantic_settings import BaseSettings, SettingsConfigDict

import os
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

class Settings(BaseSettings):
    GITHUB_TOKEN: str | None = None
    SUPABASE_URL: str | None = None
    SUPABASE_KEY: str | None = None
    DATABASE_URL: str = "sqlite+aiosqlite:///./lexagent.db"
    JWT_SECRET: str = "change-this-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    LLM_MODEL: str = "gpt-4o"
    
    model_config = SettingsConfigDict(env_file=env_path, extra="ignore")

settings = Settings()
