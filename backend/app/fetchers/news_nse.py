"""NSE corporate announcement fetcher (T-VYS-05).

Fetches ALL exchange announcements for NSE-listed companies in a date range
with a single bulk API call — not per-ticker. This is the only reliable way
to get the full NSE announcement feed without triggering rate limits.

NSE Endpoint:
    GET https://www.nseindia.com/api/corporate-announcements
        ?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY

Session warm-up (Sanjaya advisory 2026-09-26):
    NSE runs Cloudflare. A bare API call without cookies returns a 403 or
    challenge page. The workaround: GET the homepage first to obtain session
    cookies, wait _WARM_UP_DELAY seconds, then make the API call using those
    cookies. This has historically worked but is fragile — build it so failure
    is NON-FATAL. An empty news result is valid input for trigger analysis;
    it will produce NO_TRIGGER_TEXT for all stocks, which is correct.

Retry policy:
    On HTTP 429, 503, or network error: retry up to MAX_RETRIES times with
    exponential backoff (_RETRY_DELAYS). After exhausting retries, log a
    warning and return an empty list. The job must not abort.

Timestamps:
    NSE reports times in IST (UTC+5:30). All published_at values in the
    returned NewsAnnouncement objects are converted to UTC.
"""
from __future__ import annotations

import datetime
import logging
import time
from typing import Any

import httpx

from app.fetchers import NewsAnnouncement

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NSE_HOME = "https://www.nseindia.com/"
_NSE_API = "https://www.nseindia.com/api/corporate-announcements"
_NSE_DATE_FMT = "%d-%m-%Y"          # format used in API query string
_NSE_TS_FMT = "%d-%b-%Y %H:%M:%S"   # format in API response exchdisstime field

_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

_WARM_UP_DELAY: float = 1.5          # seconds to wait after homepage before API call
_REQUEST_TIMEOUT: float = 15.0       # httpx timeout in seconds
_MAX_RETRIES: int = 2
_RETRY_DELAYS: tuple[float, ...] = (2.0, 4.0)  # seconds between retries

_BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
    "X-Requested-With": "XMLHttpRequest",
}


# ---------------------------------------------------------------------------
# NSEAnnouncementFetcher
# ---------------------------------------------------------------------------


class NSEAnnouncementFetcher:
    """Fetches NSE corporate announcements for a date range.

    Args:
        client:         Optional pre-built httpx.Client. When provided, the
                        warm-up step is skipped (used in tests to inject a
                        mock client without real network calls).
        warm_up_delay:  Seconds to wait between homepage warm-up and API call.
                        Set to 0 in tests to avoid sleeping.
    """

    def __init__(
        self,
        client: httpx.Client | None = None,
        warm_up_delay: float = _WARM_UP_DELAY,
    ) -> None:
        self._injected_client = client
        self._warm_up_delay = warm_up_delay

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(
        self,
        date_from: datetime.date,
        date_to: datetime.date,
    ) -> list[NewsAnnouncement]:
        """Fetch all NSE corporate announcements for [date_from, date_to].

        Returns an empty list on any failure — non-fatal per T-VYS-05.
        Never raises.
        """
        from_str = date_from.strftime(_NSE_DATE_FMT)
        to_str = date_to.strftime(_NSE_DATE_FMT)
        url = f"{_NSE_API}?index=equities&from_date={from_str}&to_date={to_str}"

        raw: list[dict[str, Any]] = self._get_with_retry(url)
        if not raw:
            return []

        announcements: list[NewsAnnouncement] = []
        for item in raw:
            ann = self._parse_item(item)
            if ann is not None:
                announcements.append(ann)

        log.info(
            "NSEAnnouncementFetcher: fetched %d announcements for %s–%s",
            len(announcements),
            date_from,
            date_to,
        )
        return announcements

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_with_retry(self, url: str) -> list[dict[str, Any]]:
        """GET url with session warm-up + exponential backoff. Returns [] on failure."""
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return self._get_once(url)
            except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
                if attempt == _MAX_RETRIES:
                    log.warning(
                        "NSEAnnouncementFetcher: all %d attempts failed for %s: %s",
                        _MAX_RETRIES + 1,
                        url,
                        exc,
                    )
                    return []
                delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                log.debug(
                    "NSEAnnouncementFetcher: attempt %d failed (%s), retrying in %.1fs",
                    attempt + 1,
                    exc,
                    delay,
                )
                time.sleep(delay)
        return []  # unreachable but satisfies type checker

    def _get_once(self, url: str) -> list[dict[str, Any]]:
        """Make a single GET request, returning the parsed JSON list."""
        if self._injected_client is not None:
            # Test path: use the injected client directly, no warm-up
            resp = self._injected_client.get(url, headers=_BROWSER_HEADERS)
            resp.raise_for_status()
            return self._unwrap(resp.json())

        # Production path: warm up with homepage first to acquire session cookies
        with httpx.Client(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
            try:
                client.get(_NSE_HOME, headers=_BROWSER_HEADERS)
            except httpx.RequestError as exc:
                log.debug("NSEAnnouncementFetcher: homepage warm-up failed (%s) — continuing", exc)
            if self._warm_up_delay > 0:
                time.sleep(self._warm_up_delay)
            resp = client.get(url, headers=_BROWSER_HEADERS)
            resp.raise_for_status()
            return self._unwrap(resp.json())

    @staticmethod
    def _unwrap(data: Any) -> list[dict[str, Any]]:
        """Extract announcement list from NSE response (handles direct list or wrapped object)."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Some NSE endpoints wrap under a "data" or "announcements" key
            for key in ("data", "announcements", "results"):
                if isinstance(data.get(key), list):
                    return data[key]  # type: ignore[return-value]
        raise ValueError(f"Unexpected NSE response shape: {type(data)}")

    @staticmethod
    def _parse_item(item: dict[str, Any]) -> NewsAnnouncement | None:
        """Parse one raw NSE JSON object into a NewsAnnouncement.

        Returns None and logs a warning if the item is missing required fields.
        """
        symbol: str | None = item.get("symbol") or item.get("smIndustry") or None
        subject: str | None = item.get("subject") or item.get("desc") or None
        if not subject:
            return None

        symbol = (symbol or "").strip().upper() or None
        headline = subject.strip()

        # URL: real attachment file if present, otherwise synthetic
        attachment = (item.get("attchmntFile") or "").strip()
        if attachment and attachment.startswith("http"):
            url = attachment
        else:
            seq_id = str(item.get("seq_id", "")).strip()
            if symbol and seq_id:
                url = f"nse://announcements/{symbol}/{seq_id}"
            else:
                log.debug("NSEAnnouncementFetcher: skipping item with no URL: %s", item)
                return None

        # Timestamp: "DD-MMM-YYYY HH:MM:SS" in IST → UTC
        ts_str: str = str(item.get("exchdisstime") or item.get("bdDt") or "").strip()
        published_at = _parse_nse_timestamp(ts_str)
        if published_at is None:
            log.debug("NSEAnnouncementFetcher: cannot parse timestamp %r, skipping", ts_str)
            return None

        return NewsAnnouncement(
            source="NSE",
            ticker_raw=symbol,
            scrip_code=None,
            headline=headline,
            url=url,
            published_at=published_at,
            source_name="NSE",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_nse_timestamp(ts_str: str) -> datetime.datetime | None:
    """Parse NSE 'DD-MMM-YYYY HH:MM:SS' IST string to UTC-aware datetime.

    Returns None on any parse failure rather than raising.
    """
    if not ts_str:
        return None
    try:
        dt_ist = datetime.datetime.strptime(ts_str, _NSE_TS_FMT)
    except ValueError:
        # Try alternate format "YYYY-MM-DD HH:MM:SS"
        try:
            dt_ist = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    return dt_ist.replace(tzinfo=_IST).astimezone(datetime.timezone.utc)
