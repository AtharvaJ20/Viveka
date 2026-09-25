"""Authentication service: password hashing, credential verification, session lifecycle.

All business logic lives here. FastAPI handlers and dependencies are thin callers.
No framework imports — this module is independently testable.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.auth import User, UserSession

logger = logging.getLogger(__name__)

# PasswordHasher defaults (argon2-cffi): m=65536 KiB, t=3, p=4 — meets OWASP 2025 (SR-AUTH-005)
_ph = PasswordHasher()

# Pre-computed dummy hash used to equalise response timing when a user account is not
# found. Generated at module load; constant across all calls (SR-AUTH-008).
_DUMMY_HASH: str = _ph.hash("viveka_timing_dummy_constant_2026")


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _make_session_token() -> tuple[str, str]:
    """Return (raw_hex_token, sha256_token_hash).

    The raw hex token is placed in the browser cookie (Set-Cookie: session_token=...).
    The SHA-256 hash is stored in the sessions.token_hash column.
    32 bytes = 256 bits of entropy — satisfies SR-AUTH-003.
    """
    raw: bytes = secrets.token_bytes(32)
    return raw.hex(), hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(plaintext: str) -> str:
    """Hash plaintext with Argon2id. Result always starts with $argon2id$ (SR-AUTH-005)."""
    return _ph.hash(plaintext)


def verify_password(stored_hash: str, plaintext: str) -> bool:
    """Return True if plaintext matches stored_hash. Never raises externally."""
    try:
        return _ph.verify(stored_hash, plaintext)
    except VerifyMismatchError:
        return False
    except (VerificationError, InvalidHashError):
        logger.warning("Argon2 verification error — hash may be corrupted or invalid")
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Return True if the hash was created with outdated Argon2id parameters."""
    return _ph.check_needs_rehash(stored_hash)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

async def authenticate(
    db: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    """Verify email + password against the database.

    Returns the User on success, None on any failure.

    Security properties:
    - Email normalised to lowercase before allowlist check AND DB lookup (SR-AUTH-004).
    - Allowlist gate fires before any DB query (fail fast).
    - A dummy Argon2id verify is always run when the account is absent to equalise
      response timing and prevent user-enumeration via timing oracle (SR-AUTH-008).
    - Identical return value (None) for: not in allowlist / user not found / wrong password.
    """
    normalised = email.strip().lower()

    # SR-AUTH-004: allowlist gate — checked before any DB query
    if normalised not in settings.allowed_emails_set:
        # Timing normalisation: consume ~same wall-clock as a real Argon2 verify
        try:
            _ph.verify(_DUMMY_HASH, password)
        except (VerifyMismatchError, VerificationError):
            pass
        return None

    user = await db.scalar(select(User).where(User.email == normalised))

    if user is None:
        # SR-AUTH-008: must run Argon2 even when user row is absent
        try:
            _ph.verify(_DUMMY_HASH, password)
        except (VerifyMismatchError, VerificationError):
            pass
        return None

    if not verify_password(user.hashed_password, password):
        return None

    return user


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------

async def create_session(
    db: AsyncSession,
    user: User,
    user_agent: str | None,
    ip_address: str | None,
    plaintext_password: str | None = None,
) -> str:
    """Create a new DB session row, update last_login_at, and return the raw hex token.

    Commits the transaction — do not commit separately after calling this.

    If plaintext_password is provided and the stored hash needs rehashing,
    the password hash is updated atomically in the same transaction (SR-AUTH-005).
    """
    raw_token, token_hash = _make_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.SESSION_EXPIRE_DAYS)

    session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(session)

    user.last_login_at = datetime.now(timezone.utc)

    # SR-AUTH-005: rehash when Argon2id parameters have been upgraded
    if plaintext_password is not None and needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(plaintext_password)

    await db.commit()
    return raw_token
