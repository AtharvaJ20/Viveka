"""Tests for T-BHM-02: daily briefing pipeline orchestration.

All external dependencies (DB, LLM, fetchers) are mocked. Tests verify
the orchestration logic: correct step sequencing, staleness abort, graceful
trigger degradation, report assembly, and DB persistence.
"""
from __future__ import annotations

import datetime
from contextlib import contextmanager
from unittest.mock import MagicMock, patch, call

import pytest

from app.jobs.daily_briefing import (
    BriefingResult,
    _assemble_content,
    run_daily_briefing,
)
from app.jobs.ranking import SectorRank, TopConstituent
from app.jobs.trigger_analysis import NO_TRIGGER_TEXT, TriggerResult
from app.utils.staleness import StalenessResult
from app.fetchers.news_aggregator import NewsFetchSummary


# FetchSummary is imported lazily in daily_briefing to avoid the yfinance DLL issue.
# Create a simple stand-in for tests rather than importing from registry.
from dataclasses import dataclass, field as _field


@dataclass
class FetchSummary:  # test-local mirror of fetchers.registry.FetchSummary
    fetched: int = 0
    skipped: int = 0
    errors: int = 0
    tickers_skipped: list = _field(default_factory=list)
    tickers_errored: list = _field(default_factory=list)

# ---------------------------------------------------------------------------
# Constants and helpers
# ---------------------------------------------------------------------------

_DATE = datetime.date(2026, 9, 26)
_MODULE = "app.jobs.daily_briefing"


def _fresh(row_count: int = 60) -> StalenessResult:
    return StalenessResult(is_fresh=True, reason=f"{row_count} rows", row_count=row_count)


def _stale(row_count: int = 5) -> StalenessResult:
    return StalenessResult(
        is_fresh=False,
        reason=f"price_data has {row_count} rows for {_DATE} (NSE); need at least 50",
        row_count=row_count,
    )


def _sector_rank(name: str = "IT") -> SectorRank:
    return SectorRank(
        sector_name=name,
        sector_score=2.5,
        top_constituent=TopConstituent(ticker="TCS", score=3.1),
        constituent_count=5,
        map_version="v1",
    )


def _trigger(ticker: str = "TCS") -> TriggerResult:
    return TriggerResult(
        ticker=ticker,
        sector_name="IT",
        trigger_summary="Strong Q2 earnings beat expectations.",
        news_urls_used=["https://nse.com/tcs-q2"],
        model_used="claude-haiku-4-5-20251001",
        tokens_used=200,
    )


def _fetch_sum(**kwargs) -> FetchSummary:
    defaults = {"fetched": 50, "skipped": 0, "errors": 0}
    defaults.update(kwargs)
    return FetchSummary(**defaults)


def _news_sum(**kwargs) -> NewsFetchSummary:
    defaults = {"nse_fetched": 10, "bse_fetched": 5, "rows_inserted": 12}
    defaults.update(kwargs)
    return NewsFetchSummary(**defaults)


def _mock_report(report_id: int = 42) -> MagicMock:
    """Return a mock Report instance with pre-assigned id (simulates DB flush)."""
    r = MagicMock()
    r.id = report_id
    return r


@dataclass
class _PipelineHandles:
    """Mocks and expected values for a full-pipeline test run."""

    registry: MagicMock
    price_ranks: list
    volume_ranks: list
    triggers: list
    settings: MagicMock


@contextmanager
def _full_pipeline_ctx(
    *,
    freshness: StalenessResult | None = None,
    tickers: list[str] | None = None,
    fetch_sum: FetchSummary | None = None,
    news_sum: NewsFetchSummary | None = None,
    price_ranks: list[SectorRank] | None = None,
    volume_ranks: list[SectorRank] | None = None,
    triggers: list[TriggerResult] | None = None,
    report_id: int = 42,
    api_key: str = "test-api-key",
):
    """Context manager that patches all external dependencies for a full pipeline run.

    The FetcherRegistry is injected via run_daily_briefing's _fetch_registry param
    rather than patched — this avoids importing registry.py (and triggering the
    yfinance/pandas DLL issue) at test-collection time.
    """
    freshness = freshness if freshness is not None else _fresh()
    tickers = tickers if tickers is not None else ["TCS", "INFY"]
    fetch_sum = fetch_sum if fetch_sum is not None else _fetch_sum()
    news_sum = news_sum if news_sum is not None else _news_sum()
    price_ranks = price_ranks if price_ranks is not None else [_sector_rank("IT")]
    volume_ranks = volume_ranks if volume_ranks is not None else [_sector_rank("FMCG")]
    triggers = triggers if triggers is not None else [_trigger()]

    mock_registry = MagicMock()
    mock_registry.fetch_and_persist_daily.return_value = fetch_sum

    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = api_key

    with (
        patch(f"{_MODULE}.check_data_freshness", return_value=freshness),
        patch(f"{_MODULE}._get_active_nse_tickers", return_value=tickers),
        patch(f"{_MODULE}.ingest_announcements", return_value=news_sum),
        patch(f"{_MODULE}.compute_price_ranking", return_value=price_ranks),
        patch(f"{_MODULE}.compute_volume_ranking", return_value=volume_ranks),
        patch(f"{_MODULE}.analyze_triggers", return_value=triggers),
        patch(f"{_MODULE}.LLMClient"),
        patch(f"{_MODULE}.Report", return_value=_mock_report(report_id)),
        patch(f"{_MODULE}.settings", mock_settings),
    ):
        # yield the handles so tests can inspect call args
        yield _PipelineHandles(
            registry=mock_registry,
            price_ranks=price_ranks,
            volume_ranks=volume_ranks,
            triggers=triggers,
            settings=mock_settings,
        )


def _run(
    date=_DATE,
    session=None,
    *,
    fresh: bool = True,
    extra_patches: dict | None = None,
    **ctx_kwargs,
):
    """Helper: run run_daily_briefing inside _full_pipeline_ctx and return result."""
    if session is None:
        session = MagicMock()
    with _full_pipeline_ctx(**ctx_kwargs) as handles:
        result = run_daily_briefing(date, session, _fetch_registry=handles.registry)
        return result, handles


# ---------------------------------------------------------------------------
# TestStalenessAbort
# ---------------------------------------------------------------------------


class TestStalenessAbort:
    def _run_stale(self, row_count: int = 5):
        session = MagicMock()
        mock_registry = MagicMock()
        with patch(f"{_MODULE}.check_data_freshness", return_value=_stale(row_count)):
            result = run_daily_briefing(_DATE, session, _fetch_registry=mock_registry)
        return result, session

    def test_stale_returns_skipped_true(self):
        result, _ = self._run_stale()
        assert result.skipped is True

    def test_stale_report_id_is_none(self):
        result, _ = self._run_stale()
        assert result.report_id is None

    def test_stale_skip_reason_propagated(self):
        result, _ = self._run_stale(row_count=5)
        assert "5 rows" in result.skip_reason

    def test_stale_rankings_are_empty(self):
        result, _ = self._run_stale()
        assert result.rankings_price == []
        assert result.rankings_volume == []
        assert result.triggers == []

    def test_stale_does_not_create_report(self):
        session = MagicMock()
        mock_registry = MagicMock()
        with (
            patch(f"{_MODULE}.check_data_freshness", return_value=_stale()),
            patch(f"{_MODULE}.Report") as mock_report_cls,
        ):
            run_daily_briefing(_DATE, session, _fetch_registry=mock_registry)
        mock_report_cls.assert_not_called()

    def test_stale_does_not_call_ranking(self):
        session = MagicMock()
        mock_registry = MagicMock()
        with (
            patch(f"{_MODULE}.check_data_freshness", return_value=_stale()),
            patch(f"{_MODULE}.compute_price_ranking") as mock_price,
        ):
            run_daily_briefing(_DATE, session, _fetch_registry=mock_registry)
        mock_price.assert_not_called()

    def test_stale_does_not_call_news_ingest(self):
        session = MagicMock()
        mock_registry = MagicMock()
        with (
            patch(f"{_MODULE}.check_data_freshness", return_value=_stale()),
            patch(f"{_MODULE}.ingest_announcements") as mock_ingest,
        ):
            run_daily_briefing(_DATE, session, _fetch_registry=mock_registry)
        mock_ingest.assert_not_called()


# ---------------------------------------------------------------------------
# TestHappyPath
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_returns_briefing_result(self):
        result, _ = _run()
        assert isinstance(result, BriefingResult)

    def test_report_id_set(self):
        result, _ = _run(report_id=99)
        assert result.report_id == 99

    def test_skipped_is_false(self):
        result, _ = _run()
        assert result.skipped is False
        assert result.skip_reason is None

    def test_date_preserved(self):
        result, _ = _run()
        assert result.date == _DATE

    def test_rankings_price_populated(self):
        price = [_sector_rank("IT"), _sector_rank("FMCG")]
        result, _ = _run(price_ranks=price)
        assert result.rankings_price == price

    def test_rankings_volume_populated(self):
        volume = [_sector_rank("BANK")]
        result, _ = _run(volume_ranks=volume)
        assert result.rankings_volume == volume

    def test_triggers_populated(self):
        triggers = [_trigger("TCS"), _trigger("INFY")]
        result, _ = _run(triggers=triggers)
        assert result.triggers == triggers

    def test_report_persisted_to_session(self):
        session = MagicMock()
        with _full_pipeline_ctx() as handles:
            run_daily_briefing(_DATE, session, _fetch_registry=handles.registry)
        session.add.assert_called_once()
        session.flush.assert_called()
        session.commit.assert_called()

    def test_ohlcv_fetch_called_with_tickers_and_date(self):
        session = MagicMock()
        tickers = ["TCS", "INFY", "RELIANCE"]
        with _full_pipeline_ctx(tickers=tickers) as handles:
            run_daily_briefing(_DATE, session, _fetch_registry=handles.registry)
        handles.registry.fetch_and_persist_daily.assert_called_once_with(
            tickers, "NSE", _DATE, session
        )

    def test_ingest_announcements_called_with_date(self):
        session = MagicMock()
        with (
            _full_pipeline_ctx() as handles,
            patch(f"{_MODULE}.ingest_announcements") as mock_ingest,
        ):
            mock_ingest.return_value = _news_sum()
            run_daily_briefing(_DATE, session, _fetch_registry=handles.registry)
        mock_ingest.assert_called_once_with(session, _DATE, _DATE)

    def test_analyze_triggers_receives_price_rankings(self):
        session = MagicMock()
        price = [_sector_rank("AUTO")]
        with (
            _full_pipeline_ctx(price_ranks=price) as handles,
            patch(f"{_MODULE}.analyze_triggers") as mock_at,
        ):
            mock_at.return_value = []
            run_daily_briefing(_DATE, session, _fetch_registry=handles.registry)
        # analyze_triggers(session, ranked_sectors, date, llm_client)
        _, called_ranks, called_date, _ = mock_at.call_args[0]
        assert called_ranks == price
        assert called_date == _DATE


# ---------------------------------------------------------------------------
# TestTriggerDegradation
# ---------------------------------------------------------------------------


class TestTriggerDegradation:
    def test_trigger_exception_does_not_abort_pipeline(self):
        """analyze_triggers raises — pipeline still persists report."""
        session = MagicMock()
        with (
            _full_pipeline_ctx(report_id=77) as handles,
            patch(f"{_MODULE}.analyze_triggers", side_effect=RuntimeError("LLM down")),
            patch(f"{_MODULE}.Report", return_value=_mock_report(77)),
        ):
            result = run_daily_briefing(_DATE, session, _fetch_registry=handles.registry)
        assert result.report_id == 77
        assert result.skipped is False

    def test_trigger_exception_sets_empty_triggers(self):
        """analyze_triggers raises — result.triggers is []."""
        session = MagicMock()
        with (
            _full_pipeline_ctx() as handles,
            patch(f"{_MODULE}.analyze_triggers", side_effect=RuntimeError("LLM down")),
        ):
            result = run_daily_briefing(_DATE, session, _fetch_registry=handles.registry)
        assert result.triggers == []

    def test_rankings_still_populated_when_triggers_fail(self):
        """Rankings are included in the result even when trigger analysis fails."""
        price = [_sector_rank("IT")]
        session = MagicMock()
        with (
            _full_pipeline_ctx(price_ranks=price) as handles,
            patch(f"{_MODULE}.analyze_triggers", side_effect=ValueError("cost ceiling")),
        ):
            result = run_daily_briefing(_DATE, session, _fetch_registry=handles.registry)
        assert result.rankings_price == price

    def test_no_api_key_passes_none_llm_client(self):
        """Empty ANTHROPIC_API_KEY → llm_client=None passed to analyze_triggers."""
        session = MagicMock()
        with (
            _full_pipeline_ctx(api_key="") as handles,
            patch(f"{_MODULE}.analyze_triggers") as mock_at,
        ):
            mock_at.return_value = []
            run_daily_briefing(_DATE, session, _fetch_registry=handles.registry)
        # analyze_triggers(session, ranked_sectors, date, llm_client)
        _, _, _, llm_client_arg = mock_at.call_args[0]
        assert llm_client_arg is None


# ---------------------------------------------------------------------------
# TestReportContent
# ---------------------------------------------------------------------------


class TestReportContent:
    def test_assemble_content_has_required_keys(self):
        price = [_sector_rank("IT")]
        volume = [_sector_rank("FMCG")]
        triggers = [_trigger()]
        content = _assemble_content(
            _DATE, price, volume, triggers, _fetch_sum(), _news_sum()
        )
        assert "date" in content
        assert "generated_at" in content
        assert "rankings_price" in content
        assert "rankings_volume" in content
        assert "triggers" in content
        assert "fetch_summary" in content
        assert "news_summary" in content

    def test_assemble_content_date_is_string(self):
        content = _assemble_content(
            _DATE, [], [], [], _fetch_sum(), _news_sum()
        )
        assert content["date"] == str(_DATE)

    def test_assemble_content_provenance_in_rankings(self):
        price = [_sector_rank("IT")]
        content = _assemble_content(
            _DATE, price, [], [], _fetch_sum(), _news_sum()
        )
        ranking_entry = content["rankings_price"][0]
        assert ranking_entry["map_version"] == "v1"
        assert "top_constituent" in ranking_entry
        assert ranking_entry["top_constituent"]["ticker"] == "TCS"

    def test_assemble_content_provenance_in_triggers(self):
        triggers = [_trigger()]
        content = _assemble_content(
            _DATE, [], [], triggers, _fetch_sum(), _news_sum()
        )
        trigger_entry = content["triggers"][0]
        assert trigger_entry["model_used"] == "claude-haiku-4-5-20251001"
        assert trigger_entry["news_urls_used"] == ["https://nse.com/tcs-q2"]

    def test_assemble_content_fetch_summary_counts(self):
        content = _assemble_content(
            _DATE, [], [], [], _fetch_sum(fetched=48, errors=2), _news_sum()
        )
        assert content["fetch_summary"]["fetched"] == 48
        assert content["fetch_summary"]["errors"] == 2

    def test_assemble_content_news_summary_counts(self):
        content = _assemble_content(
            _DATE, [], [], [], _fetch_sum(), _news_sum(nse_fetched=7, bse_fetched=3, rows_inserted=9)
        )
        assert content["news_summary"]["nse_fetched"] == 7
        assert content["news_summary"]["rows_inserted"] == 9


# ---------------------------------------------------------------------------
# TestBriefingResultDataclass
# ---------------------------------------------------------------------------


class TestBriefingResultDataclass:
    def test_defaults_are_empty_lists_and_false(self):
        result = BriefingResult(report_id=None, date=_DATE)
        assert result.rankings_price == []
        assert result.rankings_volume == []
        assert result.triggers == []
        assert result.skipped is False
        assert result.skip_reason is None

    def test_skipped_result_construction(self):
        result = BriefingResult(
            report_id=None,
            date=_DATE,
            skipped=True,
            skip_reason="only 5 rows",
        )
        assert result.skipped is True
        assert result.report_id is None
        assert result.skip_reason == "only 5 rows"
