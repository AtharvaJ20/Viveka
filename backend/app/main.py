"""FastAPI application factory.

Security controls wired here:
- SecurityHeadersMiddleware: X-Content-Type-Options, X-Frame-Options, Referrer-Policy (SR-AUTH-012)
- slowapi rate limiter: shared state added to app.state (SR-AUTH-007)
- RateLimitExceeded handler: returns 429 with Retry-After header
- Generic Exception handler: returns {"detail": "Internal server error"} — no stack traces (SR-AUTH-010)
- CORS: explicit allow_headers list, not wildcard (SR-AUTH-013)
- /docs and /redoc disabled in production

Scheduler:
- AsyncIOScheduler starts in lifespan startup and shuts down on exit (T-BHM-01).
- Scheduler reference stored at app.state.scheduler.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.auth import router as auth_router
from app.api.v1.reports import router as reports_router
from app.config import settings
from app.limiter import limiter
from app.middleware import SecurityHeadersMiddleware
from app.scheduler import _set_pipeline_fn, create_scheduler

logger = logging.getLogger(__name__)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a generic 500 body — never expose internals (SR-AUTH-010)."""
    logger.error(
        "Unhandled exception: %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the daily briefing scheduler on startup; shut it down on exit."""
    # Lazy import: daily_briefing → registry → nse_yfinance requires yfinance.
    # Importing at module load time breaks conftest (yfinance not installed in test env).
    from app.jobs.daily_briefing import run_daily_briefing  # noqa: PLC0415

    _set_pipeline_fn(run_daily_briefing)
    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("APScheduler started")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")


app = FastAPI(
    title="Viveka",
    description="Personal Stock Research & Monitoring Agent",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# --- Rate limiting (SR-AUTH-007) ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# --- Security headers (SR-AUTH-012) ---
app.add_middleware(SecurityHeadersMiddleware)

# --- CORS (SR-AUTH-013: explicit allow_headers, not wildcard) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Accept"],
)

# --- Generic 500 handler (SR-AUTH-010) ---
app.add_exception_handler(Exception, _unhandled_exception_handler)  # type: ignore[arg-type]

# --- Routers ---
app.include_router(auth_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness probe. Returns only status — no version, config, or internal state."""
    return {"status": "ok"}
