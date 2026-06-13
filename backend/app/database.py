from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = None
AsyncSessionLocal = None

if settings.DATABASE == "sqlite":
    engine = create_async_engine(settings.DATABASE_URL, echo=settings.APP_ENV == "development")
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        raise RuntimeError("SQLite database not configured. Set DATABASE=sqlite in .env")
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables() -> None:
    if settings.DATABASE != "sqlite":
        return

    from app import models  # noqa: F401

    async with engine.begin() as conn:
        from app.models.case import Case
        from app.models.case_document import CaseDocument
        from app.models.case_message import CaseMessage
        from app.models.user import User
        await conn.run_sync(User.__table__.create, checkfirst=True)
        await conn.run_sync(Case.__table__.create, checkfirst=True)
        await conn.run_sync(CaseDocument.__table__.create, checkfirst=True)
        await conn.run_sync(CaseMessage.__table__.create, checkfirst=True)
