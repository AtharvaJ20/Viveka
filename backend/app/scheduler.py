"""APScheduler wiring — daily briefing job (T-BHM-01).

Scheduler: AsyncIOScheduler  (runs jobs inside the FastAPI asyncio event loop;
           sync job functions are dispatched to a thread pool so they never
           block the event loop).
Trigger:   CronTrigger hour=21 minute=0 timezone='Asia/Kolkata'
Job:       run_daily_briefing_job(date=None)

Job lifecycle (every execution):
  1. Open a sync DB session and write a job_executions row with status='running'.
  2. Check is_trading_day(job_date, 'NSE'); if False → update row to 'skipped' and return.
  3. Call the pipeline function (T-BHM-02 supplies the real one; T-BHM-01 uses a stub).
  4. On pipeline exception: retry up to MAX_RETRIES times with RETRY_DELAY_SECONDS backoff.
  5. On exhausted retries: update row to 'failed'.
  6. On pipeline success: update row to 'completed'.

Configuration:
  coalesce=True          — if the process was down and missed multiple 21:00 ticks,
                           fire at most once on restart (not once per missed tick).
  misfire_grace_time=3600 — fire late if the app restarted within 60 min of 21:00;
                            skip if more than 60 min have passed.

Manual trigger:
  Call run_daily_briefing_job(date=target_date) from any Python context.
  triggered_by is set to 'manual' when date is explicitly provided.
"""
from __future__ import annotations

import datetime
import logging
import time
import zoneinfo
from collections.abc import Callable
from typing import Any  # noqa: F401 — used in type hints for pipeline return

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.db.models.research import JobExecution
from app.utils.calendar import is_trading_day

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JOB_NAME = "daily_briefing"
CRON_HOUR = 21
CRON_MINUTE = 0
CRON_TZ = "Asia/Kolkata"

MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 300  # 5 minutes

_IST = zoneinfo.ZoneInfo(CRON_TZ)
_UTC = datetime.timezone.utc

_MISFIRE_GRACE_TIME = 3600  # seconds: allow firing up to 60 min late


# ---------------------------------------------------------------------------
# Pipeline placeholder
# ---------------------------------------------------------------------------


def _pipeline_stub(session: Session, job_date: datetime.date) -> None:
    """T-BHM-01 placeholder pipeline — replaced by T-BHM-02 implementation.

    T-BHM-02 will assign:
        from app.scheduler import _set_pipeline_fn
        _set_pipeline_fn(real_pipeline)
    or directly call run_daily_briefing_job with _pipeline=real_pipeline.
    """
    log.info("Pipeline stub called for %s (T-BHM-02 not yet wired)", job_date)


# Module-level reference; T-BHM-02 replaces this via _set_pipeline_fn.
# Return type is Any: the stub returns None; the real pipeline returns BriefingResult.
_PIPELINE_FN: Callable[[Session, datetime.date], Any] = _pipeline_stub


def _set_pipeline_fn(fn: Callable[[Session, datetime.date], Any]) -> None:
    """Register the pipeline implementation (T-BHM-02 calls this from main.py lifespan)."""
    global _PIPELINE_FN
    _PIPELINE_FN = fn


# ---------------------------------------------------------------------------
# Scheduler factory
# ---------------------------------------------------------------------------


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure (but do NOT start) the AsyncIOScheduler.

    Call scheduler.start() in the FastAPI lifespan startup handler.
    Call scheduler.shutdown(wait=False) in the lifespan shutdown handler.
    """
    scheduler = AsyncIOScheduler()

    trigger = CronTrigger(
        hour=CRON_HOUR,
        minute=CRON_MINUTE,
        timezone=CRON_TZ,
    )

    scheduler.add_job(
        run_daily_briefing_job,
        trigger=trigger,
        id=JOB_NAME,
        name=JOB_NAME,
        coalesce=True,
        misfire_grace_time=_MISFIRE_GRACE_TIME,
        replace_existing=True,
    )

    log.info(
        "Scheduler configured: job=%s trigger=%02d:%02d %s",
        JOB_NAME,
        CRON_HOUR,
        CRON_MINUTE,
        CRON_TZ,
    )
    return scheduler


# ---------------------------------------------------------------------------
# Job entry point
# ---------------------------------------------------------------------------


def run_daily_briefing_job(
    date: datetime.date | None = None,
    _session_factory: Any | None = None,
    _pipeline: Callable[[Session, datetime.date], None] | None = None,
    _retry_delay_seconds: int = RETRY_DELAY_SECONDS,
) -> None:
    """Run (or skip) the daily briefing for the given date.

    This function is called by APScheduler at 21:00 IST. It can also be
    called directly (manual trigger) by passing an explicit date.

    Args:
        date:                 Target date. None → today in IST (normal scheduler path).
        _session_factory:     Override for test injection. None → SyncSessionLocal.
        _pipeline:            Override for test injection. None → _PIPELINE_FN.
        _retry_delay_seconds: Override for test injection (set to 0 to skip sleep).
    """
    from app.db.session import SyncSessionLocal  # local import avoids circular deps

    session_factory = _session_factory if _session_factory is not None else SyncSessionLocal
    pipeline_fn = _pipeline if _pipeline is not None else _PIPELINE_FN

    job_date = date if date is not None else datetime.datetime.now(tz=_IST).date()
    triggered_by = "manual" if date is not None else "scheduler"

    log.info(
        "run_daily_briefing_job: date=%s triggered_by=%s", job_date, triggered_by
    )

    with session_factory() as session:
        exec_row = _create_execution_row(session, job_date, triggered_by)

        # ------------------------------------------------------------------
        # Trading-day guard
        # ------------------------------------------------------------------
        if not is_trading_day(job_date, "NSE"):
            _mark_skipped(session, exec_row, "holiday")
            log.info(
                "run_daily_briefing_job: %s is not a trading day — skipped", job_date
            )
            return

        # ------------------------------------------------------------------
        # Run pipeline with retry
        # ------------------------------------------------------------------
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                result = pipeline_fn(session, job_date)
                _mark_completed(
                    session, exec_row, attempt,
                    report_id=getattr(result, "report_id", None),
                )
                log.info(
                    "run_daily_briefing_job: completed date=%s attempt=%d",
                    job_date,
                    attempt,
                )
                return

            except Exception as exc:
                last_exc = exc
                log.warning(
                    "run_daily_briefing_job: attempt %d/%d failed for %s: %s",
                    attempt + 1,
                    MAX_RETRIES + 1,
                    job_date,
                    exc,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(_retry_delay_seconds)

        # All retries exhausted
        _mark_failed(session, exec_row, last_exc)
        log.error(
            "run_daily_briefing_job: all %d attempts failed for %s: %s",
            MAX_RETRIES + 1,
            job_date,
            last_exc,
        )


# ---------------------------------------------------------------------------
# job_executions helpers
# ---------------------------------------------------------------------------


def _create_execution_row(
    session: Session,
    job_date: datetime.date,
    triggered_by: str,
) -> JobExecution:
    """Insert a 'running' job_executions row and flush to get the DB-assigned id."""
    exec_row = JobExecution(
        job_name=JOB_NAME,
        triggered_by=triggered_by,
        started_at=datetime.datetime.now(tz=_UTC),
        status="running",
        retry_count=0,
    )
    session.add(exec_row)
    session.flush()
    return exec_row


def _mark_skipped(session: Session, exec_row: JobExecution, reason: str) -> None:
    exec_row.status = "skipped"
    exec_row.skip_reason = reason
    exec_row.completed_at = datetime.datetime.now(tz=_UTC)
    session.commit()


def _mark_completed(
    session: Session,
    exec_row: JobExecution,
    attempt: int,
    report_id: int | None = None,
) -> None:
    exec_row.status = "completed"
    exec_row.completed_at = datetime.datetime.now(tz=_UTC)
    exec_row.retry_count = attempt
    if isinstance(report_id, int):
        exec_row.report_id = report_id
    session.commit()


def _mark_failed(
    session: Session, exec_row: JobExecution, exc: Exception | None
) -> None:
    exec_row.status = "failed"
    exec_row.completed_at = datetime.datetime.now(tz=_UTC)
    exec_row.retry_count = MAX_RETRIES
    exec_row.error_message = str(exc)[:1000] if exc else "Unknown error"
    session.commit()
