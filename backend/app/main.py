import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import demo
from app.config import settings
from app.database import create_tables

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("server.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LexAgent API",
    description="Autonomous Legal Aid Agent for India",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(demo.router, prefix="")


@app.on_event("startup")
async def startup() -> None:
    logger.info("Starting LexAgent API...")
    await create_tables()
    logger.info("Database tables ready")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "LexAgent API"}
