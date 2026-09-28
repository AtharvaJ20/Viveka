"""BSE Bhavcopy fetcher stub (Phase 5 placeholder).

Registered in FetcherRegistry so the router exists in Phase 1 and Phase 5
adds the real implementation without touching the registry or pipeline.

The official BSE Bhavcopy CSV is published at bhavdata.bseindia.com after
market close each day. When Phase 5 implements this stub, it should:
  1. Download the daily equity Bhavcopy CSV for the trading date.
  2. Filter rows where SC_TYPE == 'Q' (equity mainboard, not preference/rights).
  3. Map BSE scrip code to company_id via companies.ticker_bse.
  4. Parse OPEN, HIGH, LOW, CLOSE, TRDQTY columns into OHLCVResult.
  5. Persist via FetcherRegistry._upsert_price_row() — same path as NSE.

Do NOT remove this stub before Phase 5 is ready. The registry must always
have a handler registered for BSE, even if it raises NotImplementedError,
so that accidental BSE fetch attempts fail loudly rather than silently
routing to the NSE fetcher.
"""
from __future__ import annotations

from datetime import date

from app.fetchers import OHLCVResult

_NOT_IMPLEMENTED_MSG = (
    "BSE Bhavcopy fetcher not implemented until Phase 5. "
    "Register BSEBhavCopyFetcher in FetcherRegistry at that point."
)


class BSEBhavCopyStub:
    """Placeholder — raises NotImplementedError on any data request."""

    def supports(self, ticker: str, exchange: str) -> bool:
        return exchange == "BSE"

    def fetch_ohlcv(self, ticker: str, trading_date: date) -> OHLCVResult | None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def fetch_ohlcv_range(
        self, ticker: str, start: date, end: date
    ) -> list[OHLCVResult]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)


# Module-level instance
bse_stub = BSEBhavCopyStub()
