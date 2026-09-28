"""LLM abstraction layer — ADR-005.

All LLM calls go through LLMClient. Zero direct Anthropic SDK calls outside
this module.

Cost enforcement (REQ-034, ADR-005):
  1. Monthly ceiling: ₹500. Every call checks accumulated spend before proceeding.
  2. Warning threshold: ₹350. A log.warning fires when spend crosses this level.
  3. Pre-flight estimate: uses input_tokens ≈ len(prompt)//4 and max_tokens for
     output — conservative, never under-estimates the cost of a call.

USD→INR rate: fetched once per LLMClient instance from open.er-api.com; falls
back to settings.USD_TO_INR_FALLBACK (84.0) if the FX call fails or times out.

Model routing config: MODELS dict maps a task key to a model ID. Upgrading any
single task to a different model is a one-line config change.
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from decimal import Decimal

import anthropic
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.research import LLMUsage

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model routing config (ARCH §7, ADR-005)
# ---------------------------------------------------------------------------

MODELS: dict[str, str] = {
    # Scheduled jobs — Haiku 4.5 (cost-conscious)
    "sector_trigger":       "claude-haiku-4-5-20251001",
    "watchlist_news":       "claude-haiku-4-5-20251001",
    "weekly_report":        "claude-haiku-4-5-20251001",
    # Deep research — Sonnet 4.6
    "concall_summary":      "claude-sonnet-4-6",
    "ppt_extraction":       "claude-sonnet-4-6",
    "doc_reconciliation":   "claude-sonnet-4-6",
    "earnings_quality":     "claude-sonnet-4-6",
    "orderbook_analysis":   "claude-sonnet-4-6",
    "forward_pe":           "claude-sonnet-4-6",
    "sme_research":         "claude-sonnet-4-6",
    "five_point_framework": "claude-sonnet-4-6",
}

# Token pricing in USD per 1M tokens. Verified against ADR-005 §Cost calculation.
RATES_PER_MILLION: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input_usd": 1.00, "output_usd": 5.00},
    "claude-sonnet-4-6":         {"input_usd": 3.00, "output_usd": 15.00},
}

_FX_API_URL = "https://open.er-api.com/v6/latest/USD"
_FX_TIMEOUT_SEC = 5.0

# Characters-per-token approximation used for pre-flight cost estimate.
_CHARS_PER_TOKEN = 4


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class LLMRequest:
    """Input to a single LLM API call."""

    task: str            # key in MODELS — determines which model to use
    system_prompt: str
    user_prompt: str
    max_tokens: int = 1024
    job_type: str = ""   # written to llm_usage.job_type; defaults to task if empty
    report_id: int | None = None


@dataclass
class LLMResponse:
    """Result of a successful LLM API call."""

    content: str
    input_tokens: int
    output_tokens: int
    model: str
    cost_inr: float


class CostCeilingExceeded(Exception):
    """Raised when a call would push monthly LLM spend above the configured ceiling."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _usd_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return USD cost for the given model and token counts.

    Raises:
        ValueError: if model is not in RATES_PER_MILLION.
    """
    rates = RATES_PER_MILLION.get(model)
    if rates is None:
        raise ValueError(f"No token rate data for model {model!r}. Add it to RATES_PER_MILLION.")
    return (input_tokens * rates["input_usd"] + output_tokens * rates["output_usd"]) / 1_000_000


def estimate_cost_inr(
    model: str, input_tokens: int, output_tokens: int, usd_to_inr: float
) -> float:
    """Return estimated INR cost for the given model and token counts."""
    return _usd_cost(model, input_tokens, output_tokens) * usd_to_inr


def _fetch_usd_to_inr() -> float:
    """Fetch current USD/INR exchange rate from open.er-api.com.

    Returns settings.USD_TO_INR_FALLBACK on any failure (network, parse, timeout).
    """
    try:
        resp = httpx.get(_FX_API_URL, timeout=_FX_TIMEOUT_SEC)
        resp.raise_for_status()
        rate = float(resp.json()["rates"]["INR"])
        log.debug("USD/INR fetched: %.4f", rate)
        return rate
    except Exception as exc:
        log.warning(
            "USD/INR fetch failed (%s) — using fallback %.4f",
            exc,
            settings.USD_TO_INR_FALLBACK,
        )
        return settings.USD_TO_INR_FALLBACK


def _monthly_spend_inr(session: Session) -> float:
    """Return total LLM spend in INR for the current calendar month."""
    today = datetime.date.today()
    first_of_month = datetime.datetime(
        today.year, today.month, 1, tzinfo=datetime.timezone.utc
    )
    result = session.execute(
        select(func.coalesce(func.sum(LLMUsage.cost_inr), 0)).where(
            LLMUsage.created_at >= first_of_month
        )
    ).scalar_one()
    return float(result)


def _estimate_input_tokens(system_prompt: str, user_prompt: str) -> int:
    """Rough token estimate for the combined prompt text (~4 chars per token)."""
    return max(1, len(system_prompt + user_prompt) // _CHARS_PER_TOKEN)


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------


class LLMClient:
    """Central LLM call gateway.

    All LLM calls must go through this class — no direct Anthropic SDK usage
    elsewhere (ADR-005). Every call:
      - Resolves the model from the MODELS config dict
      - Enforces the monthly INR cost ceiling (settings.LLM_COST_CEILING_INR)
      - Logs to llm_usage after a successful call

    Args:
        session:     Active SQLAlchemy sync session (used for cost queries and
                     usage logging). The caller owns the transaction.
        api_key:     Anthropic API key. Defaults to settings.ANTHROPIC_API_KEY.
        usd_to_inr:  If provided, skips the FX API fetch and uses this rate
                     directly. Useful for tests and deterministic cost checks.
    """

    def __init__(
        self,
        session: Session,
        api_key: str | None = None,
        usd_to_inr: float | None = None,
    ) -> None:
        self._session = session
        _key = api_key if api_key is not None else settings.ANTHROPIC_API_KEY
        self._client = anthropic.Anthropic(api_key=_key)
        self._usd_to_inr_override = usd_to_inr
        self._usd_to_inr_cached: float | None = None

    def _get_usd_to_inr(self) -> float:
        if self._usd_to_inr_override is not None:
            return self._usd_to_inr_override
        if self._usd_to_inr_cached is None:
            self._usd_to_inr_cached = _fetch_usd_to_inr()
        return self._usd_to_inr_cached

    def call(self, request: LLMRequest) -> LLMResponse:
        """Execute an LLM call with pre-flight cost enforcement and post-call logging.

        The pre-flight check uses a conservative estimate (max_tokens for output)
        so the ceiling can never be breached by a single call (ADR-005 §deliberate gap).

        Raises:
            KeyError: if request.task is not in MODELS.
            CostCeilingExceeded: if the call would push monthly spend over the ceiling.
            anthropic.APIError: on any Anthropic API failure (caller handles).
        """
        model = MODELS[request.task]
        usd_to_inr = self._get_usd_to_inr()

        estimated_input_tokens = _estimate_input_tokens(request.system_prompt, request.user_prompt)
        estimated_cost = estimate_cost_inr(
            model, estimated_input_tokens, request.max_tokens, usd_to_inr
        )

        monthly_spend = _monthly_spend_inr(self._session)

        if monthly_spend + estimated_cost > settings.LLM_COST_CEILING_INR:
            raise CostCeilingExceeded(
                f"Monthly LLM spend ₹{monthly_spend:.2f} + estimated ₹{estimated_cost:.4f} "
                f"would exceed ceiling ₹{settings.LLM_COST_CEILING_INR:.0f}"
            )

        if monthly_spend > settings.LLM_WARN_THRESHOLD_INR:
            log.warning(
                "LLM monthly spend ₹%.2f has exceeded warning threshold ₹%.0f",
                monthly_spend,
                settings.LLM_WARN_THRESHOLD_INR,
            )

        # --- API call ---
        message = self._client.messages.create(
            model=model,
            max_tokens=request.max_tokens,
            system=request.system_prompt,
            messages=[{"role": "user", "content": request.user_prompt}],
        )

        input_tokens: int = message.usage.input_tokens
        output_tokens: int = message.usage.output_tokens
        content: str = message.content[0].text

        actual_cost_usd = _usd_cost(model, input_tokens, output_tokens)
        actual_cost_inr = actual_cost_usd * usd_to_inr

        # --- Log usage to DB ---
        usage_row = LLMUsage(
            job_type=request.job_type or request.task,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=Decimal(str(round(actual_cost_usd, 6))),
            cost_inr=Decimal(str(round(actual_cost_inr, 4))),
            usd_to_inr_rate=Decimal(str(round(usd_to_inr, 4))),
            report_id=request.report_id,
        )
        self._session.add(usage_row)
        self._session.flush()

        log.info(
            "LLM call: task=%r model=%r input=%d output=%d cost_inr=₹%.4f monthly_total=₹%.2f",
            request.task,
            model,
            input_tokens,
            output_tokens,
            actual_cost_inr,
            monthly_spend + actual_cost_inr,
        )

        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            cost_inr=actual_cost_inr,
        )
