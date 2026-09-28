"""T-VIS-01: Sector ranking logic — price-change and volume-vs-20D-average.

Two independent rankings are produced each trading day:

  Price ranking
    Sector score = median (or max) intraday % change of a sector's constituent
    stocks.  Intraday change = (close − open) / open × 100.  Median is the
    default because it is robust to single-stock outliers in a small sector: a
    sector with nine flat stocks and one stock up 30% gets a median near 0%,
    correctly reflecting that the sector as a whole did not move.

  Volume ranking
    Sector score = (sector total volume today / sector 20-day average daily
    volume) × 100, rounded to 2 decimal places.  The 20-day average is
    computed from the PRIOR 20 calendar sessions (today excluded).  A sector
    at 150 means today's volume is 1.5× its trailing norm.

Both rankings:
  - Exclude sectors below SECTOR_MIN_CONSTITUENTS valid data points on the
    target date.  Default = 3 (D5 resolution).  Three is the minimum for
    statistics.median to represent a group rather than an individual stock.
  - Expose the single strongest constituent by absolute intraday % change
    (for both price and volume rankings).
  - Include map_version = f"v{sector.version}" per D2 resolution: the version
    field on the sectors table IS the sector map version.

Architecture note — pure vs. DB layers:
  _compute_price_ranks and _compute_volume_ranks are pure functions that accept
  pre-loaded _SectorInput objects.  They contain all business logic and are
  fully testable without mocking SQLAlchemy.  The public functions
  (compute_price_ranking, compute_volume_ranking) own the DB loading layer and
  delegate to the pure helpers.

Edge cases handled:
  - open = 0 or None → pct_change skipped for that company
  - volume = None or 0 → day contribution skipped for volume ranking
  - < SECTOR_MIN_CONSTITUENTS valid entries today → sector excluded
  - No prior-day volume data → sector excluded from volume ranking
  - volume_20d_avg = 0 → sector excluded from volume ranking
  - today_sector_vol = 0 → sector excluded from volume ranking
"""
from __future__ import annotations

import datetime
import logging
import statistics
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.market import Company, PriceData, Sector, SectorMapping

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config constants — override via function parameters when needed
# ---------------------------------------------------------------------------

SECTOR_MIN_CONSTITUENTS: int = 3  # D5: median of < 3 collapses to individual stock
SECTOR_RANK_METHOD: str = "median"  # "median" | "max"
VOLUME_LOOKBACK_DAYS: int = 20


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class TopConstituent:
    """Single strongest constituent within a ranked sector."""

    ticker: str
    score: float  # intraday % change for both price and volume rankings


@dataclass
class SectorRank:
    """Ranked sector entry returned by both ranking functions."""

    sector_name: str
    sector_score: float
    top_constituent: TopConstituent
    constituent_count: int
    map_version: str  # e.g. "v1" from sectors.version


# ---------------------------------------------------------------------------
# Private internal types (separate DB loading from computation)
# ---------------------------------------------------------------------------


@dataclass
class _PriceRow:
    trading_date: datetime.date
    open: Decimal | None
    close: Decimal
    volume: int | None


@dataclass
class _ConstituentData:
    company_id: int
    ticker: str
    rows: list[_PriceRow] = field(default_factory=list)
    # Rows are sorted descending by trading_date (most recent first).
    # Length is capped at (lookback_days + 1) entries by the loader.


@dataclass
class _SectorInput:
    sector_id: int
    sector_name: str
    map_version: str
    constituents: list[_ConstituentData] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _price_change_pct(open_p: Decimal | None, close: Decimal) -> float | None:
    """Return intraday % change or None when open is unavailable/zero."""
    if open_p is None or open_p <= 0:
        return None
    return float((close - open_p) / open_p * 100)


# ---------------------------------------------------------------------------
# Pure computation functions (testable without a DB session)
# ---------------------------------------------------------------------------


def _compute_price_ranks(
    sectors: list[_SectorInput],
    target_date: datetime.date,
    method: str,
    min_constituents: int,
) -> list[SectorRank]:
    """Rank sectors by price change using pre-loaded _SectorInput objects.

    Args:
        sectors:          Pre-loaded sector/constituent data.
        target_date:      The trading day to rank.
        method:           "median" or "max".
        min_constituents: Minimum valid data points to include a sector.

    Returns:
        List of SectorRank sorted by sector_score descending.
    """
    if method not in ("median", "max"):
        raise ValueError(f"Unknown ranking method: {method!r}. Must be 'median' or 'max'.")

    results: list[SectorRank] = []

    for sector in sectors:
        pct_changes: list[tuple[str, float]] = []  # (ticker, pct)

        for constituent in sector.constituents:
            today_row = next(
                (r for r in constituent.rows if r.trading_date == target_date),
                None,
            )
            if today_row is None:
                continue
            pct = _price_change_pct(today_row.open, today_row.close)
            if pct is not None:
                pct_changes.append((constituent.ticker, pct))

        if len(pct_changes) < min_constituents:
            log.debug(
                "_compute_price_ranks: sector %r has %d valid data points (need %d) — skipped",
                sector.sector_name,
                len(pct_changes),
                min_constituents,
            )
            continue

        values = [p for _, p in pct_changes]
        score = statistics.median(values) if method == "median" else max(values)

        top_ticker, top_score = max(pct_changes, key=lambda x: abs(x[1]))

        results.append(
            SectorRank(
                sector_name=sector.sector_name,
                sector_score=round(float(score), 2),
                top_constituent=TopConstituent(
                    ticker=top_ticker,
                    score=round(top_score, 4),
                ),
                constituent_count=len(pct_changes),
                map_version=sector.map_version,
            )
        )

    return sorted(results, key=lambda r: r.sector_score, reverse=True)


def _compute_volume_ranks(
    sectors: list[_SectorInput],
    target_date: datetime.date,
    lookback_days: int,
    min_constituents: int,
) -> list[SectorRank]:
    """Rank sectors by volume vs 20-day average using pre-loaded _SectorInput objects.

    Volume ratio = (sector total volume today / 20-day avg sector daily volume) × 100,
    rounded to 2 decimal places.  The 20-day average uses the `lookback_days` most
    recent trading sessions strictly before target_date.

    Args:
        sectors:          Pre-loaded sector/constituent data including prior-day rows.
        target_date:      The trading day to rank.
        lookback_days:    How many prior sessions to average over.
        min_constituents: Minimum valid price-change entries to include a sector.

    Returns:
        List of SectorRank sorted by sector_score descending.
    """
    results: list[SectorRank] = []

    for sector in sectors:
        today_pct_changes: list[tuple[str, float]] = []
        daily_volumes: dict[datetime.date, int] = {}  # date → sector total volume

        for constituent in sector.constituents:
            for row in constituent.rows:
                # Price change (for top_constituent and constituent_count)
                if row.trading_date == target_date:
                    pct = _price_change_pct(row.open, row.close)
                    if pct is not None:
                        today_pct_changes.append((constituent.ticker, pct))

                # Volume contribution per day
                if row.volume is not None and row.volume > 0:
                    daily_volumes[row.trading_date] = (
                        daily_volumes.get(row.trading_date, 0) + row.volume
                    )

        if len(today_pct_changes) < min_constituents:
            log.debug(
                "_compute_volume_ranks: sector %r has %d valid price entries (need %d) — skipped",
                sector.sector_name,
                len(today_pct_changes),
                min_constituents,
            )
            continue

        today_vol = daily_volumes.get(target_date, 0)
        if today_vol == 0:
            log.debug(
                "_compute_volume_ranks: sector %r has no volume for %s — skipped",
                sector.sector_name,
                target_date,
            )
            continue

        # Prior lookback_days sessions, most recent first, excluding today
        prior_sorted = sorted(
            [(d, v) for d, v in daily_volumes.items() if d < target_date],
            key=lambda x: x[0],
            reverse=True,
        )[:lookback_days]

        if not prior_sorted:
            log.debug(
                "_compute_volume_ranks: sector %r has no prior volume data — skipped",
                sector.sector_name,
            )
            continue

        prior_vols = [v for _, v in prior_sorted]
        volume_20d_avg = sum(prior_vols) / len(prior_vols)

        if volume_20d_avg == 0:
            log.debug(
                "_compute_volume_ranks: sector %r 20d avg volume is zero — skipped",
                sector.sector_name,
            )
            continue

        volume_ratio = round((today_vol / volume_20d_avg) * 100, 2)

        top_ticker, top_score = max(today_pct_changes, key=lambda x: abs(x[1]))

        results.append(
            SectorRank(
                sector_name=sector.sector_name,
                sector_score=volume_ratio,
                top_constituent=TopConstituent(
                    ticker=top_ticker,
                    score=round(top_score, 4),
                ),
                constituent_count=len(today_pct_changes),
                map_version=sector.map_version,
            )
        )

    return sorted(results, key=lambda r: r.sector_score, reverse=True)


# ---------------------------------------------------------------------------
# DB loading helper
# ---------------------------------------------------------------------------


def _load_sector_inputs(
    session: Session,
    as_of_date: datetime.date,
    exchange: str,
    lookback_days: int,
) -> list[_SectorInput]:
    """Fetch sector/constituent structure and price data from the DB.

    Makes two queries:
      1. JOIN sectors + sector_mappings + companies → sector/company structure
      2. price_data for all relevant company IDs in a generous calendar window

    Args:
        session:      Active read-only SQLAlchemy session.
        as_of_date:   Target trading date (most recent row for price ranking;
                      as_of_date + prior lookback_days rows for volume ranking).
        exchange:     Exchange code (e.g. "NSE").
        lookback_days: How many prior days of price data to load per company.
                      Pass 1 for price ranking (today only), VOLUME_LOOKBACK_DAYS
                      for volume ranking.

    Returns:
        List of _SectorInput with constituent rows populated (desc by date,
        capped at lookback_days + 1 entries per company).
    """
    # ---- Query 1: sector / company structure --------------------------------
    sector_rows = session.execute(
        select(
            Sector.id,
            Sector.name,
            Sector.version,
            Company.id,
            Company.ticker_nse,
        )
        .join(SectorMapping, SectorMapping.sector_id == Sector.id)
        .join(Company, Company.id == SectorMapping.company_id)
        .where(
            SectorMapping.is_current == True,  # noqa: E712
            Company.is_active == True,  # noqa: E712
            Company.ticker_nse.isnot(None),
        )
        .order_by(Sector.id, Company.id)
    ).all()

    if not sector_rows:
        return []

    # Build sector map and constituent lookup
    sector_map: dict[int, _SectorInput] = {}
    constituent_lookup: dict[int, _ConstituentData] = {}  # company_id → constituent

    for sector_id, sector_name, version, company_id, ticker_nse in sector_rows:
        if sector_id not in sector_map:
            sector_map[sector_id] = _SectorInput(
                sector_id=sector_id,
                sector_name=sector_name,
                map_version=f"v{version}",
            )
        cd = _ConstituentData(company_id=company_id, ticker=ticker_nse)
        sector_map[sector_id].constituents.append(cd)
        constituent_lookup[company_id] = cd

    # ---- Query 2: price data ------------------------------------------------
    # Use a generous calendar buffer: trading days are ~5/7 of calendar days.
    # Multiply lookback_days × 3 and add a 10-day buffer to guarantee coverage
    # across weekends and holidays.
    calendar_window = max(lookback_days * 3 + 10, 30)
    from_date = as_of_date - datetime.timedelta(days=calendar_window)

    price_rows = session.execute(
        select(
            PriceData.company_id,
            PriceData.trading_date,
            PriceData.open,
            PriceData.close,
            PriceData.volume,
        )
        .where(
            PriceData.company_id.in_(list(constituent_lookup.keys())),
            PriceData.exchange == exchange,
            PriceData.trading_date <= as_of_date,
            PriceData.trading_date >= from_date,
        )
        .order_by(PriceData.company_id, PriceData.trading_date.desc())
    ).all()

    max_rows = lookback_days + 1  # today + lookback_days prior sessions

    for company_id, trading_date, open_p, close, volume in price_rows:
        cd = constituent_lookup.get(company_id)
        if cd is None:
            continue
        if len(cd.rows) < max_rows:
            cd.rows.append(
                _PriceRow(
                    trading_date=trading_date,
                    open=open_p,
                    close=close,
                    volume=volume,
                )
            )

    return list(sector_map.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_price_ranking(
    session: Session,
    date: datetime.date,
    exchange: str = "NSE",
    method: str = SECTOR_RANK_METHOD,
    min_constituents: int = SECTOR_MIN_CONSTITUENTS,
) -> list[SectorRank]:
    """Compute price-change sector rankings for the given trading date.

    Args:
        session:          Active SQLAlchemy session (read-only).
        date:             Target trading date.
        exchange:         Exchange code (default "NSE").
        method:           "median" (default) or "max".
        min_constituents: Minimum constituents with valid data to include a sector.

    Returns:
        List of SectorRank ordered by sector_score descending (highest first).
        Returns [] when no sectors qualify or no price data exists.
    """
    sectors = _load_sector_inputs(session, date, exchange, lookback_days=1)
    log.info(
        "compute_price_ranking: loaded %d sectors for %s %s (method=%s)",
        len(sectors),
        date,
        exchange,
        method,
    )
    return _compute_price_ranks(sectors, date, method, min_constituents)


def compute_volume_ranking(
    session: Session,
    date: datetime.date,
    exchange: str = "NSE",
    lookback_days: int = VOLUME_LOOKBACK_DAYS,
    min_constituents: int = SECTOR_MIN_CONSTITUENTS,
) -> list[SectorRank]:
    """Compute volume-vs-20D-average sector rankings for the given trading date.

    Args:
        session:          Active SQLAlchemy session (read-only).
        date:             Target trading date.
        exchange:         Exchange code (default "NSE").
        lookback_days:    Prior sessions to average over (default 20).
        min_constituents: Minimum constituents with valid price-change data
                          to include a sector.

    Returns:
        List of SectorRank ordered by sector_score (volume ratio %) descending.
        Returns [] when no sectors qualify or insufficient volume history exists.
    """
    sectors = _load_sector_inputs(session, date, exchange, lookback_days=lookback_days)
    log.info(
        "compute_volume_ranking: loaded %d sectors for %s %s (lookback=%d)",
        len(sectors),
        date,
        exchange,
        lookback_days,
    )
    return _compute_volume_ranks(sectors, date, lookback_days, min_constituents)
