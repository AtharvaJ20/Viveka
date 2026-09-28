"""T-VYS-04: Price-data staleness detection.

Before the ranking job runs, verify that sufficient price data for the expected
trading day is present in the database. The pipeline (T-BHM-02) must abort when
is_fresh=False — no partial or empty report should be generated.

Semantics of the non-trading-day path:
  If the date is not a trading day, the function returns is_fresh=True with
  reason="non-trading day". This is intentional: the scheduler (T-BHM-01)
  already guards against running on non-trading days via is_trading_day(). From
  the staleness checker's perspective, a non-trading day is "not applicable" —
  there is no missing data, and the pipeline should not have been invoked at all.
  Returning is_fresh=True ensures the pipeline can distinguish "no data because
  the market was closed" from "no data because the fetch failed".
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.market import PriceData
from app.utils.calendar import is_trading_day

log = logging.getLogger(__name__)

_DEFAULT_MIN_ROWS: int = 50


@dataclass
class StalenessResult:
    """Result of a single staleness check.

    Attributes:
        is_fresh:  True → pipeline may proceed. False → pipeline must abort.
        reason:    Human-readable explanation of the result.
        row_count: Rows found in price_data for the checked date/exchange.
                   Always 0 when the date is a non-trading day.
    """

    is_fresh: bool
    reason: str
    row_count: int


def check_data_freshness(
    date: datetime.date,
    exchange: str,
    session: Session,
    min_rows: int = _DEFAULT_MIN_ROWS,
) -> StalenessResult:
    """Check whether price data for date/exchange meets the minimum row threshold.

    Args:
        date:     The trading date to check (typically today).
        exchange: Exchange code, e.g. "NSE".
        session:  Active SQLAlchemy session (read-only query; no writes).
        min_rows: Minimum number of price_data rows required to consider the
                  data fresh. Defaults to 50 (NSE NIFTY 50 coverage).

    Returns:
        StalenessResult with is_fresh, reason, and row_count.
    """
    if not is_trading_day(date, exchange):
        log.debug(
            "check_data_freshness: %s %s is a non-trading day — DB check skipped",
            date,
            exchange,
        )
        return StalenessResult(
            is_fresh=True,
            reason="non-trading day",
            row_count=0,
        )

    count: int = session.execute(
        select(func.count()).select_from(PriceData).where(
            PriceData.trading_date == date,
            PriceData.exchange == exchange,
        )
    ).scalar_one()

    if count >= min_rows:
        log.debug(
            "check_data_freshness: %s %s — %d rows present (threshold %d) → FRESH",
            date,
            exchange,
            count,
            min_rows,
        )
        return StalenessResult(
            is_fresh=True,
            reason=f"{count} rows present for {date} ({exchange}); threshold {min_rows}",
            row_count=count,
        )

    log.warning(
        "check_data_freshness: %s %s — %d rows in price_data, need >= %d → STALE",
        date,
        exchange,
        count,
        min_rows,
    )
    return StalenessResult(
        is_fresh=False,
        reason=(
            f"price_data has {count} rows for {date} ({exchange}); "
            f"need at least {min_rows}"
        ),
        row_count=count,
    )
