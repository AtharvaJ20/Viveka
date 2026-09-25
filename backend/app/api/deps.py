"""FastAPI dependencies for authentication.

IMPORTANT: Do NOT add `from __future__ import annotations` to this file.
FastAPI introspects dependency function signatures at route-registration time
via inspect.get_annotations(func, eval_str=True). Deferred string annotations
can cause TypeError at startup for any type that is not subscriptable at runtime.
"""
import hashlib
import logging
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.auth import User, UserSession
from app.db.session import get_db

logger = logging.getLogger(__name__)

_UNAUTHENTICATED = HTTPException(status_code=401, detail="Not authenticated")


async def _resolve_session(
    db: AsyncSession = Depends(get_db),
    session_token: str | None = Cookie(default=None),
) -> UserSession:
    """Core session validation — the single choke point for all authentication.

    Checks:
    1. Cookie present and parseable as hex
    2. Session row exists for this token hash
    3. Session has not expired
    4. Associated user has is_active = True (SR-AUTH-006)

    FastAPI's dependency cache ensures this function executes only once per request,
    even when both get_current_user and get_current_session are declared as parameters
    on the same handler.
    """
    if session_token is None:
        raise _UNAUTHENTICATED

    try:
        token_hash = hashlib.sha256(bytes.fromhex(session_token)).hexdigest()
    except ValueError:
        raise _UNAUTHENTICATED

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(UserSession)
        .options(selectinload(UserSession.user))
        .join(User, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.expires_at > now,
            User.is_active.is_(True),  # SR-AUTH-006: re-checked on every request
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise _UNAUTHENTICATED

    return session


async def get_current_session(
    session: UserSession = Depends(_resolve_session),
) -> UserSession:
    """Dependency: return the authenticated UserSession for the current request."""
    return session


async def get_current_user(
    session: UserSession = Depends(_resolve_session),
) -> User:
    """Dependency: return the authenticated User for the current request."""
    return session.user
