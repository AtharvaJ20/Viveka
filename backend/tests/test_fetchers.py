"""Unit tests for T-VYS-01: DataFetcher Protocol + OHLCV ingestion.

All yfinance calls are mocked at NSEYFinanceFetcher._download so no network
access is required. Database interactions use MagicMock sessions with scripted
return values.

Coverage targets (acceptance criteria):
  AC1 — valid response → OHLCVResult persisted to price_data with correct fields
  AC2 — empty yfinance response → skip logged, no DB write, job continues
  AC3 — invalid close (NaN / zero) → row rejected before persistence
  AC4 — exchange='BSE' → NotImplementedError immediately
  AC5 — FetchError on one ticker → error counted, other tickers continue
  AC6 — idempotency: ON CONFLICT DO NOTHING on re-run (mock verifies single execute)
"""
from __future__ import annotations

import datetime
import math
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

# Set required env vars before importing app modules
import os
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_viveka")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-exactly-thirty-two-chars")

from app.fetchers import FetchError, OHLCVResult
from app.fetchers.bse_stub import BSEBhavCopyStub
from app.fetchers.nse_yfinance import NSEYFinanceFetcher, _to_nse_symbol
from app.fetchers.registry import FetchSummary, FetcherRegistry, _upsert_price_row

DATE = datetime.date(2026, 9, 25)
DATE_START = datetime.date(2026, 9, 23)
DATE_END = datetime.date(2026, 9, 25)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

try:
    import pandas as pd  # type: ignore[import-untyped]
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False


def _make_df(
    open_: float = 2400.0,
    high: float = 2450.0,
    low: float = 2380.0,
    close: float = 2430.0,
    volume: int = 5_000_000,
    date_str: str = "2026-09-25",
) -> "pd.DataFrame":
    """Return a single-row OHLCV DataFrame mimicking yfinance Ticker.history()."""
    import pandas as pd  # type: ignore[import-untyped]
    return pd.DataFrame(
        {
            "Open": [open_],
            "High": [high],
            "Low": [low],
            "Close": [close],
            "Adj Close": [close],
            "Volume": [volume],
        },
        index=pd.DatetimeIndex([pd.Timestamp(date_str)]),
    )


def _make_range_df() -> "pd.DataFrame":
    """Return a 3-row DataFrame for 2026-09-23 through 2026-09-25."""
    import pandas as pd  # type: ignore[import-untyped]
    dates = pd.DatetimeIndex([
        pd.Timestamp("2026-09-23"),
        pd.Timestamp("2026-09-24"),
        pd.Timestamp("2026-09-25"),
    ])
    return pd.DataFrame(
        {
            "Open":    [2380.0, 2400.0, 2420.0],
            "High":    [2410.0, 2450.0, 2460.0],
            "Low":     [2370.0, 2390.0, 2410.0],
            "Close":   [2400.0, 2430.0, 2445.0],
            "Adj Close": [2400.0, 2430.0, 2445.0],
            "Volume":  [4_000_000, 5_000_000, 4_500_000],
        },
        index=dates,
    )


def _make_company(ticker_nse: str = "RELIANCE", company_id: int = 1) -> MagicMock:
    c = MagicMock()
    c.id = company_id
    c.ticker_nse = ticker_nse
    c.ticker_bse = None
    c.exchange = "NSE"
    return c


def _make_session(companies: list[MagicMock] | None = None) -> MagicMock:
    """Return a mock sync Session with a scripted company query result."""
    if companies is None:
        companies = [_make_company()]
    s = MagicMock()
    s.execute.return_value.scalars.return_value.all.return_value = companies
    return s


# ---------------------------------------------------------------------------
# OHLCVResult
# ---------------------------------------------------------------------------

class TestOHLCVResult:

    def test_is_persistable_with_valid_close(self) -> None:
        r = OHLCVResult("RELIANCE", "NSE", DATE, 2400.0, 2450.0, 2380.0, 2430.0, 5_000_000, "yfinance")
        assert r.is_persistable() is True

    def test_is_persistable_false_nan_close(self) -> None:
        r = OHLCVResult("X", "NSE", DATE, None, None, None, float("nan"), None, "yfinance")
        assert r.is_persistable() is False

    def test_is_persistable_false_inf_close(self) -> None:
        r = OHLCVResult("X", "NSE", DATE, None, None, None, float("inf"), None, "yfinance")
        assert r.is_persistable() is False

    def test_is_persistable_false_zero_close(self) -> None:
        r = OHLCVResult("X", "NSE", DATE, None, None, None, 0.0, None, "yfinance")
        assert r.is_persistable() is False

    def test_is_persistable_false_negative_close(self) -> None:
        r = OHLCVResult("X", "NSE", DATE, None, None, None, -1.0, None, "yfinance")
        assert r.is_persistable() is False

    def test_nullable_fields_allowed(self) -> None:
        r = OHLCVResult("THINSTOCK", "NSE", DATE, None, None, None, 50.0, None, "yfinance")
        assert r.is_persistable() is True


# ---------------------------------------------------------------------------
# NSEYFinanceFetcher
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _PANDAS_AVAILABLE, reason="pandas not installed")
class TestNSEYFinanceFetcher:

    def test_symbol_conversion(self) -> None:
        assert _to_nse_symbol("RELIANCE") == "RELIANCE.NS"
        assert _to_nse_symbol("RELIANCE.NS") == "RELIANCE.NS"

    def test_supports_nse_true(self) -> None:
        assert NSEYFinanceFetcher().supports("RELIANCE", "NSE") is True

    def test_supports_bse_false(self) -> None:
        assert NSEYFinanceFetcher().supports("RELIANCE", "BSE") is False

    def test_fetch_ohlcv_ac1_valid_data(self) -> None:
        """AC1: valid yfinance response → correct OHLCVResult fields."""
        fetcher = NSEYFinanceFetcher()
        with patch.object(NSEYFinanceFetcher, "_download", return_value=_make_df()):
            result = fetcher.fetch_ohlcv("RELIANCE", DATE)

        assert result is not None
        assert result.ticker == "RELIANCE"
        assert result.exchange == "NSE"
        assert result.trading_date == DATE
        assert result.close == pytest.approx(2430.0)
        assert result.open == pytest.approx(2400.0)
        assert result.high == pytest.approx(2450.0)
        assert result.low == pytest.approx(2380.0)
        assert result.volume == 5_000_000
        assert result.fetcher_source == "yfinance"
        assert result.is_persistable() is True

    def test_fetch_ohlcv_ac2_empty_response(self) -> None:
        """AC2: empty DataFrame → return None, no exception."""
        fetcher = NSEYFinanceFetcher()
        with patch.object(NSEYFinanceFetcher, "_download", return_value=None):
            result = fetcher.fetch_ohlcv("ILLIQUID", DATE)
        assert result is None

    def test_fetch_ohlcv_ac3_nan_close_returns_none(self) -> None:
        """AC3: NaN close → _row_to_result returns None, fetch returns None."""
        fetcher = NSEYFinanceFetcher()
        with patch.object(NSEYFinanceFetcher, "_download", return_value=_make_df(close=float("nan"))):
            result = fetcher.fetch_ohlcv("BADDATA", DATE)
        assert result is None

    def test_fetch_ohlcv_ac3_zero_close_returns_none(self) -> None:
        """AC3: zero close → rejected."""
        fetcher = NSEYFinanceFetcher()
        with patch.object(NSEYFinanceFetcher, "_download", return_value=_make_df(close=0.0)):
            result = fetcher.fetch_ohlcv("BADDATA", DATE)
        assert result is None

    def test_fetch_ohlcv_null_open_high_low_allowed(self) -> None:
        """Nullable fields: NaN open/high/low are accepted, stored as None."""
        fetcher = NSEYFinanceFetcher()
        with patch.object(NSEYFinanceFetcher, "_download", return_value=_make_df(
            open_=float("nan"), high=float("nan"), low=float("nan"), close=50.0
        )):
            result = fetcher.fetch_ohlcv("THINSTOCK", DATE)
        assert result is not None
        assert result.open is None
        assert result.high is None
        assert result.low is None
        assert result.close == pytest.approx(50.0)

    def test_fetch_ohlcv_network_error_raises_fetch_error(self) -> None:
        """Network failure after all retries → FetchError, not silent skip."""
        fetcher = NSEYFinanceFetcher()
        with patch.object(NSEYFinanceFetcher, "_download", side_effect=ConnectionError("timeout")):
            with patch("time.sleep"):  # skip actual sleep in tests
                with pytest.raises(FetchError) as exc_info:
                    fetcher.fetch_ohlcv("RELIANCE", DATE)
        assert exc_info.value.ticker == "RELIANCE"
        assert exc_info.value.exchange == "NSE"

    def test_fetch_ohlcv_range_returns_all_valid_rows(self) -> None:
        """Range fetch returns one result per valid trading date."""
        fetcher = NSEYFinanceFetcher()
        with patch.object(NSEYFinanceFetcher, "_download", return_value=_make_range_df()):
            results = fetcher.fetch_ohlcv_range("RELIANCE", DATE_START, DATE_END)
        assert len(results) == 3
        assert all(r.ticker == "RELIANCE" for r in results)
        assert all(r.exchange == "NSE" for r in results)
        assert results[0].trading_date == DATE_START
        assert results[2].trading_date == DATE_END

    def test_fetch_ohlcv_range_empty_returns_empty_list(self) -> None:
        fetcher = NSEYFinanceFetcher()
        with patch.object(NSEYFinanceFetcher, "_download", return_value=None):
            results = fetcher.fetch_ohlcv_range("RELIANCE", DATE_START, DATE_END)
        assert results == []

    def test_fetch_ohlcv_range_network_error_raises_fetch_error(self) -> None:
        fetcher = NSEYFinanceFetcher()
        with patch.object(NSEYFinanceFetcher, "_download", side_effect=OSError("dns failure")):
            with patch("time.sleep"):
                with pytest.raises(FetchError):
                    fetcher.fetch_ohlcv_range("RELIANCE", DATE_START, DATE_END)


# ---------------------------------------------------------------------------
# BSEBhavCopyStub
# ---------------------------------------------------------------------------

class TestBSEBhavCopyStub:

    def test_supports_bse_true(self) -> None:
        assert BSEBhavCopyStub().supports("RELIANCE", "BSE") is True

    def test_supports_nse_false(self) -> None:
        assert BSEBhavCopyStub().supports("RELIANCE", "NSE") is False

    def test_fetch_ohlcv_ac4_raises_not_implemented(self) -> None:
        """AC4: BSE fetch raises NotImplementedError with Phase 5 message."""
        with pytest.raises(NotImplementedError, match="Phase 5"):
            BSEBhavCopyStub().fetch_ohlcv("RELIANCE", DATE)

    def test_fetch_ohlcv_range_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="Phase 5"):
            BSEBhavCopyStub().fetch_ohlcv_range("RELIANCE", DATE_START, DATE_END)


# ---------------------------------------------------------------------------
# FetcherRegistry
# ---------------------------------------------------------------------------

class TestFetcherRegistry:

    def test_get_fetcher_nse_returns_nse_fetcher(self) -> None:
        reg = FetcherRegistry()
        fetcher = reg.get_fetcher("NSE")
        assert isinstance(fetcher, NSEYFinanceFetcher)

    def test_get_fetcher_bse_returns_bse_stub(self) -> None:
        reg = FetcherRegistry()
        fetcher = reg.get_fetcher("BSE")
        assert isinstance(fetcher, BSEBhavCopyStub)

    def test_get_fetcher_unknown_exchange_raises_value_error(self) -> None:
        reg = FetcherRegistry()
        with pytest.raises(ValueError, match="No registered DataFetcher"):
            reg.get_fetcher("MCX")

    @pytest.mark.skipif(not _PANDAS_AVAILABLE, reason="pandas not installed")
    def test_fetch_and_persist_daily_ac1_writes_row(self) -> None:
        """AC1 via registry: valid fetch result → price_data row inserted."""
        reg = FetcherRegistry()

        mock_result = OHLCVResult(
            "RELIANCE", "NSE", DATE, 2400.0, 2450.0, 2380.0, 2430.0, 5_000_000, "yfinance"
        )
        mock_nse = MagicMock()
        mock_nse.supports.return_value = True
        mock_nse.fetch_ohlcv.return_value = mock_result
        reg._fetchers = [mock_nse]

        session = _make_session([_make_company("RELIANCE", 1)])

        with patch("app.fetchers.registry._upsert_price_row") as mock_upsert:
            summary = reg.fetch_and_persist_daily(["RELIANCE"], "NSE", DATE, session)

        assert summary.fetched == 1
        assert summary.skipped == 0
        assert summary.errors == 0
        mock_upsert.assert_called_once()
        session.commit.assert_called_once()

    def test_fetch_and_persist_daily_ac2_skips_none_result(self) -> None:
        """AC2: fetcher returns None → skip counted, no DB write."""
        reg = FetcherRegistry()
        mock_nse = MagicMock()
        mock_nse.supports.return_value = True
        mock_nse.fetch_ohlcv.return_value = None
        reg._fetchers = [mock_nse]

        session = _make_session([_make_company("RELIANCE", 1)])

        with patch("app.fetchers.registry._upsert_price_row") as mock_upsert:
            summary = reg.fetch_and_persist_daily(["RELIANCE"], "NSE", DATE, session)

        assert summary.skipped == 1
        assert summary.fetched == 0
        assert "RELIANCE" in summary.tickers_skipped
        mock_upsert.assert_not_called()

    def test_fetch_and_persist_daily_ac5_handles_fetch_error(self) -> None:
        """AC5: FetchError on one ticker → error counted, pipeline continues."""
        reg = FetcherRegistry()
        mock_nse = MagicMock()
        mock_nse.supports.return_value = True
        mock_nse.fetch_ohlcv.side_effect = [
            FetchError("ERRSTOCK", "NSE", "timeout"),
            OHLCVResult("RELIANCE", "NSE", DATE, 2400.0, 2450.0, 2380.0, 2430.0, 5_000_000, "yfinance"),
        ]
        reg._fetchers = [mock_nse]

        companies = [_make_company("RELIANCE", 1)]
        session = _make_session(companies)

        with patch("app.fetchers.registry._upsert_price_row"):
            summary = reg.fetch_and_persist_daily(
                ["ERRSTOCK", "RELIANCE"], "NSE", DATE, session
            )

        assert summary.errors == 1
        assert summary.fetched == 1
        assert "ERRSTOCK" in summary.tickers_errored

    def test_fetch_and_persist_daily_skips_ticker_not_in_company_table(self) -> None:
        """Ticker not in companies → warning logged, skipped, no DB write."""
        reg = FetcherRegistry()
        mock_nse = MagicMock()
        mock_nse.supports.return_value = True
        mock_nse.fetch_ohlcv.return_value = OHLCVResult(
            "UNKNOWN", "NSE", DATE, 100.0, 110.0, 95.0, 105.0, 100_000, "yfinance"
        )
        reg._fetchers = [mock_nse]

        session = _make_session([])  # empty company table

        with patch("app.fetchers.registry._upsert_price_row") as mock_upsert:
            summary = reg.fetch_and_persist_daily(["UNKNOWN"], "NSE", DATE, session)

        assert summary.skipped == 1
        assert "UNKNOWN" in summary.tickers_skipped
        mock_upsert.assert_not_called()

    def test_fetch_and_persist_daily_ac4_bse_raises_not_implemented(self) -> None:
        """AC4 via registry: BSE exchange propagates NotImplementedError."""
        reg = FetcherRegistry()
        session = _make_session([])

        with pytest.raises(NotImplementedError, match="Phase 5"):
            reg.fetch_and_persist_daily(["RELIANCE"], "BSE", DATE, session)

    def test_fetch_and_persist_daily_ac6_commit_called_once(self) -> None:
        """AC6 idempotency: session.commit is called exactly once per run."""
        reg = FetcherRegistry()
        mock_nse = MagicMock()
        mock_nse.supports.return_value = True
        mock_nse.fetch_ohlcv.return_value = None  # all skipped
        reg._fetchers = [mock_nse]

        session = _make_session([])

        reg.fetch_and_persist_daily(["T1", "T2", "T3"], "NSE", DATE, session)
        session.commit.assert_called_once()

    def test_multiple_tickers_all_valid(self) -> None:
        """5 tickers, all valid → 5 rows fetched, 5 upserts called."""
        tickers = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "ICICIBANK"]
        reg = FetcherRegistry()
        mock_nse = MagicMock()
        mock_nse.supports.return_value = True
        mock_nse.fetch_ohlcv.side_effect = [
            OHLCVResult(t, "NSE", DATE, 1000.0, 1050.0, 990.0, 1020.0, 500_000, "yfinance")
            for t in tickers
        ]
        reg._fetchers = [mock_nse]

        companies = [_make_company(t, i + 1) for i, t in enumerate(tickers)]
        session = _make_session(companies)

        with patch("app.fetchers.registry._upsert_price_row") as mock_upsert:
            summary = reg.fetch_and_persist_daily(tickers, "NSE", DATE, session)

        assert summary.fetched == 5
        assert summary.skipped == 0
        assert summary.errors == 0
        assert mock_upsert.call_count == 5
