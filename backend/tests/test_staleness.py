"""Unit tests for T-VYS-04: price-data staleness detection.

Coverage (acceptance criteria):
  AC1 — trading day + zero rows in price_data → is_fresh=False, reason names gap
  AC2 — trading day + >= min_rows → is_fresh=True
  AC3 — non-trading day → is_fresh=True, reason="non-trading day"
  AC4 — non-trading day: DB is NOT queried (no wasted round-trip)

Additional:
  AC5 — row count below threshold (< min_rows) → is_fresh=False
  AC6 — row count exactly at threshold → is_fresh=True
  AC7 — custom min_rows parameter respected
  AC8 — StalenessResult fields (is_fresh, reason, row_count) accessible as expected
  AC9 — stale reason includes date and exchange
  AC10 — fresh reason includes actual row count

Test dates (reference: Jan 1, 2026 = Thursday):
  2026-01-18 = Sunday   → non-trading day (weekend check, no YAML needed)
  2026-01-26 = Monday   → non-trading day (Republic Day holiday, in YAML)
  2026-09-28 = Monday   → trading day (not a holiday, not a weekend)

All DB interactions are mocked. Real YAML files are used for is_trading_day checks.
"""
from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import os
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_viveka")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-exactly-thirty-two-chars")

from app.utils.calendar import clear_holiday_cache
from app.utils.staleness import StalenessResult, _DEFAULT_MIN_ROWS, check_data_freshness

# ---------------------------------------------------------------------------
# Known test dates — verified against 2026 calendar
# ---------------------------------------------------------------------------

_SUNDAY = datetime.date(2026, 1, 18)         # non-trading day (weekend)
_REPUBLIC_DAY = datetime.date(2026, 1, 26)   # non-trading day (holiday in YAML)
_TRADING_DAY = datetime.date(2026, 9, 28)    # Monday — regular trading day, not in YAML


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_calendar_cache() -> None:
    """Clear the holiday cache before each test to avoid cross-test pollution."""
    clear_holiday_cache()


def _mock_session(row_count: int) -> MagicMock:
    """Return a mock session that returns row_count from COUNT query."""
    session = MagicMock()
    session.execute.return_value.scalar_one.return_value = row_count
    return session


# ---------------------------------------------------------------------------
# AC8 — StalenessResult dataclass fields
# ---------------------------------------------------------------------------

class TestStalenessResultDataclass:
    def test_fields_are_accessible(self) -> None:  # AC8
        result = StalenessResult(is_fresh=True, reason="ok", row_count=55)
        assert result.is_fresh is True
        assert result.reason == "ok"
        assert result.row_count == 55

    def test_default_min_rows_is_fifty(self) -> None:
        assert _DEFAULT_MIN_ROWS == 50


# ---------------------------------------------------------------------------
# AC3 + AC4 — non-trading day: returns fresh, skips DB
# ---------------------------------------------------------------------------

class TestCheckDataFreshnessNonTradingDay:
    def test_sunday_returns_is_fresh(self) -> None:  # AC3
        session = _mock_session(0)
        result = check_data_freshness(_SUNDAY, "NSE", session)
        assert result.is_fresh is True

    def test_holiday_returns_is_fresh(self) -> None:  # AC3
        session = _mock_session(0)
        result = check_data_freshness(_REPUBLIC_DAY, "NSE", session)
        assert result.is_fresh is True

    def test_non_trading_day_reason_is_non_trading_day(self) -> None:  # AC3
        session = _mock_session(0)
        result = check_data_freshness(_SUNDAY, "NSE", session)
        assert result.reason == "non-trading day"

    def test_non_trading_day_row_count_is_zero(self) -> None:
        session = _mock_session(0)
        result = check_data_freshness(_SUNDAY, "NSE", session)
        assert result.row_count == 0

    def test_non_trading_day_does_not_query_db(self) -> None:  # AC4
        # Verifies no wasted DB round-trip on non-trading days.
        session = _mock_session(0)
        check_data_freshness(_SUNDAY, "NSE", session)
        session.execute.assert_not_called()

    def test_holiday_does_not_query_db(self) -> None:  # AC4
        session = _mock_session(0)
        check_data_freshness(_REPUBLIC_DAY, "NSE", session)
        session.execute.assert_not_called()

    def test_sunday_bse_also_fresh(self) -> None:
        session = _mock_session(0)
        result = check_data_freshness(_SUNDAY, "BSE", session)
        assert result.is_fresh is True
        assert result.reason == "non-trading day"


# ---------------------------------------------------------------------------
# AC1 + AC5 — trading day, insufficient rows → is_fresh=False
# ---------------------------------------------------------------------------

class TestCheckDataFreshnessStale:
    def test_zero_rows_is_stale(self) -> None:  # AC1
        session = _mock_session(0)
        result = check_data_freshness(_TRADING_DAY, "NSE", session)
        assert result.is_fresh is False

    def test_zero_rows_row_count_is_zero(self) -> None:
        session = _mock_session(0)
        result = check_data_freshness(_TRADING_DAY, "NSE", session)
        assert result.row_count == 0

    def test_below_threshold_is_stale(self) -> None:  # AC5
        session = _mock_session(49)
        result = check_data_freshness(_TRADING_DAY, "NSE", session)
        assert result.is_fresh is False
        assert result.row_count == 49

    def test_stale_reason_names_date(self) -> None:  # AC9
        session = _mock_session(0)
        result = check_data_freshness(_TRADING_DAY, "NSE", session)
        assert str(_TRADING_DAY) in result.reason

    def test_stale_reason_names_exchange(self) -> None:  # AC9
        session = _mock_session(0)
        result = check_data_freshness(_TRADING_DAY, "NSE", session)
        assert "NSE" in result.reason

    def test_stale_reason_names_threshold(self) -> None:
        session = _mock_session(5)
        result = check_data_freshness(_TRADING_DAY, "NSE", session, min_rows=50)
        assert "50" in result.reason

    def test_stale_reason_names_actual_count(self) -> None:
        session = _mock_session(5)
        result = check_data_freshness(_TRADING_DAY, "NSE", session)
        assert "5" in result.reason


# ---------------------------------------------------------------------------
# AC2 + AC6 + AC7 — trading day, sufficient rows → is_fresh=True
# ---------------------------------------------------------------------------

class TestCheckDataFreshnessFresh:
    def test_at_threshold_is_fresh(self) -> None:  # AC6
        session = _mock_session(50)
        result = check_data_freshness(_TRADING_DAY, "NSE", session)
        assert result.is_fresh is True

    def test_above_threshold_is_fresh(self) -> None:  # AC2
        session = _mock_session(100)
        result = check_data_freshness(_TRADING_DAY, "NSE", session)
        assert result.is_fresh is True
        assert result.row_count == 100

    def test_fresh_reason_includes_row_count(self) -> None:  # AC10
        session = _mock_session(95)
        result = check_data_freshness(_TRADING_DAY, "NSE", session)
        assert "95" in result.reason

    def test_custom_min_rows_respected_below(self) -> None:  # AC7
        session = _mock_session(10)
        result = check_data_freshness(_TRADING_DAY, "NSE", session, min_rows=11)
        assert result.is_fresh is False

    def test_custom_min_rows_respected_at(self) -> None:  # AC7
        session = _mock_session(10)
        result = check_data_freshness(_TRADING_DAY, "NSE", session, min_rows=10)
        assert result.is_fresh is True

    def test_single_row_min_rows_one(self) -> None:
        session = _mock_session(1)
        result = check_data_freshness(_TRADING_DAY, "NSE", session, min_rows=1)
        assert result.is_fresh is True
        assert result.row_count == 1

    def test_db_is_queried_exactly_once_for_trading_day(self) -> None:
        session = _mock_session(75)
        check_data_freshness(_TRADING_DAY, "NSE", session)
        session.execute.assert_called_once()
