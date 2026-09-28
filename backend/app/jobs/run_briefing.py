"""T-BHM-03: Manual daily briefing re-run CLI.

Usage:
    python -m app.jobs.run_briefing
    python -m app.jobs.run_briefing --date 2026-09-25

If --date is omitted, defaults to today in IST (Asia/Kolkata).

Idempotency: if a daily_briefing report for the target date already exists, it
is deleted before the pipeline runs. Running twice for the same date produces
exactly one report row.

Exit codes:
    0 — report generated, or run legitimately skipped (non-trading day / stale data)
    1 — invalid --date format or unhandled pipeline exception
"""
from __future__ import annotations

import argparse
import datetime
import sys
import zoneinfo
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.research import Report
from app.utils.calendar import is_trading_day

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")
_DATE_FORMAT = "%Y-%m-%d"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> datetime.date | None:
    """Return a date parsed from YYYY-MM-DD, or None if invalid."""
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def _delete_existing_report(session: Session, date: datetime.date) -> int:
    """Delete any existing daily_briefing reports for this date.

    Returns the number of rows deleted (0 or more).
    Commits the deletion so the subsequent pipeline starts clean.
    """
    rows = session.execute(
        select(Report).where(
            Report.report_type == "daily_briefing",
            Report.trading_date == date,
        )
    ).scalars().all()

    if not rows:
        return 0

    for report in rows:
        session.delete(report)
    session.commit()
    return len(rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(
    argv: list[str] | None = None,
    *,
    _session_factory: Any = None,
    _briefing_fn: Callable | None = None,
) -> int:
    """Run the daily briefing pipeline for the specified (or today's) date.

    Args:
        argv:             sys.argv[1:] override for tests. None → sys.argv[1:].
        _session_factory: SyncSessionLocal override for tests.
        _briefing_fn:     run_daily_briefing override for tests.

    Returns:
        Exit code: 0 (success/skip) or 1 (error).
    """
    # ------------------------------------------------------------------
    # Lazy imports — keep module-level import free of DB/yfinance deps
    # ------------------------------------------------------------------
    if _session_factory is None:
        from app.db.session import SyncSessionLocal

        _session_factory = SyncSessionLocal

    if _briefing_fn is None:
        from app.jobs.daily_briefing import run_daily_briefing

        _briefing_fn = run_daily_briefing

    # ------------------------------------------------------------------
    # Argument parsing
    # ------------------------------------------------------------------
    parser = argparse.ArgumentParser(
        description="Manually run the daily briefing for a given date.",
        prog="python -m app.jobs.run_briefing",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Trading date to analyse (default: today in IST)",
    )
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------
    # Date resolution and validation
    # ------------------------------------------------------------------
    if args.date is not None:
        target_date = _parse_date(args.date)
        if target_date is None:
            print(
                f"Error: invalid date format {args.date!r}. Expected YYYY-MM-DD.",
                file=sys.stderr,
            )
            return 1
    else:
        target_date = datetime.datetime.now(tz=_IST).date()

    # ------------------------------------------------------------------
    # Trading-day guard (mirrors scheduler pre-check)
    # ------------------------------------------------------------------
    if not is_trading_day(target_date, "NSE"):
        print(f"Skipped: non-trading day ({target_date})")
        return 0

    # ------------------------------------------------------------------
    # Pipeline execution
    # ------------------------------------------------------------------
    try:
        with _session_factory() as session:
            deleted = _delete_existing_report(session, target_date)
            if deleted:
                print(f"Existing report for {target_date} deleted — regenerating.")

            result = _briefing_fn(target_date, session)

        if result.skipped:
            print(f"Skipped: {result.skip_reason}")
            return 0

        print(
            f"Report generated: id={result.report_id} date={result.date} "
            f"sectors={len(result.rankings_price)} triggers={len(result.triggers)}"
        )
        return 0

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
