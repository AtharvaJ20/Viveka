"""Database engine and session factories.

Two engines are maintained:
- async_engine  — used by FastAPI request handlers (asyncpg driver)
- sync_engine   — used by APScheduler job store and background jobs (psycopg2 driver)

Import patterns:
    # In FastAPI dependency (async path)
    from app.db.session import AsyncSessionLocal
    async def get_db() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSessionLocal() as session:
            yield session

    # In APScheduler job or migration script (sync path)
    from app.db.session import SyncSessionLocal
    with SyncSessionLocal() as session:
        ...
"""
from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# ---------------------------------------------------------------------------
# Async engine — FastAPI path
# ---------------------------------------------------------------------------
async_engine = create_async_engine(
    settings.async_database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # recycle stale connections gracefully
    echo=settings.is_development,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ---------------------------------------------------------------------------
# Sync engine — APScheduler job store + background jobs
# ---------------------------------------------------------------------------
sync_engine = create_engine(
    settings.sync_database_url,
    pool_size=3,
    max_overflow=5,
    pool_pre_ping=True,
    echo=settings.is_development,
)

SyncSessionLocal: sessionmaker[Session] = sessionmaker(
    sync_engine,
    autoflush=False,
    autocommit=False,
)

# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session for a single request. Rolls back on exception."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
