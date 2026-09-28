"""DataFetcher abstraction — ARCH §6.

The DataFetcher Protocol routes OHLCV fetch requests by exchange so the
pipeline never contains exchange-specific conditionals. Adding a new source
means: implement this Protocol, register in FetcherRegistry. No pipeline
changes required.

Registered implementations (Phase 1):
  NSE  → NSEYFinanceFetcher  (live; primary NSE source)
  BSE  → BSEBhavCopyStub     (Phase 5 placeholder; raises NotImplementedError)

Decision D3 (2026-09-26): The ranking layer (Vishwakarma T-VIS-01) computes
volume_20d_avg at query time from price_data history. The DataFetcher persists
raw daily OHLCV only — no derived fields. This keeps the fetcher stateless and
the computation in the layer that has full historical context.

News types (T-VYS-05):
  NewsAnnouncement — raw announcement from a single exchange source, shared
  between NSEAnnouncementFetcher, BSEAnnouncementFetcher, and NewsAggregator.
  Defined here to avoid circular imports across the three modules.
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable


@dataclass
class OHLCVResult:
    """One OHLCV row for a single (ticker, exchange, trading_date) combination.

    Grain: one row per (ticker, exchange, trading_date). The price_data table
    enforces this via UNIQUE(company_id, trading_date, exchange).

    open / high / low / volume may be None for suspended or illiquid sessions.
    close is always required — rows where close is NaN, inf, or <= 0 are
    rejected before persistence via is_persistable().

    fetcher_source records the implementation that produced this row so the
    provenance chain is preserved end-to-end (ADR-004 principle).
    """

    ticker: str          # bare symbol, no suffix — e.g. "RELIANCE" not "RELIANCE.NS"
    exchange: str        # "NSE" or "BSE"
    trading_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float         # required; is_persistable() rejects NaN / inf / <= 0
    volume: int | None
    fetcher_source: str  # "yfinance" | "bse_bhavcopy"

    def is_persistable(self) -> bool:
        """True only when close is a valid, finite, positive number."""
        return (
            not math.isnan(self.close)
            and not math.isinf(self.close)
            and self.close > 0
        )


class FetchError(Exception):
    """Raised by a DataFetcher after all retries are exhausted.

    Per-ticker skips (no data for the date) are signalled by returning None,
    not by raising FetchError. FetchError is reserved for unrecoverable
    network or auth failures.
    """

    def __init__(self, ticker: str, exchange: str, reason: str) -> None:
        self.ticker = ticker
        self.exchange = exchange
        self.reason = reason
        super().__init__(f"FetchError [{exchange}:{ticker}]: {reason}")


@runtime_checkable
class DataFetcher(Protocol):
    """Exchange-agnostic OHLCV data source.

    Every concrete fetcher implements exactly these three methods. The registry
    dispatches by exchange; the pipeline calls the registry and never touches
    individual fetchers directly.

    Contract:
    - fetch_ohlcv returns None when no data exists for the date (skip, not error).
    - fetch_ohlcv raises FetchError on unrecoverable failure after all retries.
    - fetch_ohlcv_range omits dates with no data (does not return None entries).
    - supports() must be pure and side-effect free (called on every routing request).
    """

    def fetch_ohlcv(self, ticker: str, trading_date: date) -> OHLCVResult | None:
        """Fetch OHLCV for one ticker on one date.

        Returns None when the market had no data (holiday, suspension, or data
        source gap). Never raises for a per-ticker data absence.
        """
        ...

    def fetch_ohlcv_range(
        self, ticker: str, start: date, end: date
    ) -> list[OHLCVResult]:
        """Fetch OHLCV for [start, end] inclusive.

        Returns only dates that have data. Empty list is valid (e.g. range
        covers only weekends).
        """
        ...

    def supports(self, ticker: str, exchange: str) -> bool:
        """True when this fetcher can service the given exchange."""
        ...


# ---------------------------------------------------------------------------
# News announcement types (T-VYS-05)
# ---------------------------------------------------------------------------


@dataclass
class NewsAnnouncement:
    """Raw announcement from a single exchange source, before company mapping.

    Produced by NSEAnnouncementFetcher and BSEAnnouncementFetcher. Consumed by
    NewsAggregator which maps ticker_raw/scrip_code to company_id and persists
    to news_items.

    Grain: one row per unique (source, url). The url field is the dedup key:
      - NSE: real HTTPS attachment URL when present; otherwise synthetic
        "nse://announcements/{symbol}/{seq_id}"
      - BSE: real HTTPS attachment URL when present; otherwise synthetic
        "bse://announcements/{scrip_code}/{dt_tm_iso}" — deterministic across
        re-fetches (Sanjaya advisory 2026-09-26).

    published_at MUST be UTC-aware. Both NSE and BSE report times in IST
    (UTC+5:30) — callers must convert before constructing this object.
    """

    source: str              # "NSE" | "BSE"
    ticker_raw: str | None   # bare NSE symbol (no .NS suffix) or None for BSE
    scrip_code: str | None   # BSE 6-digit scrip code or None for NSE
    headline: str
    url: str                 # HTTPS or synthetic scheme URL — unique per announcement
    published_at: datetime.datetime  # UTC timezone-aware
    source_name: str         # "NSE" | "BSE" → written to NewsItem.source_name
