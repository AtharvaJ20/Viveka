"""BSE corporate announcement fetcher (T-VYS-05).

Fetches ALL announcements from BSE's public XML feed in a single call. The
feed is public and requires no authentication (Sanjaya advisory 2026-09-26).

BSE XML Endpoint:
    GET https://www.bseindia.com/xml-data/corpfiling/AttachLive/BSEAN.xml

Response format:
    XML with repeated <Table> (or <row>) elements, one per announcement.
    Key fields:
        COMPANY_CODE   — BSE scrip code (6 digits), used for company lookup
        COMPANY_NAME   — display name only, not used for lookup
        NEWSSUB        — announcement subject/headline
        ATTACHMENTNAME — filename of attachment (may be empty)
        DT_TM          — timestamp in IST, format YYYYMMDDHHMMSS

URL strategy (Sanjaya advisory 2026-09-26):
    Real URL  (ATTACHMENTNAME non-empty):
        https://www.bseindia.com/xml-data/corpfiling/AttachLive/{ATTACHMENTNAME}
    Synthetic URL (no attachment):
        bse://announcements/{scrip_code}/{dt_tm_iso}
    The synthetic URL is deterministic across re-fetches — the same announcement
    always produces the same URL — satisfying the UNIQUE(url) dedup constraint.

Timestamps:
    DT_TM is IST (UTC+5:30). All published_at values are converted to UTC.

Date filtering:
    The BSE feed returns all recent announcements (not bounded to a single day).
    Items outside [date_from, date_to] (compared at UTC day boundary) are
    dropped after parsing.

Failure handling:
    Non-fatal. Any HTTP or parse error returns an empty list after logging a
    warning. The job must not abort.
"""
from __future__ import annotations

import datetime
import logging
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.fetchers import NewsAnnouncement

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BSE_XML_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/BSEAN.xml"
_BSE_ATTACHMENT_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
_BSE_DT_FMT = "%Y%m%d%H%M%S"   # DT_TM field format: "20260926180000"

_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

_REQUEST_TIMEOUT: float = 15.0
_MAX_RETRIES: int = 2
_RETRY_DELAYS: tuple[float, ...] = (2.0, 4.0)

# XML element tags — BSE uses both <Table> and <row> in different feed versions
_ROW_TAGS: frozenset[str] = frozenset({"Table", "row", "Row"})


# ---------------------------------------------------------------------------
# BSEAnnouncementFetcher
# ---------------------------------------------------------------------------


class BSEAnnouncementFetcher:
    """Fetches BSE corporate announcements from the BSEAN.xml public feed.

    Args:
        client: Optional pre-built httpx.Client for test injection. When
                provided, no real HTTP call is made to bseindia.com.
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._injected_client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(
        self,
        date_from: datetime.date,
        date_to: datetime.date,
    ) -> list[NewsAnnouncement]:
        """Fetch BSE announcements published within [date_from, date_to].

        Returns an empty list on any failure — non-fatal per T-VYS-05.
        Never raises.
        """
        xml_text = self._get_with_retry()
        if not xml_text:
            return []

        all_items = self._parse_xml(xml_text)
        filtered = [
            item for item in all_items
            if _in_date_range(item.published_at, date_from, date_to)
        ]

        log.info(
            "BSEAnnouncementFetcher: parsed %d items, %d in date range %s–%s",
            len(all_items),
            len(filtered),
            date_from,
            date_to,
        )
        return filtered

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_with_retry(self) -> str:
        """GET the BSE XML feed with exponential backoff. Returns '' on failure."""
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return self._get_once()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                if attempt == _MAX_RETRIES:
                    log.warning(
                        "BSEAnnouncementFetcher: all %d attempts failed: %s",
                        _MAX_RETRIES + 1,
                        exc,
                    )
                    return ""
                delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                log.debug(
                    "BSEAnnouncementFetcher: attempt %d failed (%s), retrying in %.1fs",
                    attempt + 1,
                    exc,
                    delay,
                )
                time.sleep(delay)
        return ""  # unreachable

    def _get_once(self) -> str:
        """Perform one HTTP GET, returning the raw response body."""
        if self._injected_client is not None:
            resp = self._injected_client.get(_BSE_XML_URL)
            resp.raise_for_status()
            return resp.text

        with httpx.Client(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(_BSE_XML_URL)
            resp.raise_for_status()
            return resp.text

    def _parse_xml(self, xml_text: str) -> list[NewsAnnouncement]:
        """Parse BSEAN.xml into NewsAnnouncement objects."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            log.warning("BSEAnnouncementFetcher: XML parse error: %s", exc)
            return []

        announcements: list[NewsAnnouncement] = []
        for child in root:
            if child.tag not in _ROW_TAGS:
                continue
            ann = _parse_bse_row(child)
            if ann is not None:
                announcements.append(ann)

        return announcements


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_bse_row(elem: ET.Element) -> NewsAnnouncement | None:
    """Parse one BSE XML row element into a NewsAnnouncement.

    Returns None when required fields are missing or unparseable.
    """
    scrip_code = _text(elem, "COMPANY_CODE")
    headline = _text(elem, "NEWSSUB")
    dt_tm = _text(elem, "DT_TM")
    attachment = _text(elem, "ATTACHMENTNAME")

    if not scrip_code or not headline or not dt_tm:
        return None

    headline = headline.strip()

    # URL: use real attachment if present, otherwise build synthetic
    if attachment and attachment.strip():
        url = f"{_BSE_ATTACHMENT_BASE}{attachment.strip()}"
    else:
        # Deterministic synthetic URL — same announcement always produces same URL
        # so UNIQUE(url) constraint handles re-fetches correctly
        dt_iso = dt_tm.strip()  # keep raw form for URL — readable and unique
        url = f"bse://announcements/{scrip_code.strip()}/{dt_iso}"

    published_at = _parse_bse_timestamp(dt_tm.strip())
    if published_at is None:
        return None

    return NewsAnnouncement(
        source="BSE",
        ticker_raw=None,
        scrip_code=scrip_code.strip(),
        headline=headline,
        url=url,
        published_at=published_at,
        source_name="BSE",
    )


def _text(elem: ET.Element, tag: str) -> str:
    """Return the text of a child element, or '' if absent."""
    child = elem.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text


def _parse_bse_timestamp(dt_tm: str) -> datetime.datetime | None:
    """Parse BSE YYYYMMDDHHMMSS IST string to UTC-aware datetime.

    Returns None on any parse failure.
    """
    if not dt_tm or len(dt_tm) < 14:
        return None
    try:
        dt_ist = datetime.datetime.strptime(dt_tm[:14], _BSE_DT_FMT)
    except ValueError:
        return None
    return dt_ist.replace(tzinfo=_IST).astimezone(datetime.timezone.utc)


def _in_date_range(
    dt_utc: datetime.datetime,
    date_from: datetime.date,
    date_to: datetime.date,
) -> bool:
    """True if dt_utc falls on a calendar date within [date_from, date_to] (UTC day)."""
    d = dt_utc.astimezone(datetime.timezone.utc).date()
    return date_from <= d <= date_to
