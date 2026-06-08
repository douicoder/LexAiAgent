from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.DATABASE_URL, echo=settings.APP_ENV == "development")
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables() -> None:
    from app import models  # noqa: F401
    from app.models.user import User

    async with engine.begin() as conn:
        if settings.DATABASE_URL.startswith("sqlite"):
            await conn.run_sync(User.__table__.create, checkfirst=True)
            return

        await conn.run_sync(Base.metadata.create_all)
