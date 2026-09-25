"""Auth endpoints: login, logout, current-user.

IMPORTANT: Do NOT add `from __future__ import annotations` to this file.
FastAPI introspects route handler and dependency signatures at registration time.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_session, get_current_user
from app.config import settings
from app.db.models.auth import User, UserSession
from app.db.session import get_db
from app.limiter import get_login_retry_after, is_login_allowed, record_login_failure
from app.services.auth import authenticate, create_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.strip().lower()


class UserOut(BaseModel):
    id: int
    email: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

def _set_session_cookie(response: Response, raw_token: str) -> None:
    """Set the session cookie with all required security attributes (SR-AUTH-001)."""
    response.set_cookie(
        key="session_token",
        value=raw_token,
        httponly=True,    # blocks JS document.cookie access
        secure=True,      # HTTPS only (Caddy terminates TLS in production)
        samesite="strict",# blocks cross-site cookie sends — primary CSRF mitigation (SR-AUTH-002)
        max_age=settings.SESSION_EXPIRE_DAYS * 86400,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    """Clear the session cookie (SR-AUTH-009)."""
    response.delete_cookie(
        key="session_token",
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )


def _client_ip(request: Request) -> str | None:
    """Return the real client IP for session audit logging.

    Prefers X-Forwarded-For (set by Caddy in production).
    Falls back to the direct connection host (127.0.0.1 behind a proxy).
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login", response_model=UserOut)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate with email + password and issue a session cookie.

    Rate limited to 5 *failed* attempts per 10 minutes per IP (SR-AUTH-007).
    Successful logins do not consume rate-limit budget.
    Returns 401 for any authentication failure — identical message for wrong
    password, missing account, or non-allowlisted email (SR-AUTH-008).
    Cookie attributes: HttpOnly + Secure + SameSite=Strict (SR-AUTH-001/002).
    """
    ip = _client_ip(request) or "127.0.0.1"

    # SR-AUTH-007: gate on failed-attempt counter BEFORE attempting auth.
    # Only failures are counted (see record_login_failure below), so legitimate
    # logins never deplete the budget.
    if not is_login_allowed(ip):
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(get_login_retry_after(ip))},
        )

    user = await authenticate(db, body.email, body.password)
    if user is None:
        record_login_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    raw_token = await create_session(
        db,
        user,
        user_agent=request.headers.get("User-Agent"),
        ip_address=ip,
        plaintext_password=body.password,  # passed for Argon2 rehash if needed
    )

    _set_session_cookie(response, raw_token)
    logger.info("login user_id=%d ip=%s", user.id, ip)
    return user


@router.post("/logout")
async def logout(
    response: Response,
    session: UserSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Invalidate the session: delete the DB row AND clear the cookie (SR-AUTH-009).

    Both steps are required: clearing only the cookie leaves the token replayable
    from other clients; deleting only the DB row leaves the cookie in the browser.
    """
    await db.delete(session)
    await db.commit()
    _clear_session_cookie(response)
    logger.info("logout user_id=%d session_id=%d", session.user_id, session.id)
    return {"status": "logged_out"}


@router.get("/me", response_model=UserOut)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return the authenticated user's profile. Validates session on every call (SR-AUTH-006)."""
    return current_user
