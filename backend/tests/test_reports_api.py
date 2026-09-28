"""API-level tests for the reports endpoints (T-BHM-05).

DB is mocked via conftest.override_db. Auth is bypassed by overriding
_resolve_session to return a valid test session, exactly as test_auth_api.py
does. All three endpoints are covered: list, detail, and latest.
"""
from __future__ import annotations

import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine.result import ScalarResult

from app.api.deps import _resolve_session
from app.db.models.research import Report
from app.db.session import get_db
from app.main import app
from tests.conftest import TEST_EMAIL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.datetime(2026, 9, 25, 15, 33, 0, tzinfo=datetime.timezone.utc)
_TODAY = datetime.date(2026, 9, 25)


def _make_report(
    report_id: int = 1,
    report_type: str = "daily_briefing",
    trading_date: datetime.date | None = _TODAY,
    status: str = "published",
    content: dict | None = None,
) -> Report:
    r = Report(
        id=report_id,
        report_type=report_type,
        trading_date=trading_date,
        status=status,
        content=content or {"date": str(trading_date), "rankings_price": []},
        generated_at=_NOW,
    )
    return r


def _scalar_result_of(items: list) -> MagicMock:
    """Return a mock execute() result whose .scalar_one_or_none() / .scalars().all() work."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = items[0] if items else None
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items
    mock_result.scalars.return_value = mock_scalars
    mock_result.scalar_one.return_value = len(items)
    return mock_result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db_reports() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def override_db_reports(mock_db_reports: AsyncMock) -> AsyncMock:
    async def _get_mock_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db_reports

    app.dependency_overrides[get_db] = _get_mock_db
    yield mock_db_reports
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def authed_client(
    override_db_reports: AsyncMock,
    test_session,  # from conftest
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with DB mocked and session auth bypassed."""
    app.dependency_overrides[_resolve_session] = lambda: test_session
    yield
    app.dependency_overrides.pop(_resolve_session, None)


@pytest_asyncio.fixture
async def client_authed(
    override_db_reports: AsyncMock,
    test_session,
) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[_resolve_session] = lambda: test_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.pop(_resolve_session, None)


@pytest_asyncio.fixture
async def client_unauthed(
    override_db_reports: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with DB mocked but NO auth override — session cookie absent."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Auth guard: all three endpoints return 401 without a session cookie
# ---------------------------------------------------------------------------

class TestAuthGuard:
    @pytest.mark.anyio
    async def test_list_requires_auth(self, client_unauthed: AsyncClient) -> None:
        resp = await client_unauthed.get("/api/v1/reports")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_detail_requires_auth(self, client_unauthed: AsyncClient) -> None:
        resp = await client_unauthed.get("/api/v1/reports/1")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_latest_requires_auth(self, client_unauthed: AsyncClient) -> None:
        resp = await client_unauthed.get("/api/v1/reports/latest")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/reports — list
# ---------------------------------------------------------------------------

class TestListReports:
    @pytest.mark.anyio
    async def test_returns_list_with_pagination_metadata(
        self,
        client_authed: AsyncClient,
        override_db_reports: AsyncMock,
    ) -> None:
        report = _make_report(report_id=1)
        # First execute call: COUNT(*) → 1
        # Second execute call: SELECT rows → [report]
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        rows_result = MagicMock()
        rows_scalars = MagicMock()
        rows_scalars.all.return_value = [report]
        rows_result.scalars.return_value = rows_scalars

        override_db_reports.execute.side_effect = [count_result, rows_result]

        resp = await client_authed.get("/api/v1/reports")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == 1
        assert body["items"][0]["report_type"] == "daily_briefing"
        assert body["items"][0]["status"] == "published"

    @pytest.mark.anyio
    async def test_empty_list_returns_zero_total(
        self,
        client_authed: AsyncClient,
        override_db_reports: AsyncMock,
    ) -> None:
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        rows_result = MagicMock()
        rows_scalars = MagicMock()
        rows_scalars.all.return_value = []
        rows_result.scalars.return_value = rows_scalars

        override_db_reports.execute.side_effect = [count_result, rows_result]

        resp = await client_authed.get("/api/v1/reports")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    @pytest.mark.anyio
    async def test_page_size_respected(
        self,
        client_authed: AsyncClient,
        override_db_reports: AsyncMock,
    ) -> None:
        count_result = MagicMock()
        count_result.scalar_one.return_value = 50
        rows_result = MagicMock()
        rows_scalars = MagicMock()
        rows_scalars.all.return_value = [_make_report(i) for i in range(1, 6)]
        rows_result.scalars.return_value = rows_scalars

        override_db_reports.execute.side_effect = [count_result, rows_result]

        resp = await client_authed.get("/api/v1/reports?page=1&page_size=5")
        assert resp.status_code == 200
        body = resp.json()
        assert body["page_size"] == 5
        assert len(body["items"]) == 5

    @pytest.mark.anyio
    async def test_invalid_page_returns_422(self, client_authed: AsyncClient) -> None:
        resp = await client_authed.get("/api/v1/reports?page=0")
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_page_size_above_max_returns_422(self, client_authed: AsyncClient) -> None:
        resp = await client_authed.get("/api/v1/reports?page_size=101")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/reports/{id} — detail
# ---------------------------------------------------------------------------

class TestGetReport:
    @pytest.mark.anyio
    async def test_returns_full_content(
        self,
        client_authed: AsyncClient,
        override_db_reports: AsyncMock,
    ) -> None:
        content = {
            "date": "2026-09-25",
            "rankings_price": [{"rank": 1, "sector_name": "Banking", "sector_score": 2.34}],
            "rankings_volume": [],
            "triggers": [],
        }
        report = _make_report(report_id=42, content=content)
        result = MagicMock()
        result.scalar_one_or_none.return_value = report
        override_db_reports.execute.return_value = result

        resp = await client_authed.get("/api/v1/reports/42")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 42
        assert body["content"]["rankings_price"][0]["sector_name"] == "Banking"

    @pytest.mark.anyio
    async def test_unknown_id_returns_404(
        self,
        client_authed: AsyncClient,
        override_db_reports: AsyncMock,
    ) -> None:
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        override_db_reports.execute.return_value = result

        resp = await client_authed.get("/api/v1/reports/9999")
        assert resp.status_code == 404
        assert "9999" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_response_includes_generated_at_iso(
        self,
        client_authed: AsyncClient,
        override_db_reports: AsyncMock,
    ) -> None:
        report = _make_report(report_id=7)
        result = MagicMock()
        result.scalar_one_or_none.return_value = report
        override_db_reports.execute.return_value = result

        resp = await client_authed.get("/api/v1/reports/7")
        assert resp.status_code == 200
        body = resp.json()
        assert body["generated_at"] is not None
        # ISO format check — must be parseable
        datetime.datetime.fromisoformat(body["generated_at"])


# ---------------------------------------------------------------------------
# GET /api/v1/reports/latest — latest by type
# ---------------------------------------------------------------------------

class TestGetLatestReport:
    @pytest.mark.anyio
    async def test_returns_most_recent_daily_briefing(
        self,
        client_authed: AsyncClient,
        override_db_reports: AsyncMock,
    ) -> None:
        report = _make_report(report_id=10, report_type="daily_briefing")
        result = MagicMock()
        result.scalar_one_or_none.return_value = report
        override_db_reports.execute.return_value = result

        resp = await client_authed.get("/api/v1/reports/latest?type=daily_briefing")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 10
        assert body["report_type"] == "daily_briefing"

    @pytest.mark.anyio
    async def test_defaults_to_daily_briefing_type(
        self,
        client_authed: AsyncClient,
        override_db_reports: AsyncMock,
    ) -> None:
        """Omitting ?type= should default to daily_briefing (not crash or 422)."""
        report = _make_report(report_id=5)
        result = MagicMock()
        result.scalar_one_or_none.return_value = report
        override_db_reports.execute.return_value = result

        resp = await client_authed.get("/api/v1/reports/latest")
        assert resp.status_code == 200
        assert resp.json()["report_type"] == "daily_briefing"

    @pytest.mark.anyio
    async def test_no_report_returns_404(
        self,
        client_authed: AsyncClient,
        override_db_reports: AsyncMock,
    ) -> None:
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        override_db_reports.execute.return_value = result

        resp = await client_authed.get("/api/v1/reports/latest?type=daily_briefing")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_returns_content_with_provenance_fields(
        self,
        client_authed: AsyncClient,
        override_db_reports: AsyncMock,
    ) -> None:
        content = {
            "date": "2026-09-25",
            "rankings_price": [
                {
                    "rank": 1,
                    "sector_name": "Banking",
                    "sector_score": 2.34,
                    "top_constituent": {"ticker": "HDFCBANK", "score": 4.1},
                    "constituent_count": 12,
                    "map_version": "v1",
                }
            ],
            "rankings_volume": [],
            "triggers": [
                {
                    "ticker": "HDFCBANK",
                    "sector_name": "Banking",
                    "trigger_summary": "HDFC Bank reported Q2 net profit...",
                    "news_urls_used": ["https://example.com/news/1"],
                    "model_used": "claude-haiku-4-5-20251001",
                    "tokens_used": 312,
                }
            ],
        }
        report = _make_report(report_id=99, content=content)
        result = MagicMock()
        result.scalar_one_or_none.return_value = report
        override_db_reports.execute.return_value = result

        resp = await client_authed.get("/api/v1/reports/latest?type=daily_briefing")
        assert resp.status_code == 200
        body = resp.json()
        # Provenance fields (ADR-004): sector_map_version in ranking, model+urls in trigger
        ranking = body["content"]["rankings_price"][0]
        assert ranking["map_version"] == "v1"
        trigger = body["content"]["triggers"][0]
        assert trigger["model_used"] == "claude-haiku-4-5-20251001"
        assert len(trigger["news_urls_used"]) == 1
