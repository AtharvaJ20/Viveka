"""T-BHM-02: Daily briefing pipeline orchestration.

Sequences the complete daily analysis for one trading date:
  1. Staleness check    — abort if price data is missing
  2. OHLCV fetch        — persist any missing rows via FetcherRegistry
  3. News ingest        — pull NSE/BSE announcements into news_items
  4. Price ranking      — sector ranks by median intraday % change
  5. Volume ranking     — sector ranks by volume-vs-20D-average
  6. Trigger analysis   — LLM explanations for top movers (degrades gracefully)
  7. Report assembly    — build JSONB content with embedded provenance
  8. Report persistence — write Report row; return BriefingResult

This function is wired as the scheduler's pipeline via _set_pipeline_fn in
main.py's lifespan startup. It is also called directly by the CLI (T-BHM-03).

Graceful degradation:
  - Stale data: returns BriefingResult(skipped=True), no DB writes.
  - No ANTHROPIC_API_KEY: llm_client=None passed to analyze_triggers; all
    triggers default to NO_TRIGGER_TEXT.
  - LLM exception inside analyze_triggers: logged, triggers=[]; rankings
    still published.
  - Any unhandled exception propagates to the scheduler, which catches it
    and marks job_executions as 'failed'.
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.market import Company
from app.db.models.research import Report
from app.fetchers.news_aggregator import NewsFetchSummary, ingest_announcements
from app.jobs.ranking import SectorRank, compute_price_ranking, compute_volume_ranking
from app.jobs.trigger_analysis import TriggerResult, analyze_triggers
from app.services.llm_client import LLMClient
from app.utils.staleness import check_data_freshness

if TYPE_CHECKING:
    from app.fetchers.registry import FetchSummary

log = logging.getLogger(__name__)

_UTC = datetime.timezone.utc


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class BriefingResult:
    """Result of a single run_daily_briefing call.

    Attributes:
        report_id:       DB id of the persisted Report row, or None if skipped.
        date:            The trading date this briefing covers.
        rankings_price:  Sector rankings by intraday price change (descending).
        rankings_volume: Sector rankings by volume-vs-20D-average (descending).
        triggers:        LLM trigger summaries for top-N sectors.
        skipped:         True when the run was aborted early (stale data, etc.).
        skip_reason:     Human-readable reason for the skip, or None.
    """

    report_id: int | None
    date: datetime.date
    rankings_price: list[SectorRank] = field(default_factory=list)
    rankings_volume: list[SectorRank] = field(default_factory=list)
    triggers: list[TriggerResult] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_active_nse_tickers(session: Session) -> list[str]:
    """Return ticker_nse for all active NSE companies."""
    rows = session.execute(
        select(Company.ticker_nse).where(
            Company.is_active == True,  # noqa: E712
            Company.ticker_nse.isnot(None),
        )
    ).scalars().all()
    return list(rows)


def _build_llm_client(session: Session) -> LLMClient | None:
    """Create LLMClient; return None if the API key is absent or init fails."""
    if not settings.ANTHROPIC_API_KEY:
        log.info(
            "run_daily_briefing: ANTHROPIC_API_KEY not set — trigger analysis will use NO_TRIGGER_TEXT"
        )
        return None
    try:
        return LLMClient(session)
    except Exception as exc:
        log.warning("run_daily_briefing: LLMClient init failed: %s", exc)
        return None


def _sector_rank_to_dict(sr: SectorRank) -> dict:
    return {
        "sector_name": sr.sector_name,
        "sector_score": sr.sector_score,
        "top_constituent": {
            "ticker": sr.top_constituent.ticker,
            "score": sr.top_constituent.score,
        },
        "constituent_count": sr.constituent_count,
        "map_version": sr.map_version,
    }


def _trigger_to_dict(tr: TriggerResult) -> dict:
    return {
        "ticker": tr.ticker,
        "sector_name": tr.sector_name,
        "trigger_summary": tr.trigger_summary,
        "news_urls_used": tr.news_urls_used,
        "model_used": tr.model_used,
        "tokens_used": tr.tokens_used,
    }


def _assemble_content(
    date: datetime.date,
    rankings_price: list[SectorRank],
    rankings_volume: list[SectorRank],
    triggers: list[TriggerResult],
    fetch_summary: FetchSummary,
    news_summary: NewsFetchSummary,
) -> dict:
    """Build the JSONB content dict for the reports table.

    Includes embedded provenance (ADR-004): sector map version per ranking entry,
    model per trigger, and news URLs used.
    """
    return {
        "date": str(date),
        "generated_at": datetime.datetime.now(tz=_UTC).isoformat(),
        "rankings_price": [_sector_rank_to_dict(r) for r in rankings_price],
        "rankings_volume": [_sector_rank_to_dict(r) for r in rankings_volume],
        "triggers": [_trigger_to_dict(t) for t in triggers],
        "fetch_summary": {
            "fetched": fetch_summary.fetched,
            "skipped": fetch_summary.skipped,
            "errors": fetch_summary.errors,
        },
        "news_summary": {
            "nse_fetched": news_summary.nse_fetched,
            "bse_fetched": news_summary.bse_fetched,
            "rows_inserted": news_summary.rows_inserted,
        },
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_daily_briefing(
    date: datetime.date,
    session: Session,
    _fetch_registry: Any = None,
) -> BriefingResult:
    """Run the complete daily briefing pipeline for a single trading date.

    Called by APScheduler via _PIPELINE_FN and by the manual re-run CLI
    (T-BHM-03). The scheduler owns job_executions tracking; this function
    owns report creation and all business logic.

    Unexpected exceptions propagate to the scheduler, which catches them and
    marks the job_executions row as 'failed'. Do not swallow unexpected errors
    — let them surface so the scheduler can record them correctly.

    Args:
        date:             The trading date to analyse (NSE market day).
        session:          Active sync SQLAlchemy session. Caller owns session lifecycle.
        _fetch_registry:  Injectable FetcherRegistry for tests. Defaults to the
                          module singleton (lazy import avoids top-level yfinance dep).

    Returns:
        BriefingResult with report_id, rankings, and triggers.
        Returns BriefingResult(skipped=True) when data is stale.
    """
    if _fetch_registry is None:
        from app.fetchers.registry import registry as _default_registry

        _fetch_registry = _default_registry

    log.info("run_daily_briefing: starting for date=%s", date)

    # ------------------------------------------------------------------
    # Step 1: Staleness check — abort if price data is missing
    # ------------------------------------------------------------------
    staleness = check_data_freshness(date, "NSE", session)
    if not staleness.is_fresh:
        log.warning(
            "run_daily_briefing: data is stale for %s — %s — aborting",
            date,
            staleness.reason,
        )
        return BriefingResult(
            report_id=None,
            date=date,
            skipped=True,
            skip_reason=staleness.reason,
        )

    # ------------------------------------------------------------------
    # Step 2: OHLCV fetch — commits session after writing rows
    # ------------------------------------------------------------------
    tickers = _get_active_nse_tickers(session)
    fetch_summary = _fetch_registry.fetch_and_persist_daily(tickers, "NSE", date, session)
    log.info(
        "run_daily_briefing: OHLCV fetch done — fetched=%d skipped=%d errors=%d",
        fetch_summary.fetched,
        fetch_summary.skipped,
        fetch_summary.errors,
    )

    # ------------------------------------------------------------------
    # Step 3: News ingest — flushes but does not commit
    # ------------------------------------------------------------------
    news_summary = ingest_announcements(session, date, date)
    log.info(
        "run_daily_briefing: news ingest done — nse=%d bse=%d inserted=%d",
        news_summary.nse_fetched,
        news_summary.bse_fetched,
        news_summary.rows_inserted,
    )

    # ------------------------------------------------------------------
    # Step 4+5: Sector rankings
    # ------------------------------------------------------------------
    rankings_price = compute_price_ranking(session, date)
    rankings_volume = compute_volume_ranking(session, date)
    log.info(
        "run_daily_briefing: rankings done — price=%d sectors volume=%d sectors",
        len(rankings_price),
        len(rankings_volume),
    )

    # ------------------------------------------------------------------
    # Step 6: Trigger analysis — degrades gracefully on LLM failure
    # ------------------------------------------------------------------
    llm_client = _build_llm_client(session)
    try:
        triggers = analyze_triggers(session, rankings_price, date, llm_client)
    except Exception as exc:
        log.error(
            "run_daily_briefing: trigger analysis raised — publishing rankings without triggers: %s",
            exc,
            exc_info=True,
        )
        triggers = []
    log.info("run_daily_briefing: trigger analysis done — %d triggers", len(triggers))

    # ------------------------------------------------------------------
    # Step 7: Assemble JSONB content with embedded provenance
    # ------------------------------------------------------------------
    content = _assemble_content(
        date, rankings_price, rankings_volume, triggers, fetch_summary, news_summary
    )

    # ------------------------------------------------------------------
    # Step 8: Persist report — flush to get id, then commit
    # ------------------------------------------------------------------
    report = Report(
        report_type="daily_briefing",
        trading_date=date,
        status="published",
        content=content,
        generated_at=datetime.datetime.now(tz=_UTC),
    )
    session.add(report)
    session.flush()
    session.commit()

    log.info(
        "run_daily_briefing: report persisted id=%d date=%s", report.id, date
    )

    return BriefingResult(
        report_id=report.id,
        date=date,
        rankings_price=rankings_price,
        rankings_volume=rankings_volume,
        triggers=triggers,
    )
