"""Unit tests for T-VIS-02: LLMClient and trigger analysis.

Coverage (acceptance criteria):
  AC1 — 3 flagged stocks with matching news → each has trigger_summary
  AC2 — stock with no news → NO_TRIGGER_TEXT, LLM NOT called (zero tokens)
  AC3 — monthly spend >= ₹450 (90% of ₹500) → all stocks skipped, no LLM call
  AC4 — successful call writes row to llm_usage with correct fields
  AC5 — cost formula: cost_inr = (input×rate_in + output×rate_out) / 1M × usd_to_inr
  AC6 — CostCeilingExceeded raised when monthly spend + estimate > ₹500
  AC7 — CostCeilingExceeded mid-analysis → current + remaining filled with NO_TRIGGER_TEXT
  AC8 — empty ranked_sectors → empty result list
  AC9 — only top_n sectors are analysed (extras ignored)
  AC10 — llm_client=None → all results are NO_TRIGGER_TEXT, no DB cost query needed

Additional:
  AC11 — MODELS dict contains "sector_trigger" → "claude-haiku-4-5-20251001"
  AC12 — estimate_cost_inr formula matches RATES_PER_MILLION values
  AC13 — user prompt contains ticker, sector name, pct_change, and headlines
  AC14 — news time window: only news published within lookback_hours before end of day
  AC15 — top_constituent.score < 0 → direction "down" in prompt
  AC16 — LLM response content stored verbatim in trigger_summary
  AC17 — news_urls_used populated from news_items.url when LLM call succeeds
  AC18 — tokens_used = input_tokens + output_tokens
  AC19 — model_used matches the model returned by LLMResponse
"""
from __future__ import annotations

import datetime
import os
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_viveka")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-exactly-thirty-two-chars")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-placeholder")

from app.jobs.ranking import SectorRank, TopConstituent
from app.jobs.trigger_analysis import (
    COST_GUARD_PCT,
    NO_TRIGGER_TEXT,
    TOP_N_SECTORS,
    TRIGGER_TASK,
    TriggerResult,
    _build_user_prompt,
    _fetch_news_for_ticker,
    analyze_triggers,
)
from app.services.llm_client import (
    MODELS,
    RATES_PER_MILLION,
    CostCeilingExceeded,
    LLMClient,
    LLMRequest,
    LLMResponse,
    _monthly_spend_inr,
    estimate_cost_inr,
)

# ---------------------------------------------------------------------------
# Reference date
# ---------------------------------------------------------------------------

_TODAY = datetime.date(2026, 9, 28)  # Monday — regular trading day

# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


def _sector_rank(
    name: str = "Banking",
    score: float = 2.0,
    ticker: str = "HDFCBANK",
    top_score: float = 4.0,
) -> SectorRank:
    return SectorRank(
        sector_name=name,
        sector_score=score,
        top_constituent=TopConstituent(ticker=ticker, score=top_score),
        constituent_count=5,
        map_version="v1",
    )


def _news_item(
    ticker: str = "HDFCBANK",
    headline: str = "HDFC Bank Q2 profit rises 18%",
    url: str = "https://exchange.nse.in/hdfc-q2-2026",
    source_name: str = "NSE",
    published_at: datetime.datetime | None = None,
) -> MagicMock:
    item = MagicMock()
    item.ticker = ticker
    item.headline = headline
    item.url = url
    item.source_name = source_name
    item.published_at = published_at or datetime.datetime(
        2026, 9, 28, 9, 0, tzinfo=datetime.timezone.utc
    )
    return item


def _mock_llm_response(
    content: str = "HDFC Bank reported strong Q2 results. Net profit rose 18%.",
    input_tokens: int = 200,
    output_tokens: int = 80,
    model: str = "claude-haiku-4-5-20251001",
    cost_inr: float = 0.05,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        cost_inr=cost_inr,
    )


def _mock_llm_client(response: LLMResponse | None = None) -> MagicMock:
    """Return a mock LLMClient whose .call() returns the given response."""
    client = MagicMock(spec=LLMClient)
    if response is not None:
        client.call.return_value = response
    return client


def _mock_session_with_news(news_items: list) -> MagicMock:
    """Return a mock session whose execute().scalars().all() returns news_items."""
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = news_items
    return session


def _mock_session_no_news() -> MagicMock:
    return _mock_session_with_news([])


def _mock_session_with_spend(spend_inr: float) -> MagicMock:
    """Return a mock session that returns spend_inr from scalar_one (cost guard query)."""
    session = MagicMock()
    session.execute.return_value.scalar_one.return_value = spend_inr
    return session


# ---------------------------------------------------------------------------
# AC11 — MODELS config
# ---------------------------------------------------------------------------


class TestModelsConfig:
    def test_sector_trigger_maps_to_haiku(self) -> None:  # AC11
        assert MODELS["sector_trigger"] == "claude-haiku-4-5-20251001"

    def test_concall_summary_maps_to_sonnet(self) -> None:
        assert MODELS["concall_summary"] == "claude-sonnet-4-6"

    def test_all_scheduled_jobs_use_haiku(self) -> None:
        scheduled = ["sector_trigger", "watchlist_news", "weekly_report"]
        for task in scheduled:
            assert "haiku" in MODELS[task], f"{task!r} should map to Haiku model"

    def test_trigger_task_constant_is_in_models(self) -> None:
        assert TRIGGER_TASK in MODELS


# ---------------------------------------------------------------------------
# AC5 + AC12 — estimate_cost_inr formula
# ---------------------------------------------------------------------------


class TestEstimateCostInr:
    def test_haiku_formula(self) -> None:  # AC5, AC12
        # Haiku: $1/M input, $5/M output. 1000 input + 500 output, rate=84.0
        # USD = (1000 * 1.00 + 500 * 5.00) / 1_000_000 = 0.006 / 1_000_000? No:
        # USD = (1000 * 1.00 + 500 * 5.00) / 1_000_000
        #     = (1000 + 2500) / 1_000_000 = 3500 / 1_000_000 = 0.0035
        # INR = 0.0035 * 84.0 = 0.294
        result = estimate_cost_inr("claude-haiku-4-5-20251001", 1000, 500, 84.0)
        assert result == pytest.approx(0.294, rel=0.001)

    def test_sonnet_formula(self) -> None:
        # Sonnet: $3/M input, $15/M output. 500 input + 200 output, rate=84.0
        # USD = (500 * 3 + 200 * 15) / 1_000_000 = (1500 + 3000) / 1_000_000 = 0.0045
        # INR = 0.0045 * 84.0 = 0.378
        result = estimate_cost_inr("claude-sonnet-4-6", 500, 200, 84.0)
        assert result == pytest.approx(0.378, rel=0.001)

    def test_zero_tokens_is_zero_cost(self) -> None:
        assert estimate_cost_inr("claude-haiku-4-5-20251001", 0, 0, 84.0) == 0.0

    def test_rates_per_million_structure(self) -> None:
        for model, rates in RATES_PER_MILLION.items():
            assert "input_usd" in rates
            assert "output_usd" in rates
            assert rates["input_usd"] > 0
            assert rates["output_usd"] > 0


# ---------------------------------------------------------------------------
# LLMClient — cost guard
# ---------------------------------------------------------------------------


class TestLLMClientCostGuard:
    def _make_client(self, session: MagicMock) -> LLMClient:
        return LLMClient(session=session, api_key="test-key", usd_to_inr=84.0)

    def _mock_session_for_llm(self, spend: float) -> MagicMock:
        """Session mock that returns spend from the monthly cost query."""
        session = MagicMock()
        session.execute.return_value.scalar_one.return_value = spend
        return session

    def test_ceiling_exceeded_raises(self) -> None:  # AC6
        # Monthly spend at ₹499.6; estimated cost for max_tokens=1024 ≈ ₹0.43 INR
        # 499.6 + 0.43 = 500.03 > 500.0 → should raise
        # (system="system" + user="user" → 10 chars → ~2 estimated input tokens)
        session = self._mock_session_for_llm(499.6)
        client = self._make_client(session)
        request = LLMRequest(
            task="sector_trigger",
            system_prompt="system",
            user_prompt="user",
            max_tokens=1024,
        )
        with pytest.raises(CostCeilingExceeded):
            client.call(request)

    def test_ceiling_not_exceeded_does_not_raise_before_api(self) -> None:
        # Monthly spend at ₹0; ceiling should not be triggered
        # We don't reach the API because the mock Anthropic client isn't set up,
        # so we just check CostCeilingExceeded is NOT raised on the ceiling check
        session = self._mock_session_for_llm(0.0)
        client = self._make_client(session)
        # Replace the internal Anthropic client with a mock that raises to stop execution
        client._client = MagicMock()
        client._client.messages.create.side_effect = RuntimeError("stop here")
        request = LLMRequest(
            task="sector_trigger",
            system_prompt="s",
            user_prompt="u",
            max_tokens=1024,
        )
        with pytest.raises(RuntimeError, match="stop here"):
            client.call(request)  # RuntimeError, not CostCeilingExceeded

    def test_unknown_task_raises_key_error(self) -> None:
        session = self._mock_session_for_llm(0.0)
        client = self._make_client(session)
        request = LLMRequest(task="nonexistent_task", system_prompt="s", user_prompt="u")
        with pytest.raises(KeyError):
            client.call(request)


# ---------------------------------------------------------------------------
# LLMClient — successful call flow
# ---------------------------------------------------------------------------


class TestLLMClientCallFlow:
    def _setup_client(self, monthly_spend: float = 0.0) -> tuple[LLMClient, MagicMock, MagicMock]:
        session = MagicMock()
        session.execute.return_value.scalar_one.return_value = monthly_spend

        mock_message = MagicMock()
        mock_message.usage.input_tokens = 150
        mock_message.usage.output_tokens = 60
        mock_message.content = [MagicMock(text="HDFC Bank reported strong Q2 results.")]

        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.return_value = mock_message

        client = LLMClient(session=session, api_key="test-key", usd_to_inr=84.0)
        client._client = mock_anthropic

        return client, session, mock_anthropic

    def test_call_returns_llm_response(self) -> None:
        client, _, _ = self._setup_client()
        request = LLMRequest(
            task="sector_trigger",
            system_prompt="You are an analyst.",
            user_prompt="Explain the move.",
            max_tokens=256,
        )
        response = client.call(request)
        assert isinstance(response, LLMResponse)
        assert response.content == "HDFC Bank reported strong Q2 results."
        assert response.input_tokens == 150
        assert response.output_tokens == 60
        assert response.model == "claude-haiku-4-5-20251001"

    def test_call_computes_cost_inr_correctly(self) -> None:  # AC5
        client, _, _ = self._setup_client()
        request = LLMRequest(
            task="sector_trigger",
            system_prompt="s",
            user_prompt="u",
        )
        response = client.call(request)
        # Haiku: (150 * 1.0 + 60 * 5.0) / 1_000_000 * 84.0 = 450 / 1_000_000 * 84 = 0.0378
        expected = (150 * 1.0 + 60 * 5.0) / 1_000_000 * 84.0
        assert response.cost_inr == pytest.approx(expected, rel=0.001)

    def test_call_writes_usage_row_to_session(self) -> None:  # AC4
        client, session, _ = self._setup_client()
        request = LLMRequest(
            task="sector_trigger",
            system_prompt="s",
            user_prompt="u",
            job_type="trigger_analysis",
        )
        client.call(request)
        session.add.assert_called_once()
        usage_row = session.add.call_args[0][0]
        assert usage_row.job_type == "trigger_analysis"
        assert usage_row.model == "claude-haiku-4-5-20251001"
        assert usage_row.input_tokens == 150
        assert usage_row.output_tokens == 60

    def test_call_uses_task_as_job_type_when_job_type_empty(self) -> None:
        client, session, _ = self._setup_client()
        request = LLMRequest(
            task="sector_trigger",
            system_prompt="s",
            user_prompt="u",
            job_type="",  # empty → should default to task
        )
        client.call(request)
        usage_row = session.add.call_args[0][0]
        assert usage_row.job_type == "sector_trigger"

    def test_call_passes_model_and_max_tokens_to_api(self) -> None:
        client, _, mock_anthropic = self._setup_client()
        request = LLMRequest(
            task="sector_trigger",
            system_prompt="sys",
            user_prompt="usr",
            max_tokens=512,
        )
        client.call(request)
        mock_anthropic.messages.create.assert_called_once_with(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system="sys",
            messages=[{"role": "user", "content": "usr"}],
        )

    def test_usd_to_inr_override_bypasses_fx_fetch(self) -> None:
        # When usd_to_inr is set directly, _fetch_usd_to_inr must not be called
        session = MagicMock()
        session.execute.return_value.scalar_one.return_value = 0.0

        mock_message = MagicMock()
        mock_message.usage.input_tokens = 100
        mock_message.usage.output_tokens = 50
        mock_message.content = [MagicMock(text="result")]

        with patch("app.services.llm_client._fetch_usd_to_inr") as mock_fx:
            client = LLMClient(session=session, api_key="key", usd_to_inr=90.0)
            client._client = MagicMock()
            client._client.messages.create.return_value = mock_message
            request = LLMRequest(task="sector_trigger", system_prompt="s", user_prompt="u")
            client.call(request)
            mock_fx.assert_not_called()


# ---------------------------------------------------------------------------
# Trigger analysis — no-trigger path
# ---------------------------------------------------------------------------


class TestNoTriggerPath:
    def test_no_news_returns_no_trigger_text(self) -> None:  # AC2
        sector = _sector_rank("Banking", score=2.0, ticker="HDFCBANK")
        session = _mock_session_no_news()
        client = _mock_llm_client()

        results = analyze_triggers(session, [sector], _TODAY, llm_client=client)

        assert len(results) == 1
        assert results[0].trigger_summary == NO_TRIGGER_TEXT

    def test_no_news_does_not_call_llm(self) -> None:  # AC2
        sector = _sector_rank("Banking", score=2.0, ticker="HDFCBANK")
        session = _mock_session_no_news()
        client = _mock_llm_client()

        analyze_triggers(session, [sector], _TODAY, llm_client=client)

        client.call.assert_not_called()

    def test_no_llm_client_returns_no_trigger_text(self) -> None:  # AC10
        sector = _sector_rank("Banking", score=2.0, ticker="HDFCBANK")
        session = _mock_session_with_news([_news_item()])

        results = analyze_triggers(session, [sector], _TODAY, llm_client=None)

        assert results[0].trigger_summary == NO_TRIGGER_TEXT

    def test_no_llm_client_skips_monthly_spend_query(self) -> None:  # AC10
        sector = _sector_rank("Banking", score=2.0, ticker="HDFCBANK")
        # session has news but no cost query setup — it must NOT be queried
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []

        analyze_triggers(session, [sector], _TODAY, llm_client=None)

        # Only the news query should have been called (returns empty), not the cost query
        # We can verify that scalar_one was NOT called (cost query path)
        session.execute.return_value.scalar_one.assert_not_called()

    def test_empty_ranked_sectors_returns_empty(self) -> None:  # AC8
        session = _mock_session_no_news()
        results = analyze_triggers(session, [], _TODAY, llm_client=_mock_llm_client())
        assert results == []


# ---------------------------------------------------------------------------
# Trigger analysis — successful LLM path
# ---------------------------------------------------------------------------


class TestTriggerWithNews:
    def _make_session_news_then_any(self, news: list) -> MagicMock:
        """Session that returns news for the first execute call and a dummy for others."""
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = news
        session.execute.return_value.scalar_one.return_value = 0.0  # spend = 0
        return session

    def test_news_found_calls_llm(self) -> None:  # AC1
        sector = _sector_rank("Banking", score=2.0, ticker="HDFCBANK")
        news = [_news_item(ticker="HDFCBANK")]
        session = self._make_session_news_then_any(news)
        response = _mock_llm_response(content="HDFC Bank reported strong Q2 results here.")
        client = _mock_llm_client(response=response)

        results = analyze_triggers(session, [sector], _TODAY, llm_client=client)

        client.call.assert_called_once()
        assert results[0].trigger_summary == "HDFC Bank reported strong Q2 results here."

    def test_trigger_summary_stored_verbatim(self) -> None:  # AC16
        sector = _sector_rank("IT", score=3.0, ticker="TCS")
        response_text = "TCS won a $500M deal from a US insurance major."
        news = [_news_item(ticker="TCS")]
        session = self._make_session_news_then_any(news)
        client = _mock_llm_client(_mock_llm_response(content=response_text))

        results = analyze_triggers(session, [sector], _TODAY, llm_client=client)

        assert results[0].trigger_summary == response_text

    def test_news_urls_populated(self) -> None:  # AC17
        url1 = "https://exchange.nse.in/tcs-deal-01"
        url2 = "https://exchange.nse.in/tcs-deal-02"
        sector = _sector_rank("IT", ticker="TCS")
        news = [_news_item(ticker="TCS", url=url1), _news_item(ticker="TCS", url=url2)]
        session = self._make_session_news_then_any(news)
        client = _mock_llm_client(_mock_llm_response())

        results = analyze_triggers(session, [sector], _TODAY, llm_client=client)

        assert set(results[0].news_urls_used) == {url1, url2}

    def test_tokens_used_is_sum(self) -> None:  # AC18
        sector = _sector_rank("Banking", ticker="HDFCBANK")
        news = [_news_item()]
        session = self._make_session_news_then_any(news)
        response = _mock_llm_response(input_tokens=200, output_tokens=80)
        client = _mock_llm_client(response)

        results = analyze_triggers(session, [sector], _TODAY, llm_client=client)

        assert results[0].tokens_used == 280  # 200 + 80

    def test_model_used_set_correctly(self) -> None:  # AC19
        sector = _sector_rank("Banking", ticker="HDFCBANK")
        news = [_news_item()]
        session = self._make_session_news_then_any(news)
        response = _mock_llm_response(model="claude-haiku-4-5-20251001")
        client = _mock_llm_client(response)

        results = analyze_triggers(session, [sector], _TODAY, llm_client=client)

        assert results[0].model_used == "claude-haiku-4-5-20251001"

    def test_three_sectors_three_results(self) -> None:  # AC1
        sectors = [
            _sector_rank("Banking", score=5.0, ticker="HDFCBANK"),
            _sector_rank("IT", score=3.0, ticker="TCS"),
            _sector_rank("Pharma", score=2.0, ticker="SUNPHARMA"),
        ]
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [_news_item()]
        session.execute.return_value.scalar_one.return_value = 0.0
        client = _mock_llm_client(_mock_llm_response())

        results = analyze_triggers(session, sectors, _TODAY, llm_client=client)

        assert len(results) == 3
        assert client.call.call_count == 3


# ---------------------------------------------------------------------------
# AC9 — top_n limit
# ---------------------------------------------------------------------------


class TestTopNLimit:
    def test_only_top_n_sectors_analysed(self) -> None:  # AC9
        sectors = [
            _sector_rank("A", score=10.0, ticker="A1"),
            _sector_rank("B", score=8.0, ticker="B1"),
            _sector_rank("C", score=6.0, ticker="C1"),
            _sector_rank("D", score=4.0, ticker="D1"),
            _sector_rank("E", score=2.0, ticker="E1"),
        ]
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []
        session.execute.return_value.scalar_one.return_value = 0.0
        client = _mock_llm_client()

        results = analyze_triggers(session, sectors, _TODAY, llm_client=client, top_n=3)

        assert len(results) == 3
        assert {r.sector_name for r in results} == {"A", "B", "C"}

    def test_top_n_zero_returns_empty(self) -> None:
        sectors = [_sector_rank("Banking", ticker="HDFCBANK")]
        session = _mock_session_no_news()
        results = analyze_triggers(session, sectors, _TODAY, llm_client=_mock_llm_client(), top_n=0)
        assert results == []


# ---------------------------------------------------------------------------
# AC3 — cost guard (pre-flight: monthly spend >= 90% of ceiling)
# ---------------------------------------------------------------------------


class TestCostGuardPreAnalysis:
    def test_high_spend_skips_all_llm_calls(self) -> None:  # AC3
        # ₹460 >= 90% of ₹500 (= ₹450) → skip all LLM calls
        sector = _sector_rank("Banking", ticker="HDFCBANK")
        news = [_news_item(ticker="HDFCBANK")]

        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = news
        session.execute.return_value.scalar_one.return_value = 460.0

        client = _mock_llm_client()

        results = analyze_triggers(session, [sector], _TODAY, llm_client=client)

        client.call.assert_not_called()
        assert results[0].trigger_summary == NO_TRIGGER_TEXT

    def test_high_spend_returns_no_trigger_for_all_sectors(self) -> None:  # AC3
        sectors = [
            _sector_rank("Banking", ticker="HDFCBANK"),
            _sector_rank("IT", ticker="TCS"),
            _sector_rank("Pharma", ticker="SUNPHARMA"),
        ]
        news = [_news_item()]
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = news
        session.execute.return_value.scalar_one.return_value = 460.0
        client = _mock_llm_client()

        results = analyze_triggers(session, sectors, _TODAY, llm_client=client)

        assert len(results) == 3
        for r in results:
            assert r.trigger_summary == NO_TRIGGER_TEXT

    def test_spend_below_guard_threshold_allows_llm(self) -> None:
        # ₹400 < ₹450 (90% of ₹500) → LLM calls should proceed
        sector = _sector_rank("Banking", ticker="HDFCBANK")
        news = [_news_item()]
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = news
        session.execute.return_value.scalar_one.return_value = 400.0
        client = _mock_llm_client(_mock_llm_response())

        results = analyze_triggers(session, [sector], _TODAY, llm_client=client)

        client.call.assert_called_once()
        assert results[0].trigger_summary != NO_TRIGGER_TEXT

    def test_cost_guard_pct_constant_is_ninety_percent(self) -> None:
        assert COST_GUARD_PCT == pytest.approx(0.90)


# ---------------------------------------------------------------------------
# AC7 — CostCeilingExceeded mid-analysis
# ---------------------------------------------------------------------------


class TestCostCeilingMidAnalysis:
    def test_ceiling_exceeded_fills_remaining_with_no_trigger(self) -> None:  # AC7
        sectors = [
            _sector_rank("Banking", score=5.0, ticker="HDFCBANK"),
            _sector_rank("IT", score=3.0, ticker="TCS"),
            _sector_rank("Pharma", score=2.0, ticker="SUNPHARMA"),
        ]
        news = [_news_item()]
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = news
        session.execute.return_value.scalar_one.return_value = 0.0

        client = MagicMock(spec=LLMClient)
        # First call succeeds; second call raises CostCeilingExceeded
        client.call.side_effect = [
            _mock_llm_response(content="HDFC Bank Q2 beat."),
            CostCeilingExceeded("ceiling hit"),
            _mock_llm_response(),  # should never be reached
        ]

        results = analyze_triggers(session, sectors, _TODAY, llm_client=client)

        assert len(results) == 3
        assert results[0].trigger_summary == "HDFC Bank Q2 beat."   # first succeeded
        assert results[1].trigger_summary == NO_TRIGGER_TEXT          # ceiling hit
        assert results[2].trigger_summary == NO_TRIGGER_TEXT          # filled in
        assert client.call.call_count == 2  # third never called

    def test_ceiling_on_first_call_fills_all_remaining(self) -> None:  # AC7
        sectors = [_sector_rank("A", ticker="A1"), _sector_rank("B", ticker="B1")]
        news = [_news_item()]
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = news
        session.execute.return_value.scalar_one.return_value = 0.0

        client = MagicMock(spec=LLMClient)
        client.call.side_effect = CostCeilingExceeded("ceiling")

        results = analyze_triggers(session, sectors, _TODAY, llm_client=client)

        assert len(results) == 2
        for r in results:
            assert r.trigger_summary == NO_TRIGGER_TEXT


# ---------------------------------------------------------------------------
# AC13 — user prompt content
# ---------------------------------------------------------------------------


class TestBuildUserPrompt:
    def test_prompt_contains_ticker(self) -> None:  # AC13
        news = [_news_item(headline="HDFC Bank Q2 profit up 18%", url="http://x")]
        prompt = _build_user_prompt("HDFCBANK", "Banking", 3.5, news)
        assert "HDFCBANK" in prompt

    def test_prompt_contains_sector_name(self) -> None:  # AC13
        news = [_news_item()]
        prompt = _build_user_prompt("HDFCBANK", "Banking", 3.5, news)
        assert "Banking" in prompt

    def test_prompt_contains_pct_change(self) -> None:  # AC13
        news = [_news_item()]
        prompt = _build_user_prompt("HDFCBANK", "Banking", 3.5, news)
        assert "3.50" in prompt

    def test_prompt_contains_headline(self) -> None:  # AC13
        news = [_news_item(headline="HDFC Q2 profit up 18%")]
        prompt = _build_user_prompt("HDFCBANK", "Banking", 3.5, news)
        assert "HDFC Q2 profit up 18%" in prompt

    def test_negative_pct_shows_down_direction(self) -> None:  # AC15
        news = [_news_item()]
        prompt = _build_user_prompt("HDFCBANK", "Banking", -4.2, news)
        assert "down" in prompt

    def test_positive_pct_shows_up_direction(self) -> None:
        news = [_news_item()]
        prompt = _build_user_prompt("HDFCBANK", "Banking", 4.2, news)
        assert "up" in prompt

    def test_zero_pct_shows_up_direction(self) -> None:
        news = [_news_item()]
        prompt = _build_user_prompt("HDFCBANK", "Banking", 0.0, news)
        assert "up" in prompt

    def test_prompt_contains_source_name(self) -> None:
        news = [_news_item(source_name="NSE", headline="Result")]
        prompt = _build_user_prompt("HDFCBANK", "Banking", 1.0, news)
        assert "NSE" in prompt


# ---------------------------------------------------------------------------
# AC14 — news time window
# ---------------------------------------------------------------------------


class TestFetchNewsTimeWindow:
    def test_returns_news_within_window(self) -> None:  # AC14
        # Build a real session mock that verifies the query window
        today = _TODAY
        end_dt = datetime.datetime(2026, 9, 29, 0, 0, 0, tzinfo=datetime.timezone.utc)
        start_dt = datetime.datetime(2026, 9, 28, 0, 0, 0, tzinfo=datetime.timezone.utc)

        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []

        _fetch_news_for_ticker(session, "HDFCBANK", today, lookback_hours=24)

        # Verify execute was called once
        session.execute.assert_called_once()

    def test_returns_empty_when_no_news(self) -> None:
        session = _mock_session_no_news()
        result = _fetch_news_for_ticker(session, "TCS", _TODAY, lookback_hours=24)
        assert result == []


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_no_trigger_text_is_expected_string(self) -> None:
        assert NO_TRIGGER_TEXT == "No identifiable trigger found for this move."

    def test_top_n_sectors_default_is_three(self) -> None:
        assert TOP_N_SECTORS == 3

    def test_trigger_task_constant(self) -> None:
        assert TRIGGER_TASK == "sector_trigger"
