"""Tests for T-VYS-05: NSE/BSE announcement fetchers and news aggregator.

Coverage:
  - NSEAnnouncementFetcher: parse, URL strategy, IST→UTC, retry, error handling
  - BSEAnnouncementFetcher: XML parse, date filter, IST→UTC, retry, error handling
  - ingest_announcements: company map, bulk insert, dedup, per-source failure isolation
"""
from __future__ import annotations

import datetime
from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from app.fetchers import NewsAnnouncement
from app.fetchers.news_bse import (
    BSEAnnouncementFetcher,
    _in_date_range,
    _parse_bse_row,
    _parse_bse_timestamp,
)
from app.fetchers.news_nse import (
    NSEAnnouncementFetcher,
    _parse_nse_timestamp,
)
from app.fetchers.news_aggregator import (
    NewsFetchSummary,
    _announcement_to_row,
    _build_company_maps,
    ingest_announcements,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
_UTC = datetime.timezone.utc

D = datetime.date
DT = datetime.datetime


def _make_mock_response(json_data=None, text_data="", status=200):
    """Build a mock httpx response with raise_for_status behaviour."""
    resp = MagicMock()
    resp.text = text_data
    resp.json.return_value = json_data
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status}",
            request=MagicMock(),
            response=MagicMock(status_code=status),
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# _parse_nse_timestamp
# ---------------------------------------------------------------------------


class TestParseNseTimestamp:
    def test_standard_format_ist_to_utc(self):
        # "01-Jan-2026 09:15:30" IST = "01-Jan-2026 03:45:30" UTC
        result = _parse_nse_timestamp("01-Jan-2026 09:15:30")
        assert result is not None
        assert result.tzinfo == _UTC
        expected = DT(2026, 1, 1, 3, 45, 30, tzinfo=_UTC)
        assert result == expected

    def test_alternate_format_yyyy_mm_dd(self):
        # "2026-09-26 18:00:00" IST = "2026-09-26 12:30:00" UTC
        result = _parse_nse_timestamp("2026-09-26 18:00:00")
        assert result is not None
        assert result.tzinfo == _UTC
        expected = DT(2026, 9, 26, 12, 30, 0, tzinfo=_UTC)
        assert result == expected

    def test_empty_string_returns_none(self):
        assert _parse_nse_timestamp("") is None

    def test_garbage_returns_none(self):
        assert _parse_nse_timestamp("not-a-date") is None

    def test_midnight_ist_is_previous_day_utc(self):
        # "26-Sep-2026 00:00:00" IST = "25-Sep-2026 18:30:00" UTC
        result = _parse_nse_timestamp("26-Sep-2026 00:00:00")
        assert result is not None
        assert result.date() == D(2026, 9, 25)
        assert result.hour == 18
        assert result.minute == 30


# ---------------------------------------------------------------------------
# NSEAnnouncementFetcher — parse
# ---------------------------------------------------------------------------


class TestNSEAnnouncementFetcherParse:
    def _fetcher(self, json_data):
        client = MagicMock()
        client.get.return_value = _make_mock_response(json_data=json_data)
        return NSEAnnouncementFetcher(client=client, warm_up_delay=0)

    def test_parses_announcement_with_attachment(self):
        data = [
            {
                "symbol": "RELIANCE",
                "subject": "Board Meeting Notice",
                "attchmntFile": "https://www.nseindia.com/corporate/RELIANCE_01-Jan-2026.pdf",
                "exchdisstime": "01-Jan-2026 09:15:30",
                "seq_id": "12345",
            }
        ]
        fetcher = self._fetcher(data)
        results = fetcher.fetch(D(2026, 1, 1), D(2026, 1, 1))
        assert len(results) == 1
        ann = results[0]
        assert ann.source == "NSE"
        assert ann.ticker_raw == "RELIANCE"
        assert ann.headline == "Board Meeting Notice"
        assert ann.url == "https://www.nseindia.com/corporate/RELIANCE_01-Jan-2026.pdf"
        assert ann.source_name == "NSE"
        assert ann.published_at.tzinfo == _UTC

    def test_parses_announcement_synthetic_url(self):
        data = [
            {
                "symbol": "INFY",
                "subject": "Dividend Declared",
                "attchmntFile": "",
                "exchdisstime": "01-Jan-2026 10:00:00",
                "seq_id": "99999",
            }
        ]
        fetcher = self._fetcher(data)
        results = fetcher.fetch(D(2026, 1, 1), D(2026, 1, 1))
        assert len(results) == 1
        assert results[0].url == "nse://announcements/INFY/99999"

    def test_skips_item_without_subject(self):
        data = [
            {
                "symbol": "TCS",
                "subject": "",
                "attchmntFile": "",
                "exchdisstime": "01-Jan-2026 10:00:00",
                "seq_id": "111",
            }
        ]
        fetcher = self._fetcher(data)
        assert fetcher.fetch(D(2026, 1, 1), D(2026, 1, 1)) == []

    def test_skips_item_no_url_possible(self):
        # no attachment, no seq_id, no symbol → no synthetic URL possible
        data = [
            {
                "symbol": "",
                "subject": "Something happened",
                "attchmntFile": "",
                "exchdisstime": "01-Jan-2026 10:00:00",
                "seq_id": "",
            }
        ]
        fetcher = self._fetcher(data)
        assert fetcher.fetch(D(2026, 1, 1), D(2026, 1, 1)) == []

    def test_unwraps_data_key_response(self):
        data = {
            "data": [
                {
                    "symbol": "HDFCBANK",
                    "subject": "Q3 Results",
                    "attchmntFile": "",
                    "exchdisstime": "01-Jan-2026 11:00:00",
                    "seq_id": "777",
                }
            ]
        }
        client = MagicMock()
        client.get.return_value = _make_mock_response(json_data=data)
        fetcher = NSEAnnouncementFetcher(client=client, warm_up_delay=0)
        results = fetcher.fetch(D(2026, 1, 1), D(2026, 1, 1))
        assert len(results) == 1
        assert results[0].ticker_raw == "HDFCBANK"

    def test_unexpected_response_shape_returns_empty(self):
        client = MagicMock()
        client.get.return_value = _make_mock_response(json_data={"unknown_key": 42})
        fetcher = NSEAnnouncementFetcher(client=client, warm_up_delay=0)
        results = fetcher.fetch(D(2026, 1, 1), D(2026, 1, 1))
        assert results == []

    def test_symbol_uppercased(self):
        data = [
            {
                "symbol": "reliance",
                "subject": "Notice",
                "attchmntFile": "",
                "exchdisstime": "01-Jan-2026 09:00:00",
                "seq_id": "1",
            }
        ]
        fetcher = self._fetcher(data)
        results = fetcher.fetch(D(2026, 1, 1), D(2026, 1, 1))
        assert results[0].ticker_raw == "RELIANCE"


# ---------------------------------------------------------------------------
# NSEAnnouncementFetcher — retry and error handling
# ---------------------------------------------------------------------------


class TestNSEAnnouncementFetcherRetry:
    @patch("app.fetchers.news_nse.time.sleep", return_value=None)
    def test_returns_empty_on_http_error(self, mock_sleep):
        client = MagicMock()
        client.get.return_value = _make_mock_response(status=500)
        fetcher = NSEAnnouncementFetcher(client=client, warm_up_delay=0)
        result = fetcher.fetch(D(2026, 1, 1), D(2026, 1, 1))
        assert result == []

    @patch("app.fetchers.news_nse.time.sleep", return_value=None)
    def test_retries_on_429_then_succeeds(self, mock_sleep):
        data = [
            {
                "symbol": "WIPRO",
                "subject": "AGM Notice",
                "attchmntFile": "",
                "exchdisstime": "01-Jan-2026 09:00:00",
                "seq_id": "55",
            }
        ]
        err_resp = _make_mock_response(status=429)
        ok_resp = _make_mock_response(json_data=data)
        client = MagicMock()
        client.get.side_effect = [err_resp, ok_resp]

        # Make the first call raise HTTPStatusError, second succeed
        def side_effect(url, **kwargs):
            return client.get.side_effect.pop(0)

        client.get.side_effect = None
        client.get.return_value = ok_resp

        # Build a proper "first fail, then succeed" sequence
        responses = [err_resp, ok_resp]
        client.get.side_effect = responses

        fetcher = NSEAnnouncementFetcher(client=client, warm_up_delay=0)
        result = fetcher.fetch(D(2026, 1, 1), D(2026, 1, 1))
        assert len(result) == 1

    @patch("app.fetchers.news_nse.time.sleep", return_value=None)
    def test_retries_exhausted_returns_empty(self, mock_sleep):
        client = MagicMock()
        client.get.return_value = _make_mock_response(status=503)
        fetcher = NSEAnnouncementFetcher(client=client, warm_up_delay=0)
        result = fetcher.fetch(D(2026, 1, 1), D(2026, 1, 1))
        assert result == []
        # 3 attempts total (initial + 2 retries)
        assert client.get.call_count == 3


# ---------------------------------------------------------------------------
# _parse_bse_timestamp
# ---------------------------------------------------------------------------


class TestParseBseTimestamp:
    def test_standard_format_ist_to_utc(self):
        # "20260926181500" IST = "20260926130000" UTC (offset 5h30m)
        result = _parse_bse_timestamp("20260926181500")
        assert result is not None
        assert result.tzinfo == _UTC
        expected = DT(2026, 9, 26, 12, 45, 0, tzinfo=_UTC)
        assert result == expected

    def test_empty_string_returns_none(self):
        assert _parse_bse_timestamp("") is None

    def test_short_string_returns_none(self):
        assert _parse_bse_timestamp("202609") is None

    def test_garbage_returns_none(self):
        assert _parse_bse_timestamp("ABCDEFGHIJKLMN") is None

    def test_midnight_ist_crosses_day_boundary(self):
        # "20260926000000" IST = "20260925183000" UTC
        result = _parse_bse_timestamp("20260926000000")
        assert result is not None
        assert result.date() == D(2026, 9, 25)


# ---------------------------------------------------------------------------
# _parse_bse_row
# ---------------------------------------------------------------------------


class TestParseBseRow:
    def _make_elem(self, fields: dict):
        import xml.etree.ElementTree as ET

        row = ET.Element("Table")
        for tag, val in fields.items():
            child = ET.SubElement(row, tag)
            child.text = val
        return row

    def test_parses_with_attachment(self):
        elem = self._make_elem(
            {
                "COMPANY_CODE": "500325",
                "NEWSSUB": "Board Meeting",
                "DT_TM": "20260926091500",
                "ATTACHMENTNAME": "500325_Board_20260926.pdf",
            }
        )
        ann = _parse_bse_row(elem)
        assert ann is not None
        assert ann.source == "BSE"
        assert ann.scrip_code == "500325"
        assert ann.headline == "Board Meeting"
        assert ann.url == "https://www.bseindia.com/xml-data/corpfiling/AttachLive/500325_Board_20260926.pdf"
        assert ann.source_name == "BSE"
        assert ann.ticker_raw is None

    def test_parses_synthetic_url_when_no_attachment(self):
        elem = self._make_elem(
            {
                "COMPANY_CODE": "500325",
                "NEWSSUB": "Dividend",
                "DT_TM": "20260926091500",
                "ATTACHMENTNAME": "",
            }
        )
        ann = _parse_bse_row(elem)
        assert ann is not None
        assert ann.url == "bse://announcements/500325/20260926091500"

    def test_synthetic_url_is_deterministic(self):
        import xml.etree.ElementTree as ET

        fields = {
            "COMPANY_CODE": "532540",
            "NEWSSUB": "Merger Update",
            "DT_TM": "20260101120000",
            "ATTACHMENTNAME": "",
        }
        elem1 = self._make_elem(fields)
        elem2 = self._make_elem(fields)
        ann1 = _parse_bse_row(elem1)
        ann2 = _parse_bse_row(elem2)
        assert ann1 is not None and ann2 is not None
        assert ann1.url == ann2.url

    def test_missing_scrip_code_returns_none(self):
        elem = self._make_elem(
            {
                "NEWSSUB": "Something",
                "DT_TM": "20260926091500",
            }
        )
        assert _parse_bse_row(elem) is None

    def test_missing_headline_returns_none(self):
        elem = self._make_elem(
            {
                "COMPANY_CODE": "500325",
                "DT_TM": "20260926091500",
            }
        )
        assert _parse_bse_row(elem) is None

    def test_invalid_timestamp_returns_none(self):
        elem = self._make_elem(
            {
                "COMPANY_CODE": "500325",
                "NEWSSUB": "Notice",
                "DT_TM": "bad",
            }
        )
        assert _parse_bse_row(elem) is None


# ---------------------------------------------------------------------------
# BSEAnnouncementFetcher
# ---------------------------------------------------------------------------

_SAMPLE_BSE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<NewDataSet>
  <Table>
    <COMPANY_CODE>500325</COMPANY_CODE>
    <NEWSSUB>Board Meeting Notice</NEWSSUB>
    <DT_TM>20260926091500</DT_TM>
    <ATTACHMENTNAME>500325_BM_20260926.pdf</ATTACHMENTNAME>
  </Table>
  <Table>
    <COMPANY_CODE>532540</COMPANY_CODE>
    <NEWSSUB>Dividend Announcement</NEWSSUB>
    <DT_TM>20260925180000</DT_TM>
    <ATTACHMENTNAME></ATTACHMENTNAME>
  </Table>
</NewDataSet>
"""


class TestBSEAnnouncementFetcher:
    def _fetcher(self, xml_text=_SAMPLE_BSE_XML, status=200):
        client = MagicMock()
        client.get.return_value = _make_mock_response(text_data=xml_text, status=status)
        return BSEAnnouncementFetcher(client=client)

    def test_parses_all_valid_items(self):
        fetcher = self._fetcher()
        # date range covers both items
        results = fetcher.fetch(D(2026, 9, 25), D(2026, 9, 26))
        assert len(results) == 2

    def test_date_filtering_excludes_out_of_range(self):
        fetcher = self._fetcher()
        # only include Sep 26 → excludes the Sep 25 item
        results = fetcher.fetch(D(2026, 9, 26), D(2026, 9, 26))
        assert len(results) == 1
        assert results[0].scrip_code == "500325"

    def test_returns_empty_on_http_error(self):
        fetcher = self._fetcher(status=503)
        with patch("app.fetchers.news_bse.time.sleep", return_value=None):
            result = fetcher.fetch(D(2026, 9, 26), D(2026, 9, 26))
        assert result == []

    @patch("app.fetchers.news_bse.time.sleep", return_value=None)
    def test_retries_exhausted_makes_three_attempts(self, mock_sleep):
        client = MagicMock()
        client.get.return_value = _make_mock_response(status=429)
        fetcher = BSEAnnouncementFetcher(client=client)
        result = fetcher.fetch(D(2026, 9, 26), D(2026, 9, 26))
        assert result == []
        assert client.get.call_count == 3

    def test_returns_empty_on_malformed_xml(self):
        fetcher = self._fetcher(xml_text="this is not xml")
        result = fetcher.fetch(D(2026, 9, 26), D(2026, 9, 26))
        assert result == []

    def test_attachment_url_constructed_correctly(self):
        fetcher = self._fetcher()
        results = fetcher.fetch(D(2026, 9, 26), D(2026, 9, 26))
        assert results[0].url == "https://www.bseindia.com/xml-data/corpfiling/AttachLive/500325_BM_20260926.pdf"

    def test_published_at_is_utc(self):
        fetcher = self._fetcher()
        results = fetcher.fetch(D(2026, 9, 25), D(2026, 9, 26))
        for ann in results:
            assert ann.published_at.tzinfo == _UTC


# ---------------------------------------------------------------------------
# _in_date_range
# ---------------------------------------------------------------------------


class TestInDateRange:
    def test_within_range(self):
        dt = DT(2026, 9, 26, 10, 0, 0, tzinfo=_UTC)
        assert _in_date_range(dt, D(2026, 9, 25), D(2026, 9, 27)) is True

    def test_on_lower_bound(self):
        dt = DT(2026, 9, 25, 0, 0, 1, tzinfo=_UTC)
        assert _in_date_range(dt, D(2026, 9, 25), D(2026, 9, 27)) is True

    def test_on_upper_bound(self):
        dt = DT(2026, 9, 27, 23, 59, 59, tzinfo=_UTC)
        assert _in_date_range(dt, D(2026, 9, 25), D(2026, 9, 27)) is True

    def test_before_range(self):
        dt = DT(2026, 9, 24, 23, 59, 59, tzinfo=_UTC)
        assert _in_date_range(dt, D(2026, 9, 25), D(2026, 9, 27)) is False

    def test_after_range(self):
        dt = DT(2026, 9, 28, 0, 0, 0, tzinfo=_UTC)
        assert _in_date_range(dt, D(2026, 9, 25), D(2026, 9, 27)) is False


# ---------------------------------------------------------------------------
# _announcement_to_row
# ---------------------------------------------------------------------------


def _make_ann(
    source="NSE",
    ticker_raw="RELIANCE",
    scrip_code=None,
    url="https://example.com/ann.pdf",
    headline="Notice",
) -> NewsAnnouncement:
    return NewsAnnouncement(
        source=source,
        ticker_raw=ticker_raw,
        scrip_code=scrip_code,
        headline=headline,
        url=url,
        published_at=DT(2026, 9, 26, 9, 0, 0, tzinfo=_UTC),
        source_name=source,
    )


class TestAnnouncementToRow:
    _NSE_MAP = {"RELIANCE": 1, "INFY": 2}
    _BSE_MAP = {"500325": 1, "500209": 2}
    _NOW = DT(2026, 9, 26, 10, 0, 0, tzinfo=_UTC)

    def test_nse_known_ticker(self):
        ann = _make_ann(source="NSE", ticker_raw="RELIANCE")
        row = _announcement_to_row(ann, self._NSE_MAP, self._BSE_MAP, self._NOW)
        assert row is not None
        assert row["company_id"] == 1
        assert row["ticker"] == "RELIANCE"
        assert row["exchange"] == "NSE"

    def test_nse_unknown_ticker_company_id_none(self):
        ann = _make_ann(source="NSE", ticker_raw="UNKNOWN_CO")
        row = _announcement_to_row(ann, self._NSE_MAP, self._BSE_MAP, self._NOW)
        assert row is not None
        assert row["company_id"] is None
        assert row["ticker"] == "UNKNOWN_CO"

    def test_bse_known_scrip_code(self):
        ann = _make_ann(source="BSE", ticker_raw=None, scrip_code="500325")
        row = _announcement_to_row(ann, self._NSE_MAP, self._BSE_MAP, self._NOW)
        assert row is not None
        assert row["company_id"] == 1
        assert row["exchange"] == "BSE"

    def test_bse_unknown_scrip_code_company_id_none(self):
        ann = _make_ann(source="BSE", ticker_raw=None, scrip_code="999999")
        row = _announcement_to_row(ann, self._NSE_MAP, self._BSE_MAP, self._NOW)
        assert row is not None
        assert row["company_id"] is None

    def test_empty_url_returns_none(self):
        ann = _make_ann(url="")
        row = _announcement_to_row(ann, self._NSE_MAP, self._BSE_MAP, self._NOW)
        assert row is None

    def test_row_fields_populated(self):
        ann = _make_ann(source="NSE", ticker_raw="INFY")
        row = _announcement_to_row(ann, self._NSE_MAP, self._BSE_MAP, self._NOW)
        assert row is not None
        assert row["headline"] == "Notice"
        assert row["source_type"] == "exchange_announcement"
        assert row["source_name"] == "NSE"
        assert row["fetched_at"] == self._NOW
        assert row["published_at"] == ann.published_at


# ---------------------------------------------------------------------------
# ingest_announcements — integration (DB mocked)
# ---------------------------------------------------------------------------


class TestIngestAnnouncements:
    """Tests for the full ingest_announcements orchestration.

    The SQLAlchemy session and DB operations are fully mocked so no real DB
    is needed. We verify: company map queries, fetcher calls, bulk insert,
    and summary counts.
    """

    def _make_session(self, companies=None):
        """Mock session that returns the given companies list from execute()."""
        if companies is None:
            companies = [
                (1, "RELIANCE", "500325"),
                (2, "INFY", "500209"),
            ]
        session = MagicMock()
        exec_result = MagicMock()
        exec_result.fetchall.return_value = companies
        # First execute call is the company map query
        insert_result = MagicMock()
        insert_result.rowcount = None  # overridden per test
        session.execute.side_effect = [exec_result, insert_result]
        return session, insert_result

    def _make_nse_fetcher(self, items=None):
        fetcher = MagicMock(spec=NSEAnnouncementFetcher)
        fetcher.fetch.return_value = items or []
        return fetcher

    def _make_bse_fetcher(self, items=None):
        fetcher = MagicMock(spec=BSEAnnouncementFetcher)
        fetcher.fetch.return_value = items or []
        return fetcher

    def _nse_ann(self, ticker="RELIANCE", seq="1"):
        return NewsAnnouncement(
            source="NSE",
            ticker_raw=ticker,
            scrip_code=None,
            headline=f"{ticker} Board Meeting",
            url=f"nse://announcements/{ticker}/{seq}",
            published_at=DT(2026, 9, 26, 9, 0, 0, tzinfo=_UTC),
            source_name="NSE",
        )

    def _bse_ann(self, scrip_code="500325", seq="20260926091500"):
        return NewsAnnouncement(
            source="BSE",
            ticker_raw=None,
            scrip_code=scrip_code,
            headline="BSE Announcement",
            url=f"bse://announcements/{scrip_code}/{seq}",
            published_at=DT(2026, 9, 26, 9, 0, 0, tzinfo=_UTC),
            source_name="BSE",
        )

    def test_summary_counts_both_sources(self):
        session, insert_result = self._make_session()
        insert_result.rowcount = 2
        nse = self._make_nse_fetcher([self._nse_ann()])
        bse = self._make_bse_fetcher([self._bse_ann()])

        summary = ingest_announcements(
            session, D(2026, 9, 26), D(2026, 9, 26),
            nse_fetcher=nse, bse_fetcher=bse,
        )

        assert summary.nse_fetched == 1
        assert summary.bse_fetched == 1
        assert summary.rows_inserted == 2
        assert summary.nse_error is False
        assert summary.bse_error is False

    def test_both_fetchers_called_with_date_range(self):
        session, _ = self._make_session()
        nse = self._make_nse_fetcher()
        bse = self._make_bse_fetcher()

        ingest_announcements(
            session, D(2026, 9, 25), D(2026, 9, 26),
            nse_fetcher=nse, bse_fetcher=bse,
        )

        nse.fetch.assert_called_once_with(D(2026, 9, 25), D(2026, 9, 26))
        bse.fetch.assert_called_once_with(D(2026, 9, 25), D(2026, 9, 26))

    def test_nse_error_bse_still_inserts(self):
        session, insert_result = self._make_session()
        insert_result.rowcount = 1

        nse = MagicMock(spec=NSEAnnouncementFetcher)
        nse.fetch.side_effect = RuntimeError("NSE network down")
        bse = self._make_bse_fetcher([self._bse_ann()])

        summary = ingest_announcements(
            session, D(2026, 9, 26), D(2026, 9, 26),
            nse_fetcher=nse, bse_fetcher=bse,
        )

        assert summary.nse_error is True
        assert summary.bse_error is False
        assert summary.nse_fetched == 0
        assert summary.bse_fetched == 1

    def test_bse_error_nse_still_inserts(self):
        session, insert_result = self._make_session()
        insert_result.rowcount = 1

        nse = self._make_nse_fetcher([self._nse_ann()])
        bse = MagicMock(spec=BSEAnnouncementFetcher)
        bse.fetch.side_effect = ConnectionError("BSE unreachable")

        summary = ingest_announcements(
            session, D(2026, 9, 26), D(2026, 9, 26),
            nse_fetcher=nse, bse_fetcher=bse,
        )

        assert summary.bse_error is True
        assert summary.nse_error is False
        assert summary.nse_fetched == 1

    def test_both_empty_returns_zero_inserted(self):
        session, _ = self._make_session()
        nse = self._make_nse_fetcher()
        bse = self._make_bse_fetcher()

        summary = ingest_announcements(
            session, D(2026, 9, 26), D(2026, 9, 26),
            nse_fetcher=nse, bse_fetcher=bse,
        )

        assert summary.rows_inserted == 0
        assert summary.nse_fetched == 0
        assert summary.bse_fetched == 0

    def test_unknown_ticker_stored_with_company_id_none(self):
        """Announcements for unlisted tickers are stored; company_id=None."""
        session, insert_result = self._make_session(companies=[])  # empty company map
        insert_result.rowcount = 1
        nse = self._make_nse_fetcher([self._nse_ann(ticker="UNKNOWN_CORP")])
        bse = self._make_bse_fetcher()

        summary = ingest_announcements(
            session, D(2026, 9, 26), D(2026, 9, 26),
            nse_fetcher=nse, bse_fetcher=bse,
        )

        # Row was still inserted (company_id=None is valid)
        assert summary.nse_fetched == 1
        # The bulk insert was called with rowcount-based result
        session.execute.assert_called()

    def test_dedup_rowcount_reported_accurately(self):
        """Rows already in DB are skipped; rowcount reflects actual inserts."""
        session, insert_result = self._make_session()
        insert_result.rowcount = 0  # all dupes → nothing inserted

        nse = self._make_nse_fetcher([self._nse_ann(), self._nse_ann(seq="2")])
        bse = self._make_bse_fetcher()

        summary = ingest_announcements(
            session, D(2026, 9, 26), D(2026, 9, 26),
            nse_fetcher=nse, bse_fetcher=bse,
        )

        assert summary.rows_inserted == 0
        assert summary.nse_fetched == 2
