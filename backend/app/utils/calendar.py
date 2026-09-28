"""T-VYS-03: Exchange trading-calendar utilities.

DB-free utility functions for determining trading days, plus a DB seeder that
populates the trading_calendar table idempotently.

Holiday data is read from app/data/holidays_{year}.yaml files and held in a
module-level cache keyed on (year, exchange). Call clear_holiday_cache() in
tests to reset state between cases.

Semantics:
  is_trading_day(d)          — False for weekends and YAML-listed holidays.
  next_trading_day(d)        — first trading day strictly AFTER d.
  last_trading_day(d)        — most recent trading day ON OR BEFORE d.
  seed_trading_calendar(...) — INSERT one row per calendar date per exchange,
                               ON CONFLICT DO NOTHING (safe to re-run).
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models.market import TradingCalendar

log = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data"
_DEFAULT_YEARS = [2026, 2027]
_DEFAULT_EXCHANGES = ["NSE", "BSE"]

# Module-level cache: (year, exchange) → {holiday_date: holiday_name}
_HOLIDAY_DATA: dict[tuple[int, str], dict[datetime.date, str]] = {}


@dataclass
class SeedCalendarResult:
    rows_inserted: int = 0
    rows_existing: int = 0
    years_seeded: list[int] = field(default_factory=list)
    exchanges_seeded: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API — DB-free
# ---------------------------------------------------------------------------


def is_trading_day(trading_date: datetime.date, exchange: str = "NSE") -> bool:
    """Return True if trading_date is a regular trading session for exchange.

    False for weekends (Saturday, Sunday) and holidays listed in
    holidays_{year}.yaml. If no YAML exists for the year, all weekdays
    are treated as trading days and a warning is logged.
    """
    if trading_date.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return trading_date not in _get_holidays(trading_date.year, exchange)


def next_trading_day(from_date: datetime.date, exchange: str = "NSE") -> datetime.date:
    """Return the first trading day strictly AFTER from_date.

    Raises RuntimeError if no trading day is found within 30 days (a broken
    or missing holiday YAML would cause this).
    """
    candidate = from_date + datetime.timedelta(days=1)
    for _ in range(30):
        if is_trading_day(candidate, exchange):
            return candidate
        candidate += datetime.timedelta(days=1)
    raise RuntimeError(
        f"No trading day found within 30 days after {from_date} for exchange {exchange!r}"
    )


def last_trading_day(from_date: datetime.date, exchange: str = "NSE") -> datetime.date:
    """Return the most recent trading day ON OR BEFORE from_date.

    If from_date is itself a trading day, it is returned directly.
    Raises RuntimeError if no trading day is found within 30 days prior.
    """
    candidate = from_date
    for _ in range(30):
        if is_trading_day(candidate, exchange):
            return candidate
        candidate -= datetime.timedelta(days=1)
    raise RuntimeError(
        f"No trading day found within 30 days before {from_date} for exchange {exchange!r}"
    )


# ---------------------------------------------------------------------------
# DB seeder
# ---------------------------------------------------------------------------


def seed_trading_calendar(
    session: Session,
    years: list[int] | None = None,
    exchanges: list[str] | None = None,
) -> SeedCalendarResult:
    """Populate trading_calendar with one row per calendar date per exchange.

    Generates rows for every date in each year (365 or 366 rows per year per
    exchange). Uses INSERT ... ON CONFLICT DO NOTHING — safe to re-run without
    duplicating rows. Commits at the end.
    """
    years = years or _DEFAULT_YEARS
    exchanges = exchanges or _DEFAULT_EXCHANGES
    result = SeedCalendarResult(years_seeded=list(years), exchanges_seeded=list(exchanges))

    for year in years:
        for exchange in exchanges:
            rows = _generate_calendar_rows(year, exchange)
            if not rows:
                continue
            stmt = pg_insert(TradingCalendar).values(rows).on_conflict_do_nothing()
            db_result = session.execute(stmt)
            inserted = max(0, db_result.rowcount if db_result.rowcount is not None else 0)
            result.rows_inserted += inserted
            result.rows_existing += len(rows) - inserted

    session.commit()
    log.info(
        "seed_trading_calendar: years=%s exchanges=%s — %d inserted, %d already existed",
        years,
        exchanges,
        result.rows_inserted,
        result.rows_existing,
    )
    return result


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def clear_holiday_cache() -> None:
    """Clear the in-memory holiday cache. Call this in tests to reset state."""
    _HOLIDAY_DATA.clear()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_holidays(year: int, exchange: str) -> frozenset[datetime.date]:
    return frozenset(_get_holiday_data(year, exchange))


def _get_holiday_data(year: int, exchange: str) -> dict[datetime.date, str]:
    """Return {holiday_date: name} from cache, loading from YAML on first access."""
    key = (year, exchange)
    if key not in _HOLIDAY_DATA:
        _HOLIDAY_DATA[key] = _load_holidays_for_year(year, exchange)
    return _HOLIDAY_DATA[key]


def _load_holidays_for_year(year: int, exchange: str) -> dict[datetime.date, str]:
    """Parse holidays_{year}.yaml and return {date: name} for the exchange section."""
    path = _DATA_DIR / f"holidays_{year}.yaml"
    if not path.exists():
        log.warning(
            "No holiday YAML for %s year=%d (%s); treating all weekdays as trading days",
            exchange,
            year,
            path,
        )
        return {}

    with path.open(encoding="utf-8") as fh:
        data: dict = yaml.safe_load(fh)  # type: ignore[type-arg]

    result: dict[datetime.date, str] = {}
    for entry in data.get(exchange, []):
        d = datetime.date.fromisoformat(str(entry["date"]))
        result[d] = str(entry.get("name", "Holiday"))
    return result


def _generate_calendar_rows(year: int, exchange: str) -> list[dict]:  # type: ignore[type-arg]
    """Build one row dict per calendar day for the year and exchange.

    Row dict keys match TradingCalendar column names:
      trading_date, exchange, is_trading_day, reason, source.
    """
    holiday_map = _get_holiday_data(year, exchange)
    rows: list[dict] = []  # type: ignore[type-arg]
    current = datetime.date(year, 1, 1)
    end = datetime.date(year, 12, 31)

    while current <= end:
        weekday = current.weekday()
        if weekday == 5:
            reason: str | None = "Weekend (Saturday)"
            trading = False
        elif weekday == 6:
            reason = "Weekend (Sunday)"
            trading = False
        elif current in holiday_map:
            reason = holiday_map[current]
            trading = False
        else:
            reason = None
            trading = True

        rows.append({
            "trading_date": current,
            "exchange": exchange,
            "is_trading_day": trading,
            "reason": reason,
            "source": f"{exchange.lower()}_holidays_yaml",
        })
        current += datetime.timedelta(days=1)

    return rows
