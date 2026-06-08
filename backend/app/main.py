from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, auth, cases, documents, voice
from app.config import settings
from app.database import create_tables

app = FastAPI(
    title="LexAgent API",
    description="Autonomous Legal Aid Agent for India",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(voice.router, prefix="/api/v1")


@app.on_event("startup")
async def startup() -> None:
    await create_tables()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "LexAgent API"}
