"""Tests for T-BHM-01: APScheduler setup and daily briefing job lifecycle.

Coverage:
  - create_scheduler() returns AsyncIOScheduler with correct cron + config
  - run_daily_briefing_job: non-trading-day skip, success, retry-then-success,
    retry-exhausted failure, triggered_by, date resolution
  - job_executions row fields on every outcome
"""
from __future__ import annotations

import datetime
import zoneinfo
from unittest.mock import MagicMock, call, patch

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.db.models.research import JobExecution
from app.scheduler import (
    CRON_HOUR,
    CRON_MINUTE,
    CRON_TZ,
    JOB_NAME,
    MAX_RETRIES,
    RETRY_DELAY_SECONDS,
    _MISFIRE_GRACE_TIME,
    create_scheduler,
    run_daily_briefing_job,
)

_IST = zoneinfo.ZoneInfo("Asia/Kolkata")
_UTC = datetime.timezone.utc

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> MagicMock:
    """Return a mock SQLAlchemy sync Session that works as a context manager."""
    session = MagicMock(spec=Session)
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


def _make_factory(session: MagicMock | None = None) -> MagicMock:
    """Return a mock session factory (callable that returns the session)."""
    if session is None:
        session = _make_session()
    factory = MagicMock(return_value=session)
    return factory


def _trading_day() -> datetime.date:
    """A known NSE trading day (Monday 2026-09-28 — not a holiday)."""
    return datetime.date(2026, 9, 28)


def _holiday() -> datetime.date:
    """A known non-trading day (Saturday 2026-09-26)."""
    return datetime.date(2026, 9, 26)


# ---------------------------------------------------------------------------
# create_scheduler — structure tests
# ---------------------------------------------------------------------------


class TestCreateScheduler:
    def test_returns_async_io_scheduler(self):
        scheduler = create_scheduler()
        assert isinstance(scheduler, AsyncIOScheduler)

    def test_registers_daily_briefing_job(self):
        scheduler = create_scheduler()
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == JOB_NAME

    def test_cron_trigger_hour_and_minute(self):
        scheduler = create_scheduler()
        job = scheduler.get_jobs()[0]
        trigger = job.trigger
        assert isinstance(trigger, CronTrigger)
        fields = {f.name: str(f) for f in trigger.fields}
        assert fields["hour"] == str(CRON_HOUR)
        assert fields["minute"] == str(CRON_MINUTE)

    def test_cron_trigger_timezone_is_ist(self):
        scheduler = create_scheduler()
        job = scheduler.get_jobs()[0]
        trigger = job.trigger
        assert isinstance(trigger, CronTrigger)
        assert str(trigger.timezone) == CRON_TZ

    def test_coalesce_is_true(self):
        scheduler = create_scheduler()
        job = scheduler.get_jobs()[0]
        assert job.coalesce is True

    def test_misfire_grace_time_is_one_hour(self):
        scheduler = create_scheduler()
        job = scheduler.get_jobs()[0]
        assert job.misfire_grace_time == _MISFIRE_GRACE_TIME

    def test_scheduler_not_running_after_creation(self):
        scheduler = create_scheduler()
        assert not scheduler.running


# ---------------------------------------------------------------------------
# run_daily_briefing_job — skip on non-trading day
# ---------------------------------------------------------------------------


class TestJobSkipNonTradingDay:
    @patch("app.scheduler.is_trading_day", return_value=False)
    def test_skip_writes_skipped_row(self, mock_cal):
        session = _make_session()
        factory = _make_factory(session)

        run_daily_briefing_job(
            date=_holiday(),
            _session_factory=factory,
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        # session.add was called once (the exec_row)
        session.add.assert_called_once()
        exec_row: JobExecution = session.add.call_args[0][0]

        # status was updated to 'skipped'
        assert exec_row.status == "skipped"
        assert exec_row.skip_reason == "holiday"

    @patch("app.scheduler.is_trading_day", return_value=False)
    def test_skip_does_not_call_pipeline(self, mock_cal):
        session = _make_session()
        pipeline = MagicMock()

        run_daily_briefing_job(
            date=_holiday(),
            _session_factory=_make_factory(session),
            _pipeline=pipeline,
            _retry_delay_seconds=0,
        )

        pipeline.assert_not_called()

    @patch("app.scheduler.is_trading_day", return_value=False)
    def test_skip_commits_session(self, mock_cal):
        session = _make_session()

        run_daily_briefing_job(
            date=_holiday(),
            _session_factory=_make_factory(session),
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        session.commit.assert_called()

    @patch("app.scheduler.is_trading_day", return_value=False)
    def test_skip_sets_job_name(self, mock_cal):
        session = _make_session()

        run_daily_briefing_job(
            date=_holiday(),
            _session_factory=_make_factory(session),
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        exec_row: JobExecution = session.add.call_args[0][0]
        assert exec_row.job_name == JOB_NAME

    @patch("app.scheduler.is_trading_day", return_value=False)
    def test_skip_uses_provided_date(self, mock_cal):
        session = _make_session()
        target_date = _holiday()

        run_daily_briefing_job(
            date=target_date,
            _session_factory=_make_factory(session),
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        mock_cal.assert_called_once_with(target_date, "NSE")


# ---------------------------------------------------------------------------
# run_daily_briefing_job — successful pipeline run
# ---------------------------------------------------------------------------


class TestJobSuccessfulRun:
    @patch("app.scheduler.is_trading_day", return_value=True)
    def test_pipeline_called_with_date_and_session(self, mock_cal):
        session = _make_session()
        pipeline = MagicMock()
        target_date = _trading_day()

        run_daily_briefing_job(
            date=target_date,
            _session_factory=_make_factory(session),
            _pipeline=pipeline,
            _retry_delay_seconds=0,
        )

        pipeline.assert_called_once_with(session, target_date)

    @patch("app.scheduler.is_trading_day", return_value=True)
    def test_completed_status_on_success(self, mock_cal):
        session = _make_session()
        pipeline = MagicMock()

        run_daily_briefing_job(
            date=_trading_day(),
            _session_factory=_make_factory(session),
            _pipeline=pipeline,
            _retry_delay_seconds=0,
        )

        exec_row: JobExecution = session.add.call_args[0][0]
        assert exec_row.status == "completed"

    @patch("app.scheduler.is_trading_day", return_value=True)
    def test_retry_count_zero_on_first_attempt_success(self, mock_cal):
        session = _make_session()

        run_daily_briefing_job(
            date=_trading_day(),
            _session_factory=_make_factory(session),
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        exec_row: JobExecution = session.add.call_args[0][0]
        assert exec_row.retry_count == 0

    @patch("app.scheduler.is_trading_day", return_value=True)
    def test_completed_at_is_set(self, mock_cal):
        session = _make_session()

        run_daily_briefing_job(
            date=_trading_day(),
            _session_factory=_make_factory(session),
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        exec_row: JobExecution = session.add.call_args[0][0]
        assert exec_row.completed_at is not None

    @patch("app.scheduler.is_trading_day", return_value=True)
    def test_session_committed_on_success(self, mock_cal):
        session = _make_session()

        run_daily_briefing_job(
            date=_trading_day(),
            _session_factory=_make_factory(session),
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        session.commit.assert_called()


# ---------------------------------------------------------------------------
# run_daily_briefing_job — retry logic
# ---------------------------------------------------------------------------


class TestJobRetry:
    @patch("app.scheduler.is_trading_day", return_value=True)
    def test_retries_on_transient_failure_then_succeeds(self, mock_cal):
        session = _make_session()
        pipeline = MagicMock(side_effect=[RuntimeError("timeout"), None])

        run_daily_briefing_job(
            date=_trading_day(),
            _session_factory=_make_factory(session),
            _pipeline=pipeline,
            _retry_delay_seconds=0,
        )

        assert pipeline.call_count == 2
        exec_row: JobExecution = session.add.call_args[0][0]
        assert exec_row.status == "completed"
        assert exec_row.retry_count == 1

    @patch("app.scheduler.is_trading_day", return_value=True)
    def test_retries_twice_before_failing(self, mock_cal):
        session = _make_session()
        pipeline = MagicMock(side_effect=ConnectionError("db timeout"))

        run_daily_briefing_job(
            date=_trading_day(),
            _session_factory=_make_factory(session),
            _pipeline=pipeline,
            _retry_delay_seconds=0,
        )

        # 1 original attempt + MAX_RETRIES retries
        assert pipeline.call_count == MAX_RETRIES + 1

    @patch("app.scheduler.is_trading_day", return_value=True)
    def test_status_failed_after_exhausted_retries(self, mock_cal):
        session = _make_session()
        pipeline = MagicMock(side_effect=RuntimeError("network error"))

        run_daily_briefing_job(
            date=_trading_day(),
            _session_factory=_make_factory(session),
            _pipeline=pipeline,
            _retry_delay_seconds=0,
        )

        exec_row: JobExecution = session.add.call_args[0][0]
        assert exec_row.status == "failed"

    @patch("app.scheduler.is_trading_day", return_value=True)
    def test_error_message_stored_on_failure(self, mock_cal):
        session = _make_session()
        pipeline = MagicMock(side_effect=ValueError("bad data"))

        run_daily_briefing_job(
            date=_trading_day(),
            _session_factory=_make_factory(session),
            _pipeline=pipeline,
            _retry_delay_seconds=0,
        )

        exec_row: JobExecution = session.add.call_args[0][0]
        assert exec_row.error_message is not None
        assert "bad data" in exec_row.error_message

    @patch("app.scheduler.is_trading_day", return_value=True)
    def test_retry_count_equals_max_on_failure(self, mock_cal):
        session = _make_session()
        pipeline = MagicMock(side_effect=OSError("io error"))

        run_daily_briefing_job(
            date=_trading_day(),
            _session_factory=_make_factory(session),
            _pipeline=pipeline,
            _retry_delay_seconds=0,
        )

        exec_row: JobExecution = session.add.call_args[0][0]
        assert exec_row.retry_count == MAX_RETRIES

    @patch("app.scheduler.time.sleep")
    @patch("app.scheduler.is_trading_day", return_value=True)
    def test_sleep_called_between_retries(self, mock_cal, mock_sleep):
        session = _make_session()
        pipeline = MagicMock(side_effect=RuntimeError("fail"))
        delay = 42

        run_daily_briefing_job(
            date=_trading_day(),
            _session_factory=_make_factory(session),
            _pipeline=pipeline,
            _retry_delay_seconds=delay,
        )

        # sleep is called MAX_RETRIES times (between attempts, not after last)
        assert mock_sleep.call_count == MAX_RETRIES
        mock_sleep.assert_called_with(delay)

    @patch("app.scheduler.time.sleep")
    @patch("app.scheduler.is_trading_day", return_value=True)
    def test_no_sleep_after_final_failed_attempt(self, mock_cal, mock_sleep):
        session = _make_session()
        pipeline = MagicMock(side_effect=RuntimeError("fail"))

        run_daily_briefing_job(
            date=_trading_day(),
            _session_factory=_make_factory(session),
            _pipeline=pipeline,
            _retry_delay_seconds=10,
        )

        # Called MAX_RETRIES times (not MAX_RETRIES + 1)
        assert mock_sleep.call_count == MAX_RETRIES


# ---------------------------------------------------------------------------
# run_daily_briefing_job — triggered_by and date handling
# ---------------------------------------------------------------------------


class TestJobMetadata:
    @patch("app.scheduler.is_trading_day", return_value=False)
    def test_triggered_by_scheduler_when_date_none(self, mock_cal):
        session = _make_session()

        with patch("app.scheduler.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = datetime.datetime(
                2026, 9, 28, 15, 30, 0, tzinfo=_UTC
            )
            mock_dt.date = datetime.date
            mock_dt.timedelta = datetime.timedelta
            mock_dt.timezone = datetime.timezone

            # Patch _IST resolution for date=None path
            with patch("app.scheduler.datetime.datetime") as mock_dt2:
                mock_dt2.now.return_value = datetime.datetime(
                    2026, 9, 28, 21, 0, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata")
                )
                # Simple path: just run with date=None (uses real datetime)
                pass

        run_daily_briefing_job(
            date=None,  # scheduler path
            _session_factory=_make_factory(session),
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        exec_row: JobExecution = session.add.call_args[0][0]
        assert exec_row.triggered_by == "scheduler"

    @patch("app.scheduler.is_trading_day", return_value=False)
    def test_triggered_by_manual_when_date_provided(self, mock_cal):
        session = _make_session()

        run_daily_briefing_job(
            date=_trading_day(),
            _session_factory=_make_factory(session),
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        exec_row: JobExecution = session.add.call_args[0][0]
        assert exec_row.triggered_by == "manual"

    @patch("app.scheduler.is_trading_day", return_value=False)
    def test_provided_date_passed_to_calendar(self, mock_cal):
        session = _make_session()
        target = datetime.date(2026, 9, 25)

        run_daily_briefing_job(
            date=target,
            _session_factory=_make_factory(session),
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        mock_cal.assert_called_once_with(target, "NSE")

    @patch("app.scheduler.is_trading_day", return_value=False)
    def test_date_none_uses_today_in_ist(self, mock_cal):
        """When date=None, job_date should be today's date in IST."""
        session = _make_session()
        today_ist = datetime.datetime.now(tz=_IST).date()

        run_daily_briefing_job(
            date=None,
            _session_factory=_make_factory(session),
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        mock_cal.assert_called_once_with(today_ist, "NSE")

    @patch("app.scheduler.is_trading_day", return_value=False)
    def test_initial_status_is_running(self, mock_cal):
        """The exec_row starts with status='running'; add is called before calendar check."""
        session = _make_session()
        add_calls = []

        def capture_add(row):
            add_calls.append((row.status, row.job_name))

        session.add.side_effect = capture_add

        run_daily_briefing_job(
            date=_holiday(),
            _session_factory=_make_factory(session),
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        # The first call to add should have status='running'
        assert len(add_calls) == 1
        assert add_calls[0][0] == "running"
        assert add_calls[0][1] == JOB_NAME

    @patch("app.scheduler.is_trading_day", return_value=False)
    def test_flush_called_to_get_db_id(self, mock_cal):
        session = _make_session()

        run_daily_briefing_job(
            date=_holiday(),
            _session_factory=_make_factory(session),
            _pipeline=MagicMock(),
            _retry_delay_seconds=0,
        )

        session.flush.assert_called_once()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_max_retries_is_two(self):
        assert MAX_RETRIES == 2

    def test_retry_delay_is_five_minutes(self):
        assert RETRY_DELAY_SECONDS == 300

    def test_cron_tz_is_kolkata(self):
        assert CRON_TZ == "Asia/Kolkata"

    def test_cron_hour_is_21(self):
        assert CRON_HOUR == 21

    def test_cron_minute_is_zero(self):
        assert CRON_MINUTE == 0

    def test_misfire_grace_is_one_hour(self):
        assert _MISFIRE_GRACE_TIME == 3600
