"""T-VIS-02: Trigger analysis for sector move explanations.

For each of the top-N ranked sectors (from T-VIS-01), the top constituent
stock's recent exchange announcements and news items are fetched from the
news_items table. If matching news exists, LLMClient produces a 2–4 sentence
trigger summary. If no news is found, the fixed text NO_TRIGGER_TEXT is
returned without making any LLM call (zero tokens consumed).

Cost guard: analyze_triggers checks monthly LLM spend before any API calls.
If spend has reached COST_GUARD_PCT (default 90%) of the configured ceiling,
all results are set to NO_TRIGGER_TEXT and a warning is logged. Rankings are
always published regardless — they are computed without LLM involvement.

No-trigger fallback (AC2): The LLM is never called when no news is available.
This prevents hallucinated explanations for moves with no identifiable cause.
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.market import NewsItem
from app.jobs.ranking import SectorRank
from app.services.llm_client import (
    CostCeilingExceeded,
    LLMClient,
    LLMRequest,
    _monthly_spend_inr,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NO_TRIGGER_TEXT: str = "No identifiable trigger found for this move."

TRIGGER_TASK: str = "sector_trigger"
TOP_N_SECTORS: int = 3
NEWS_LOOKBACK_HOURS: int = 24
COST_GUARD_PCT: float = 0.90  # skip all LLM calls if monthly spend >= 90% of ceiling

_SYSTEM_PROMPT: str = (
    "You are a financial news analyst for Indian equity markets. "
    "Your job is to identify the specific catalyst that caused a stock's "
    "unusually large intraday price move on the NSE.\n"
    "Write exactly 2–4 sentences. Be specific: name the event, the announcement, "
    "or the earnings result that matches the move. "
    'If the provided news does not clearly explain the move, respond with exactly: '
    '"No identifiable trigger found for this move." — do not speculate or invent reasons.'
)


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class TriggerResult:
    """Trigger analysis result for a single stock."""

    ticker: str
    sector_name: str
    trigger_summary: str
    news_urls_used: list[str] = field(default_factory=list)
    model_used: str = ""
    tokens_used: int = 0


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _fetch_news_for_ticker(
    session: Session,
    ticker: str,
    as_of_date: datetime.date,
    lookback_hours: int = NEWS_LOOKBACK_HOURS,
) -> list[NewsItem]:
    """Return news_items rows for ticker published within lookback_hours of end-of-day.

    Window: (midnight UTC on as_of_date − lookback_hours) to midnight UTC next day.
    For default lookback=24h and as_of_date=2026-09-26: window is
    2026-09-26T00:00Z → 2026-09-27T00:00Z.
    """
    end_dt = datetime.datetime(
        as_of_date.year, as_of_date.month, as_of_date.day,
        tzinfo=datetime.timezone.utc,
    ) + datetime.timedelta(days=1)
    start_dt = end_dt - datetime.timedelta(hours=lookback_hours)

    rows = session.execute(
        select(NewsItem)
        .where(
            and_(
                NewsItem.ticker == ticker,
                NewsItem.published_at >= start_dt,
                NewsItem.published_at < end_dt,
            )
        )
        .order_by(NewsItem.published_at.desc())
    ).scalars().all()
    return list(rows)


def _build_user_prompt(
    ticker: str,
    sector_name: str,
    pct_change: float,
    news_items: list[NewsItem],
) -> str:
    direction = "up" if pct_change >= 0 else "down"
    headlines = "\n".join(
        f"- [{item.source_name}] {item.headline} ({item.url})" for item in news_items
    )
    return (
        f"Stock: {ticker} (sector: {sector_name}) moved {direction} "
        f"{abs(pct_change):.2f}% today.\n\n"
        f"Recent announcements and news items:\n{headlines}\n\n"
        f"Identify the trigger for this move in 2–4 sentences."
    )


def _no_trigger_result(sector: SectorRank) -> TriggerResult:
    return TriggerResult(
        ticker=sector.top_constituent.ticker,
        sector_name=sector.sector_name,
        trigger_summary=NO_TRIGGER_TEXT,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_triggers(
    session: Session,
    ranked_sectors: list[SectorRank],
    date: datetime.date,
    llm_client: LLMClient | None = None,
    top_n: int = TOP_N_SECTORS,
    news_lookback_hours: int = NEWS_LOOKBACK_HOURS,
    cost_guard_pct: float = COST_GUARD_PCT,
) -> list[TriggerResult]:
    """Produce trigger summaries for the top_n sectors' strongest constituents.

    For each of the top_n sectors (by sector_score descending):
      1. Fetch recent news from news_items for the top_constituent ticker.
      2. If no news found or no llm_client: append NO_TRIGGER_TEXT, no LLM call.
      3. If news found and llm_client available: call LLM for a 2–4 sentence summary.

    Pre-flight cost guard: if monthly LLM spend >= cost_guard_pct of ceiling,
    all stocks are returned as NO_TRIGGER_TEXT without any LLM call. Rankings
    (computed separately, LLM-free) are unaffected.

    Args:
        session:            Active SQLAlchemy sync session.
        ranked_sectors:     Price or volume ranking output from T-VIS-01, sorted
                            descending by sector_score.
        date:               Trading date being analysed.
        llm_client:         LLMClient instance. Pass None to skip all LLM calls
                            (all results will be NO_TRIGGER_TEXT).
        top_n:              Number of top sectors to analyse (default 3).
        news_lookback_hours: Look-back window for news_items query (default 24h).
        cost_guard_pct:     If monthly spend >= this fraction of ceiling, skip LLM.

    Returns:
        list[TriggerResult] — one entry per sector analysed (length ≤ top_n).
        Always returns results for all top_n sectors even when LLM is unavailable.
    """
    sectors_to_analyse = ranked_sectors[:top_n]
    if not sectors_to_analyse:
        return []

    # --- Pre-flight cost guard ---
    llm_available = llm_client is not None
    if llm_available:
        monthly_spend = _monthly_spend_inr(session)
        ceiling_threshold = settings.LLM_COST_CEILING_INR * cost_guard_pct
        if monthly_spend >= ceiling_threshold:
            log.warning(
                "analyze_triggers: monthly LLM spend ₹%.2f >= ₹%.2f "
                "(%.0f%% of ceiling ₹%.0f) — skipping all trigger LLM calls",
                monthly_spend,
                ceiling_threshold,
                cost_guard_pct * 100,
                settings.LLM_COST_CEILING_INR,
            )
            llm_available = False

    # --- Per-sector analysis ---
    results: list[TriggerResult] = []

    for i, sector in enumerate(sectors_to_analyse):
        ticker = sector.top_constituent.ticker
        pct_change = sector.top_constituent.score

        news_items = _fetch_news_for_ticker(session, ticker, date, news_lookback_hours)

        if not news_items or not llm_available:
            results.append(_no_trigger_result(sector))
            continue

        user_prompt = _build_user_prompt(ticker, sector.sector_name, pct_change, news_items)
        request = LLMRequest(
            task=TRIGGER_TASK,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=512,
            job_type="trigger_analysis",
        )

        try:
            response = llm_client.call(request)
            results.append(TriggerResult(
                ticker=ticker,
                sector_name=sector.sector_name,
                trigger_summary=response.content,
                news_urls_used=[item.url for item in news_items],
                model_used=response.model,
                tokens_used=response.input_tokens + response.output_tokens,
            ))
        except CostCeilingExceeded:
            log.warning(
                "analyze_triggers: cost ceiling exceeded on call for %r "
                "— filling remaining %d sector(s) with NO_TRIGGER_TEXT",
                ticker,
                len(sectors_to_analyse) - i,
            )
            results.append(_no_trigger_result(sector))
            for remaining in sectors_to_analyse[i + 1:]:
                results.append(_no_trigger_result(remaining))
            break

    return results
