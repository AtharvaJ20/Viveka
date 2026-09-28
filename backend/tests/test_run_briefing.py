"""Tests for T-BHM-03: manual daily briefing re-run CLI.

All external dependencies (DB, pipeline, calendar) are mocked or injected.
Tests verify argument parsing, date validation, trading-day guard, idempotency,
stdout/stderr output, and exit codes.
"""
from __future__ import annotations

import datetime
import sys
from contextlib import contextmanager
from io import StringIO
from unittest.mock import MagicMock, call, patch

import pytest

from app.jobs.daily_briefing import BriefingResult
from app.jobs.run_briefing import _delete_existing_report, _parse_date, main

# ---------------------------------------------------------------------------
# Constants and helpers
# ---------------------------------------------------------------------------

_DATE = datetime.date(2026, 9, 26)          # a Friday (trading day in tests)
_MODULE = "app.jobs.run_briefing"


def _mock_session(existing_report_count: int = 0) -> MagicMock:
    """Return a mock session where execute(...).scalars().all() returns N mock reports."""
    session = MagicMock()
    reports = [MagicMock() for _ in range(existing_report_count)]
    session.execute.return_value.scalars.return_value.all.return_value = reports
    return session


@contextmanager
def _session_ctx(session: MagicMock):
    """Context-manager factory that yields the given mock session."""
    yield session


def _make_factory(session: MagicMock):
    """Return a callable that acts as a context-manager session factory."""
    def factory():
        return _session_ctx(session)
    return factory


def _success_result(report_id: int = 42) -> BriefingResult:
    return BriefingResult(
        report_id=report_id,
        date=_DATE,
        rankings_price=[],
        rankings_volume=[],
        triggers=[],
        skipped=False,
    )


def _skipped_result(reason: str = "price_data has 5 rows; need at least 50") -> BriefingResult:
    return BriefingResult(
        report_id=None,
        date=_DATE,
        skipped=True,
        skip_reason=reason,
    )


# ---------------------------------------------------------------------------
# TestParseDateHelper
# ---------------------------------------------------------------------------


class TestParseDateHelper:
    def test_valid_iso_date(self):
        assert _parse_date("2026-09-26") == datetime.date(2026, 9, 26)

    def test_invalid_format_returns_none(self):
        assert _parse_date("26-09-2026") is None

    def test_non_date_string_returns_none(self):
        assert _parse_date("not-a-date") is None

    def test_empty_string_returns_none(self):
        assert _parse_date("") is None

    def test_partial_date_returns_none(self):
        assert _parse_date("2026-09") is None


# ---------------------------------------------------------------------------
# TestDateParsing (CLI) — AC3: invalid date format → exit 1
# ---------------------------------------------------------------------------


class TestDateParsing:
    def test_invalid_date_exits_1(self, capsys):
        session = _mock_session()
        code = main(
            ["--date", "26-09-2026"],
            _session_factory=_make_factory(session),
            _briefing_fn=MagicMock(),
        )
        assert code == 1

    def test_invalid_date_prints_to_stderr(self, capsys):
        session = _mock_session()
        main(
            ["--date", "26-09-2026"],
            _session_factory=_make_factory(session),
            _briefing_fn=MagicMock(),
        )
        captured = capsys.readouterr()
        assert "Error" in captured.err
        assert "26-09-2026" in captured.err

    def test_invalid_date_expected_format_mentioned(self, capsys):
        session = _mock_session()
        main(
            ["--date", "2026/09/26"],
            _session_factory=_make_factory(session),
            _briefing_fn=MagicMock(),
        )
        captured = capsys.readouterr()
        assert "YYYY-MM-DD" in captured.err

    def test_invalid_date_nothing_on_stdout(self, capsys):
        session = _mock_session()
        main(
            ["--date", "bad-date"],
            _session_factory=_make_factory(session),
            _briefing_fn=MagicMock(),
        )
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_invalid_date_pipeline_not_called(self, capsys):
        session = _mock_session()
        briefing_fn = MagicMock()
        main(
            ["--date", "not-a-date"],
            _session_factory=_make_factory(session),
            _briefing_fn=briefing_fn,
        )
        briefing_fn.assert_not_called()


# ---------------------------------------------------------------------------
# TestNonTradingDay — AC2: non-trading day → exit 0, "Skipped: non-trading day"
# ---------------------------------------------------------------------------


class TestNonTradingDay:
    def test_non_trading_day_exits_0(self, capsys):
        session = _mock_session()
        with patch(f"{_MODULE}.is_trading_day", return_value=False):
            code = main(
                ["--date", "2026-09-27"],  # Saturday
                _session_factory=_make_factory(session),
                _briefing_fn=MagicMock(),
            )
        assert code == 0

    def test_non_trading_day_prints_skip_message(self, capsys):
        session = _mock_session()
        with patch(f"{_MODULE}.is_trading_day", return_value=False):
            main(
                ["--date", "2026-09-27"],
                _session_factory=_make_factory(session),
                _briefing_fn=MagicMock(),
            )
        captured = capsys.readouterr()
        assert "Skipped" in captured.out
        assert "non-trading day" in captured.out

    def test_non_trading_day_nothing_on_stderr(self, capsys):
        session = _mock_session()
        with patch(f"{_MODULE}.is_trading_day", return_value=False):
            main(
                ["--date", "2026-09-27"],
                _session_factory=_make_factory(session),
                _briefing_fn=MagicMock(),
            )
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_non_trading_day_pipeline_not_called(self):
        session = _mock_session()
        briefing_fn = MagicMock()
        with patch(f"{_MODULE}.is_trading_day", return_value=False):
            main(
                ["--date", "2026-09-27"],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        briefing_fn.assert_not_called()


# ---------------------------------------------------------------------------
# TestHappyPath — AC1: trading day with data → report generated, exit 0
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_success_exits_0(self):
        session = _mock_session()
        briefing_fn = MagicMock(return_value=_success_result(42))
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            code = main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        assert code == 0

    def test_success_prints_report_id(self, capsys):
        session = _mock_session()
        briefing_fn = MagicMock(return_value=_success_result(99))
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        captured = capsys.readouterr()
        assert "id=99" in captured.out

    def test_success_prints_date(self, capsys):
        session = _mock_session()
        briefing_fn = MagicMock(return_value=_success_result())
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        captured = capsys.readouterr()
        assert str(_DATE) in captured.out

    def test_success_nothing_on_stderr(self, capsys):
        session = _mock_session()
        briefing_fn = MagicMock(return_value=_success_result())
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_pipeline_called_with_date_and_session(self):
        session = _mock_session()
        briefing_fn = MagicMock(return_value=_success_result())
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        briefing_fn.assert_called_once_with(_DATE, session)


# ---------------------------------------------------------------------------
# TestSkippedStaleData — pipeline returns skipped=True → exit 0, skip message
# ---------------------------------------------------------------------------


class TestSkippedStaleData:
    def test_pipeline_skip_exits_0(self):
        session = _mock_session()
        reason = "price_data has 5 rows; need at least 50"
        briefing_fn = MagicMock(return_value=_skipped_result(reason))
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            code = main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        assert code == 0

    def test_pipeline_skip_prints_reason(self, capsys):
        session = _mock_session()
        reason = "price_data has 5 rows; need at least 50"
        briefing_fn = MagicMock(return_value=_skipped_result(reason))
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        captured = capsys.readouterr()
        assert "Skipped" in captured.out
        assert reason in captured.out

    def test_pipeline_skip_nothing_on_stderr(self, capsys):
        session = _mock_session()
        briefing_fn = MagicMock(return_value=_skipped_result())
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        captured = capsys.readouterr()
        assert captured.err == ""


# ---------------------------------------------------------------------------
# TestPipelineException — unhandled exception → exit 1, error on stderr
# ---------------------------------------------------------------------------


class TestPipelineException:
    def test_exception_exits_1(self):
        session = _mock_session()
        briefing_fn = MagicMock(side_effect=RuntimeError("DB is down"))
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            code = main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        assert code == 1

    def test_exception_prints_to_stderr(self, capsys):
        session = _mock_session()
        briefing_fn = MagicMock(side_effect=RuntimeError("DB is down"))
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        captured = capsys.readouterr()
        assert "DB is down" in captured.err

    def test_exception_stderr_contains_error_prefix(self, capsys):
        session = _mock_session()
        briefing_fn = MagicMock(side_effect=ValueError("schema mismatch"))
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_exception_nothing_on_stdout(self, capsys):
        session = _mock_session()
        briefing_fn = MagicMock(side_effect=RuntimeError("crash"))
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        captured = capsys.readouterr()
        assert captured.out == ""


# ---------------------------------------------------------------------------
# TestIdempotency — existing report deleted before re-run
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_existing_report_deleted_before_pipeline(self):
        """Running twice for the same date deletes the old report before the pipeline runs."""
        existing = MagicMock()
        session = _mock_session(existing_report_count=1)
        session.execute.return_value.scalars.return_value.all.return_value = [existing]
        briefing_fn = MagicMock(return_value=_success_result())
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        session.delete.assert_called_once_with(existing)
        session.commit.assert_called()

    def test_no_existing_report_does_not_call_delete(self):
        """When no previous report exists, session.delete is never called."""
        session = _mock_session(existing_report_count=0)
        briefing_fn = MagicMock(return_value=_success_result())
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        session.delete.assert_not_called()

    def test_deletion_message_on_stdout(self, capsys):
        """If an existing report is deleted, the CLI mentions it."""
        session = _mock_session(existing_report_count=1)
        session.execute.return_value.scalars.return_value.all.return_value = [MagicMock()]
        briefing_fn = MagicMock(return_value=_success_result())
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        captured = capsys.readouterr()
        assert "deleted" in captured.out.lower() or "regenerating" in captured.out.lower()

    def test_multiple_existing_reports_all_deleted(self):
        """If somehow two rows exist for the same date, both are deleted."""
        old1, old2 = MagicMock(), MagicMock()
        session = _mock_session()
        session.execute.return_value.scalars.return_value.all.return_value = [old1, old2]
        briefing_fn = MagicMock(return_value=_success_result())
        with patch(f"{_MODULE}.is_trading_day", return_value=True):
            main(
                ["--date", str(_DATE)],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        assert session.delete.call_count == 2


# ---------------------------------------------------------------------------
# TestDefaultDate — no --date flag → uses today in IST
# ---------------------------------------------------------------------------


class TestDefaultDate:
    def test_no_date_flag_uses_today_ist(self):
        """Omitting --date → pipeline receives today's date in IST."""
        session = _mock_session()
        today_ist = datetime.date(2026, 9, 28)
        briefing_fn = MagicMock(return_value=_success_result())

        mock_now = MagicMock()
        mock_now.date.return_value = today_ist

        with (
            patch(f"{_MODULE}.is_trading_day", return_value=True),
            patch("app.jobs.run_briefing.datetime") as mock_dt,
        ):
            mock_dt.datetime.now.return_value = mock_now
            mock_dt.date = datetime.date  # keep date.fromisoformat working
            main(
                [],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        briefing_fn.assert_called_once_with(today_ist, session)

    def test_no_date_flag_exits_0_on_success(self):
        session = _mock_session()
        briefing_fn = MagicMock(return_value=_success_result())
        mock_now = MagicMock()
        mock_now.date.return_value = _DATE
        with (
            patch(f"{_MODULE}.is_trading_day", return_value=True),
            patch("app.jobs.run_briefing.datetime") as mock_dt,
        ):
            mock_dt.datetime.now.return_value = mock_now
            mock_dt.date = datetime.date
            code = main(
                [],
                _session_factory=_make_factory(session),
                _briefing_fn=briefing_fn,
            )
        assert code == 0


# ---------------------------------------------------------------------------
# TestDeleteExistingReport helper (unit)
# ---------------------------------------------------------------------------


class TestDeleteExistingReportHelper:
    def test_returns_zero_when_no_rows(self):
        session = _mock_session(existing_report_count=0)
        count = _delete_existing_report(session, _DATE)
        assert count == 0

    def test_returns_count_of_deleted_rows(self):
        session = _mock_session()
        r1, r2 = MagicMock(), MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [r1, r2]
        count = _delete_existing_report(session, _DATE)
        assert count == 2

    def test_deletes_each_row(self):
        session = _mock_session()
        r = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [r]
        _delete_existing_report(session, _DATE)
        session.delete.assert_called_once_with(r)

    def test_commits_deletion(self):
        session = _mock_session()
        r = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [r]
        _delete_existing_report(session, _DATE)
        session.commit.assert_called()

    def test_no_commit_when_no_rows(self):
        session = _mock_session(existing_report_count=0)
        _delete_existing_report(session, _DATE)
        session.commit.assert_not_called()
