"""News aggregator — ingests NSE/BSE announcements into news_items (T-VYS-05).

Orchestration flow:
  1. Build ticker → company_id lookup maps from the companies table.
  2. Fetch announcements from both NSE and BSE (bulk, non-per-ticker).
  3. Map each NewsAnnouncement to a NewsItem row (ticker, company_id, etc.).
  4. Bulk-insert with INSERT ... ON CONFLICT (url) DO NOTHING.
  5. Return a NewsFetchSummary with counts and any per-source error flags.

Failure policy (Sanjaya advisory 2026-09-26):
  - NSE or BSE fetch failure → empty list for that source; other source proceeds.
  - Trigger analysis still runs; it will produce NO_TRIGGER_TEXT for stocks
    with no news. Job does not abort.

Deduplication key: news_items.url (UNIQUE constraint, migration 012).
Company mapping:
  - NSE: NewsAnnouncement.ticker_raw → companies.ticker_nse → company_id
  - BSE: NewsAnnouncement.scrip_code → companies.ticker_bse → company_id
  - Unknown ticker: company_id=None, ticker populated — row still stored.
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models.market import Company, NewsItem
from app.fetchers import NewsAnnouncement
from app.fetchers.news_bse import BSEAnnouncementFetcher
from app.fetchers.news_nse import NSEAnnouncementFetcher

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Summary dataclass
# ---------------------------------------------------------------------------


@dataclass
class NewsFetchSummary:
    """Result returned by ingest_announcements."""

    nse_fetched: int = 0
    bse_fetched: int = 0
    rows_inserted: int = 0
    nse_error: bool = False
    bse_error: bool = False
    skipped_no_url: int = 0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def ingest_announcements(
    session: Session,
    date_from: datetime.date,
    date_to: datetime.date,
    nse_fetcher: NSEAnnouncementFetcher | None = None,
    bse_fetcher: BSEAnnouncementFetcher | None = None,
) -> NewsFetchSummary:
    """Fetch NSE + BSE announcements and persist them to news_items.

    Args:
        session:      SQLAlchemy sync session (caller owns the transaction).
        date_from:    Inclusive lower bound for announcements (UTC date).
        date_to:      Inclusive upper bound for announcements (UTC date).
        nse_fetcher:  Override for tests; defaults to NSEAnnouncementFetcher().
        bse_fetcher:  Override for tests; defaults to BSEAnnouncementFetcher().

    Returns:
        NewsFetchSummary with counts and error flags.
    """
    if nse_fetcher is None:
        nse_fetcher = NSEAnnouncementFetcher()
    if bse_fetcher is None:
        bse_fetcher = BSEAnnouncementFetcher()

    summary = NewsFetchSummary()

    # ------------------------------------------------------------------
    # Step 1: Build company lookup maps
    # ------------------------------------------------------------------
    nse_map, bse_map = _build_company_maps(session)

    # ------------------------------------------------------------------
    # Step 2: Fetch from both sources
    # ------------------------------------------------------------------
    nse_items = _safe_fetch(nse_fetcher, "NSE", date_from, date_to, summary)
    bse_items = _safe_fetch(bse_fetcher, "BSE", date_from, date_to, summary)

    summary.nse_fetched = len(nse_items)
    summary.bse_fetched = len(bse_items)

    all_items = nse_items + bse_items
    if not all_items:
        log.info(
            "ingest_announcements: no announcements fetched for %s–%s",
            date_from,
            date_to,
        )
        return summary

    # ------------------------------------------------------------------
    # Step 3: Map to NewsItem rows and bulk-insert
    # ------------------------------------------------------------------
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    rows: list[dict] = []

    for ann in all_items:
        row = _announcement_to_row(ann, nse_map, bse_map, now)
        if row is None:
            summary.skipped_no_url += 1
            continue
        rows.append(row)

    if rows:
        summary.rows_inserted = _bulk_insert(session, rows)

    log.info(
        "ingest_announcements: nse=%d bse=%d rows_inserted=%d for %s–%s",
        summary.nse_fetched,
        summary.bse_fetched,
        summary.rows_inserted,
        date_from,
        date_to,
    )
    return summary


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_company_maps(
    session: Session,
) -> tuple[dict[str, int], dict[str, int]]:
    """Return (nse_ticker → company_id, bse_scrip_code → company_id) maps."""
    stmt = select(Company.id, Company.ticker_nse, Company.ticker_bse)
    rows = session.execute(stmt).fetchall()

    nse_map: dict[str, int] = {}
    bse_map: dict[str, int] = {}

    for company_id, ticker_nse, ticker_bse in rows:
        if ticker_nse:
            nse_map[ticker_nse.upper().strip()] = company_id
        if ticker_bse:
            bse_map[ticker_bse.strip()] = company_id

    return nse_map, bse_map


def _safe_fetch(
    fetcher: NSEAnnouncementFetcher | BSEAnnouncementFetcher,
    source: str,
    date_from: datetime.date,
    date_to: datetime.date,
    summary: NewsFetchSummary,
) -> list[NewsAnnouncement]:
    """Call fetcher.fetch() and mark error on exception (non-fatal)."""
    try:
        return fetcher.fetch(date_from, date_to)
    except Exception as exc:
        log.warning(
            "_safe_fetch: %s fetch raised unexpectedly: %s", source, exc
        )
        if source == "NSE":
            summary.nse_error = True
        else:
            summary.bse_error = True
        return []


def _announcement_to_row(
    ann: NewsAnnouncement,
    nse_map: dict[str, int],
    bse_map: dict[str, int],
    fetched_at: datetime.datetime,
) -> dict | None:
    """Convert a NewsAnnouncement to a dict suitable for bulk insert.

    Returns None only if url is somehow empty (should not happen with
    well-formed fetchers, but guards against future bugs).
    """
    if not ann.url:
        log.debug(
            "_announcement_to_row: skipping announcement with no url: %s", ann
        )
        return None

    # Company lookup
    company_id: int | None = None
    ticker: str | None = None

    if ann.source == "NSE" and ann.ticker_raw:
        key = ann.ticker_raw.upper().strip()
        company_id = nse_map.get(key)
        ticker = key
    elif ann.source == "BSE" and ann.scrip_code:
        key = ann.scrip_code.strip()
        company_id = bse_map.get(key)
        # For BSE, store scrip_code as ticker when no company_id; or map back
        # to the canonical NSE ticker if found via company_id
        ticker = key  # stored as-is; trigger analysis queries via company_id

    return {
        "company_id": company_id,
        "ticker": ticker,
        "exchange": ann.source,
        "source_type": "exchange_announcement",
        "headline": ann.headline,
        "source_name": ann.source_name,
        "url": ann.url,
        "published_at": ann.published_at,
        "fetched_at": fetched_at,
    }


def _bulk_insert(session: Session, rows: list[dict]) -> int:
    """INSERT rows into news_items with ON CONFLICT (url) DO NOTHING.

    Returns the number of rows actually inserted (not skipped).
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(NewsItem).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["url"])

    result = session.execute(stmt)
    session.flush()

    inserted = result.rowcount if result.rowcount is not None else 0
    log.debug("_bulk_insert: %d/%d rows inserted", inserted, len(rows))
    return inserted
