"""Shared pytest fixtures for the auth test suite."""
from __future__ import annotations

# Set required env vars BEFORE any app module is imported.
# Settings() is instantiated at module level; these values are synthetic
# test stubs — no real database or secret is used in unit/mock tests.
import os
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://test:test@localhost:5432/test_viveka",
)
os.environ.setdefault(
    "SECRET_KEY",
    "test-secret-key-that-is-exactly-thirty-two-chars",
)

import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import User, UserSession
from app.db.session import get_db
from app.main import app
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

TEST_EMAIL = "analyst@viveka.in"
TEST_PASSWORD = "correct_horse_battery_staple_42"


# ---------------------------------------------------------------------------
# DB mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db() -> AsyncMock:
    """AsyncMock of AsyncSession with all async methods pre-wired."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()       # synchronous in SQLAlchemy ORM
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.scalar = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def override_db(mock_db: AsyncMock) -> AsyncMock:
    """Override app's get_db dependency with mock_db for the duration of the test."""
    async def _get_mock_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _get_mock_db
    yield mock_db
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# User / session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_user() -> User:
    """A User instance with a real Argon2id hash of TEST_PASSWORD."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return User(
        id=1,
        email=TEST_EMAIL,
        hashed_password=hash_password(TEST_PASSWORD),
        is_active=True,
        created_at=now,
        last_login_at=None,
    )


@pytest.fixture
def test_session(test_user: User) -> UserSession:
    """A UserSession instance linked to test_user."""
    now = datetime.datetime.now(datetime.timezone.utc)
    sess = UserSession(
        id=100,
        user_id=test_user.id,
        token_hash="a" * 64,
        expires_at=now + datetime.timedelta(days=30),
        created_at=now,
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    sess.user = test_user
    return sess


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(override_db: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient wired to the FastAPI app with a mocked DB dependency."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Allowlist helper
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=False)
def allow_test_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch settings so TEST_EMAIL is in the allowlist for this test."""
    monkeypatch.setattr("app.config.settings.ALLOWED_EMAILS", TEST_EMAIL)
