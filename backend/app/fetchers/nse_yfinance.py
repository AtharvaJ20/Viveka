"""NSE OHLCV fetcher via yfinance.

Symbol convention: bare NSE ticker (e.g. "RELIANCE") → yfinance symbol
"RELIANCE.NS". yfinance is treated as an unofficial source — responses may be
empty, delayed, or malformed. Every row is validated before being returned.

Retry policy: up to 3 attempts with 1 s / 3 s / 9 s backoff. A per-ticker
network failure after all retries raises FetchError, not a silent skip.
"""
from __future__ import annotations

import logging
import math
import time
from datetime import date, timedelta
from typing import Any

from app.fetchers import DataFetcher, FetchError, OHLCVResult

try:
    import yfinance as yf  # type: ignore[import-untyped]
    import pandas as pd    # type: ignore[import-untyped]
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "yfinance and pandas are required for NSEYFinanceFetcher. "
        "Install them: pip install yfinance pandas"
    ) from exc

log = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1, 3, 9)
_NS_SUFFIX = ".NS"


def _to_nse_symbol(ticker: str) -> str:
    return ticker if ticker.endswith(_NS_SUFFIX) else f"{ticker}{_NS_SUFFIX}"


class NSEYFinanceFetcher:
    """Fetches NSE daily OHLCV via yfinance's Ticker.history() API.

    Uses Ticker.history() rather than yf.download() because the single-ticker
    path returns a simple (non-MultiIndex) DataFrame regardless of yfinance
    version. auto_adjust=False preserves the raw unadjusted Close so that
    price_data and the ranked percentage change reflect actual traded prices.
    """

    def supports(self, ticker: str, exchange: str) -> bool:
        return exchange == "NSE"

    def fetch_ohlcv(self, ticker: str, trading_date: date) -> OHLCVResult | None:
        """Fetch a single day. Returns None when yfinance has no data."""
        yf_symbol = _to_nse_symbol(ticker)
        end = trading_date + timedelta(days=1)

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                df = self._download(yf_symbol, trading_date, end)
                if df is None or len(df) == 0:
                    log.warning(
                        "yfinance: no data for %s on %s", ticker, trading_date
                    )
                    return None
                row: Any = df.iloc[0]
                return self._row_to_result(ticker, trading_date, row)

            except FetchError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_SECONDS[attempt]
                    log.warning(
                        "yfinance fetch failed for %s (attempt %d/%d), "
                        "retrying in %ds: %s",
                        ticker, attempt + 1, _MAX_RETRIES, wait, exc,
                    )
                    time.sleep(wait)

        raise FetchError(ticker, "NSE", str(last_exc)) from last_exc

    def fetch_ohlcv_range(
        self, ticker: str, start: date, end: date
    ) -> list[OHLCVResult]:
        """Fetch a date range [start, end] inclusive."""
        yf_symbol = _to_nse_symbol(ticker)
        end_exclusive = end + timedelta(days=1)

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                df = self._download(yf_symbol, start, end_exclusive)
                if df is None or len(df) == 0:
                    log.warning(
                        "yfinance: no data for %s in %s – %s", ticker, start, end
                    )
                    return []

                results: list[OHLCVResult] = []
                for idx, row in df.iterrows():
                    row_date: date = idx.date()  # type: ignore[union-attr]
                    result = self._row_to_result(ticker, row_date, row)
                    if result is not None:
                        results.append(result)
                return results

            except FetchError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_SECONDS[attempt]
                    log.warning(
                        "yfinance range fetch failed for %s (attempt %d/%d), "
                        "retrying in %ds: %s",
                        ticker, attempt + 1, _MAX_RETRIES, wait, exc,
                    )
                    time.sleep(wait)

        raise FetchError(ticker, "NSE", str(last_exc)) from last_exc

    @staticmethod
    def _download(symbol: str, start: date, end: date) -> "pd.DataFrame | None":
        """Isolated yfinance call — the sole seam for unit-test mocking.

        auto_adjust=False: preserve raw prices (unadjusted for splits/dividends)
        actions=False: exclude Dividends and Stock Splits columns
        """
        hist: pd.DataFrame = yf.Ticker(symbol).history(
            start=str(start),
            end=str(end),
            auto_adjust=False,
            actions=False,
        )
        return hist if not hist.empty else None

    @staticmethod
    def _row_to_result(
        ticker: str, trading_date: date, row: Any
    ) -> OHLCVResult | None:
        """Convert one pandas row to OHLCVResult.

        Returns None (and logs a warning) when Close is missing or invalid.
        open / high / low / volume accept None to handle partial trading days.
        """

        def _f(col: str) -> float | None:
            val = row.get(col) if hasattr(row, "get") else getattr(row, col, None)
            if val is None:
                return None
            try:
                f = float(val)
                return None if (math.isnan(f) or math.isinf(f)) else f
            except (TypeError, ValueError):
                return None

        close = _f("Close")
        if close is None or close <= 0:
            log.warning(
                "Invalid close price for %s on %s (close=%s) — row skipped",
                ticker, trading_date, row.get("Close") if hasattr(row, "get") else "?",
            )
            return None

        raw_vol = row.get("Volume") if hasattr(row, "get") else getattr(row, "Volume", None)
        try:
            volume: int | None = int(raw_vol) if raw_vol is not None else None
            if volume == 0:
                volume = None
        except (TypeError, ValueError):
            volume = None

        return OHLCVResult(
            ticker=ticker,
            exchange="NSE",
            trading_date=trading_date,
            open=_f("Open"),
            high=_f("High"),
            low=_f("Low"),
            close=close,
            volume=volume,
            fetcher_source="yfinance",
        )


# Module-level instance — import and use directly
nse_fetcher: DataFetcher = NSEYFinanceFetcher()
