import time

from fastapi import Request
from limits import parse as _parse_limit
from slowapi import Limiter

# Shared rate-limiter instance. Added to app.state in main.py.
# Uses in-memory storage (per-process; resets on restart — acceptable for personal tool).
# headers_enabled=True so slowapi injects Retry-After on decorator-gated 429s (SR-AUTH-007, BUG-001).


def _get_real_ip(request: Request) -> str:
    """Return the originating IP: X-Forwarded-For (set by Caddy) takes precedence."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


limiter = Limiter(key_func=_get_real_ip, storage_uri="memory://", headers_enabled=True)

# Pre-parsed limit for failed-login tracking (SR-AUTH-007).
# A dedicated namespace keeps this counter independent of all other limits.
_FAILED_LOGIN_LIMIT = _parse_limit("5/10minute")
_FAILED_LOGIN_NS = "viveka_login_failures"


def is_login_allowed(ip: str) -> bool:
    """Return True if this IP has budget remaining for a login attempt.

    Checks without incrementing — call record_login_failure() on auth failure.
    """
    return limiter._limiter.test(_FAILED_LOGIN_LIMIT, _FAILED_LOGIN_NS, ip)


def record_login_failure(ip: str) -> None:
    """Increment the failed-login counter for this IP (SR-AUTH-007, BUG-002 fix).

    Called only on authentication failure so successful logins never consume budget.
    """
    limiter._limiter.hit(_FAILED_LOGIN_LIMIT, _FAILED_LOGIN_NS, ip)


def get_login_retry_after(ip: str) -> int:
    """Return seconds until the rate-limit window resets for this IP."""
    try:
        stats = limiter._limiter.get_window_stats(
            _FAILED_LOGIN_LIMIT, _FAILED_LOGIN_NS, ip
        )
        return max(1, int(stats.reset_time - time.time()) + 1)
    except Exception:
        return 600  # 10-minute fallback
