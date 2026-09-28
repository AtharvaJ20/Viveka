"""FetcherRegistry — routes OHLCV fetch requests by exchange.

This is the only module the pipeline (T-BHM-02 daily_briefing job) imports
from the fetcher layer. Individual fetchers are never called directly by the
pipeline.

Idempotency: fetch_and_persist_daily uses INSERT ... ON CONFLICT DO NOTHING so
running it twice for the same (company_id, trading_date, exchange) is safe.

Partial failure: a FetchError on one ticker is logged and counted in the
FetchSummary; remaining tickers still proceed. NotImplementedError (BSE stub)
propagates immediately — this is intentional (loud failure, not silent skip).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models.market import Company, PriceData
from app.fetchers import DataFetcher, FetchError, OHLCVResult
from app.fetchers.bse_stub import BSEBhavCopyStub
from app.fetchers.nse_yfinance import NSEYFinanceFetcher

log = logging.getLogger(__name__)


@dataclass
class FetchSummary:
    """Summary of a single fetch_and_persist_daily call.

    fetched: rows written to price_data (new rows only; ON CONFLICT DO NOTHING
             means re-runs do not increment this counter for existing rows).
    skipped: tickers with no data for the date (valid skip, not an error).
    errors:  tickers where FetchError was raised after all retries.
    """

    fetched: int = 0
    skipped: int = 0
    errors: int = 0
    tickers_skipped: list[str] = field(default_factory=list)
    tickers_errored: list[str] = field(default_factory=list)


class FetcherRegistry:
    """Routes OHLCV requests to the correct DataFetcher by exchange.

    Registration order determines priority: the first fetcher whose supports()
    returns True handles the request. In Phase 1, NSE is registered before BSE.

    To add a new source: instantiate it and prepend to _fetchers (to make it
    the new primary) or append (to make it a fallback).
    """

    def __init__(self) -> None:
        self._fetchers: list[DataFetcher] = [
            NSEYFinanceFetcher(),
            BSEBhavCopyStub(),
        ]

    def get_fetcher(self, exchange: str) -> DataFetcher:
        """Return the registered fetcher for exchange.

        Raises ValueError for unknown exchanges so callers fail loudly
        rather than silently routing to the wrong source.
        """
        for fetcher in self._fetchers:
            if fetcher.supports("", exchange):
                return fetcher
        raise ValueError(
            f"No registered DataFetcher supports exchange '{exchange}'. "
            f"Registered: {[type(f).__name__ for f in self._fetchers]}"
        )

    def fetch_and_persist_daily(
        self,
        tickers: list[str],
        exchange: str,
        trading_date: date,
        session: Session,
    ) -> FetchSummary:
        """Fetch OHLCV for all tickers and persist to price_data.

        Steps per ticker:
          1. Fetch via the exchange's registered DataFetcher.
          2. Validate result.is_persistable().
          3. Look up company_id from companies table (pre-fetched in bulk).
          4. Upsert into price_data (ON CONFLICT DO NOTHING).

        The session is committed once at the end; callers must not hold the
        session open across unrelated work.

        NotImplementedError (BSE stub) propagates immediately.
        FetchError is caught per ticker; other tickers continue.
        """
        fetcher = self.get_fetcher(exchange)
        summary = FetchSummary()

        company_map = self._build_company_map(session, exchange)

        for ticker in tickers:
            try:
                result = fetcher.fetch_ohlcv(ticker, trading_date)
            except FetchError as exc:
                log.error(
                    "Fetch failed for %s/%s on %s: %s",
                    exchange, ticker, trading_date, exc,
                )
                summary.errors += 1
                summary.tickers_errored.append(ticker)
                continue

            if result is None or not result.is_persistable():
                log.debug("Skipping %s/%s on %s (no valid data)", exchange, ticker, trading_date)
                summary.skipped += 1
                summary.tickers_skipped.append(ticker)
                continue

            company_id = company_map.get(ticker)
            if company_id is None:
                log.warning(
                    "Ticker %s not found in companies table (exchange=%s) — "
                    "populate T-VYS-02 sector mapping before fetching price data",
                    ticker, exchange,
                )
                summary.skipped += 1
                summary.tickers_skipped.append(ticker)
                continue

            _upsert_price_row(session, company_id, result)
            summary.fetched += 1

        session.commit()
        log.info(
            "fetch_and_persist_daily(%s, %s): fetched=%d skipped=%d errors=%d",
            exchange, trading_date, summary.fetched, summary.skipped, summary.errors,
        )
        return summary

    @staticmethod
    def _build_company_map(session: Session, exchange: str) -> dict[str, int]:
        """Return {ticker → company_id} for all companies on the exchange.

        Fetches in one query to avoid N+1 lookups inside the ticker loop.
        exchange='NSE' uses ticker_nse; exchange='BSE' uses ticker_bse.
        """
        exchange_filter = ["NSE", "BOTH"] if exchange == "NSE" else ["BSE", "BOTH"]
        companies = (
            session.execute(select(Company).where(Company.exchange.in_(exchange_filter)))
            .scalars()
            .all()
        )
        ticker_attr = "ticker_nse" if exchange == "NSE" else "ticker_bse"
        return {
            ticker: c.id
            for c in companies
            if (ticker := getattr(c, ticker_attr)) is not None
        }


def _upsert_price_row(session: Session, company_id: int, result: OHLCVResult) -> None:
    """INSERT INTO price_data ... ON CONFLICT DO NOTHING.

    The UNIQUE constraint on (company_id, trading_date, exchange) ensures
    re-runs for the same date are idempotent.
    """

    def _dec(v: float | None) -> Decimal | None:
        return Decimal(str(v)) if v is not None else None

    stmt = (
        pg_insert(PriceData)
        .values(
            company_id=company_id,
            trading_date=result.trading_date,
            exchange=result.exchange,
            open=_dec(result.open),
            high=_dec(result.high),
            low=_dec(result.low),
            close=Decimal(str(result.close)),
            volume=result.volume,
            fetcher_source=result.fetcher_source,
        )
        .on_conflict_do_nothing()
    )
    session.execute(stmt)


# Module-level singleton — the pipeline imports this
registry = FetcherRegistry()
