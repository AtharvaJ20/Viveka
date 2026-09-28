"""Unit tests for T-VIS-01: sector ranking logic.

Coverage (acceptance criteria):
  AC1 — 3 sectors with known price moves → correct descending median order
  AC2 — one outlier +30%, rest flat → sector score ≈ 0% (median, not mean)
  AC3 — sector below SECTOR_MIN_CONSTITUENTS → excluded from price ranking
  AC4 — method="max" → sector score = max constituent move
  AC5 — 20 days of volume data → volume_ratio = today/avg × 100, rounded 2dp
  AC6 — sector excluded from volume ranking when no prior-day volume data
  AC7 — top_constituent selected by highest absolute price change
  AC8 — map_version = "v{sector.version}" on every SectorRank
  AC9 — results sorted descending by sector_score
  AC10 — sector below min_constituents excluded from volume ranking
  AC11 — compute_price_ranking / compute_volume_ranking work with mocked session

Additional:
  AC12 — constituent with open=0 or open=None skipped (pct not computed)
  AC13 — constituent with volume=None or 0 skipped in volume totals
  AC14 — volume_20d_avg=0 → sector excluded from volume ranking
  AC15 — today_sector_vol=0 → sector excluded from volume ranking
  AC16 — fewer prior days than lookback_days → uses what is available
  AC17 — method other than median/max raises ValueError
  AC18 — empty sector list → empty result
  AC19 — top_constituent score = raw pct (not abs), abs used only for selection

Test dates:
  2026-09-28 = Monday (regular trading day, not a holiday)
  Prior days: 2026-09-27 (Sun, weekend), 2026-09-25 (Fri), 2026-09-24 (Thu), ...

All tests operate on in-memory _SectorInput objects — no DB session required
for pure-function tests. A small set of integration-style tests mocks the
session for compute_price_ranking / compute_volume_ranking.
"""
from __future__ import annotations

import datetime
import os
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_viveka")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-exactly-thirty-two-chars")

from app.jobs.ranking import (
    SECTOR_MIN_CONSTITUENTS,
    SECTOR_RANK_METHOD,
    VOLUME_LOOKBACK_DAYS,
    SectorRank,
    TopConstituent,
    _ConstituentData,
    _PriceRow,
    _SectorInput,
    _compute_price_ranks,
    _compute_volume_ranks,
    compute_price_ranking,
    compute_volume_ranking,
)

# ---------------------------------------------------------------------------
# Reference date
# ---------------------------------------------------------------------------

_TODAY = datetime.date(2026, 9, 28)  # Monday — regular trading day

# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


def _row(
    d: datetime.date,
    open_p: float = 100.0,
    close: float = 102.0,
    volume: int = 1_000_000,
) -> _PriceRow:
    return _PriceRow(
        trading_date=d,
        open=Decimal(str(open_p)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _constituent(ticker: str, rows: list[_PriceRow]) -> _ConstituentData:
    return _ConstituentData(company_id=hash(ticker) % 10_000, ticker=ticker, rows=rows)


def _sector(
    name: str,
    constituents: list[_ConstituentData],
    version: int = 1,
    sid: int | None = None,
) -> _SectorInput:
    return _SectorInput(
        sector_id=sid if sid is not None else hash(name) % 10_000,
        sector_name=name,
        map_version=f"v{version}",
        constituents=constituents,
    )


def _sector_with_changes(
    name: str,
    changes: list[float],
    version: int = 1,
    volume: int = 1_000_000,
) -> _SectorInput:
    """Build a sector where each constituent has one row on _TODAY with the given pct change."""
    constituents = []
    for i, pct in enumerate(changes):
        open_p = 100.0
        close = 100.0 * (1.0 + pct / 100.0)
        ticker = f"{name.upper()[:3]}{i+1:02d}"
        constituents.append(
            _constituent(ticker, [_row(_TODAY, open_p=open_p, close=close, volume=volume)])
        )
    return _sector(name, constituents, version=version)


def _sector_with_volume_history(
    name: str,
    today_vol: int,
    prior_vols: list[int],
    version: int = 1,
    pct_change_today: float = 1.0,
    n_constituents: int = 3,
) -> _SectorInput:
    """Build a sector with volume history across multiple constituents.

    today_vol is split evenly across n_constituents tickers.
    prior_vols is a list of SECTOR totals (one per prior day), most-recent-first.
    Each prior day's sector volume is split evenly across the same tickers.
    """
    per_ticker_today = today_vol // n_constituents
    per_ticker_pct = pct_change_today

    constituents = []
    for i in range(n_constituents):
        ticker = f"{name.upper()[:3]}{i+1:02d}"
        open_p = 100.0
        close = 100.0 * (1.0 + per_ticker_pct / 100.0)
        rows: list[_PriceRow] = [
            _row(_TODAY, open_p=open_p, close=close, volume=per_ticker_today)
        ]
        for j, sector_vol in enumerate(prior_vols):
            prior_date = _TODAY - datetime.timedelta(days=j + 1)
            per_ticker_prior = sector_vol // n_constituents
            rows.append(_row(prior_date, open_p=open_p, close=close, volume=per_ticker_prior))
        constituents.append(_constituent(ticker, rows))

    return _sector(name, constituents, version=version)


# ---------------------------------------------------------------------------
# AC1 — 3 sectors ordered by median descending
# ---------------------------------------------------------------------------


class TestPriceRankingOrdering:
    def test_three_sectors_ordered_by_median(self) -> None:  # AC1
        sectors = [
            _sector_with_changes("Banking", [1.0, 2.0, 3.0]),    # median 2.0
            _sector_with_changes("IT", [4.0, 5.0, 6.0]),          # median 5.0
            _sector_with_changes("FMCG", [0.5, 1.0, 1.5]),        # median 1.0
        ]
        result = _compute_price_ranks(sectors, _TODAY, "median", 3)
        assert [r.sector_name for r in result] == ["IT", "Banking", "FMCG"]

    def test_sector_score_is_correct_median(self) -> None:
        sectors = [_sector_with_changes("Banking", [1.0, 3.0, 5.0])]
        result = _compute_price_ranks(sectors, _TODAY, "median", 3)
        assert result[0].sector_score == pytest.approx(3.0, rel=0.001)

    def test_sorted_descending(self) -> None:  # AC9
        sectors = [
            _sector_with_changes("A", [0.5, 1.0, 1.5]),
            _sector_with_changes("B", [3.0, 4.0, 5.0]),
            _sector_with_changes("C", [1.0, 2.0, 3.0]),
        ]
        result = _compute_price_ranks(sectors, _TODAY, "median", 3)
        scores = [r.sector_score for r in result]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# AC2 — median is robust to outlier (not mean)
# ---------------------------------------------------------------------------


class TestPriceRankingMedianVsMean:
    def test_one_outlier_rest_flat_score_near_zero(self) -> None:  # AC2
        # One stock at +30%, four stocks flat (0%).  Mean would be 6%, median 0%.
        sectors = [_sector_with_changes("Banking", [30.0, 0.0, 0.0, 0.0, 0.0])]
        result = _compute_price_ranks(sectors, _TODAY, "median", 3)
        assert result[0].sector_score == pytest.approx(0.0, abs=0.01)

    def test_even_number_of_constituents_median_correct(self) -> None:
        # 4 stocks: [1, 2, 3, 4] → median = (2+3)/2 = 2.5
        sectors = [_sector_with_changes("IT", [1.0, 2.0, 3.0, 4.0])]
        result = _compute_price_ranks(sectors, _TODAY, "median", 3)
        assert result[0].sector_score == pytest.approx(2.5, rel=0.001)


# ---------------------------------------------------------------------------
# AC3 — thin sector excluded
# ---------------------------------------------------------------------------


class TestPriceRankingMinConstituents:
    def test_thin_sector_excluded(self) -> None:  # AC3
        thin = _sector_with_changes("Thin", [5.0, 6.0])        # 2 stocks, need 3
        full = _sector_with_changes("Full", [1.0, 2.0, 3.0])   # 3 stocks, ok
        result = _compute_price_ranks([thin, full], _TODAY, "median", 3)
        names = [r.sector_name for r in result]
        assert "Thin" not in names
        assert "Full" in names

    def test_custom_min_constituents_applied(self) -> None:
        # With min=2, thin sector (2 stocks) should now be included
        thin = _sector_with_changes("Thin", [5.0, 6.0])
        result = _compute_price_ranks([thin], _TODAY, "median", 2)
        assert len(result) == 1
        assert result[0].sector_name == "Thin"

    def test_empty_sector_list_returns_empty(self) -> None:  # AC18
        result = _compute_price_ranks([], _TODAY, "median", 3)
        assert result == []

    def test_all_sectors_thin_returns_empty(self) -> None:
        sectors = [
            _sector_with_changes("A", [1.0, 2.0]),
            _sector_with_changes("B", [3.0]),
        ]
        result = _compute_price_ranks(sectors, _TODAY, "median", 3)
        assert result == []


# ---------------------------------------------------------------------------
# AC4 — method="max" uses max not median
# ---------------------------------------------------------------------------


class TestPriceRankingMaxMethod:
    def test_max_method_returns_highest_value(self) -> None:  # AC4
        # [1.0, 2.0, 30.0] → median=2.0, max=30.0
        sectors = [_sector_with_changes("Banking", [1.0, 2.0, 30.0])]
        result = _compute_price_ranks(sectors, _TODAY, "max", 3)
        assert result[0].sector_score == pytest.approx(30.0, rel=0.001)

    def test_median_method_on_same_data(self) -> None:
        sectors = [_sector_with_changes("Banking", [1.0, 2.0, 30.0])]
        result = _compute_price_ranks(sectors, _TODAY, "median", 3)
        assert result[0].sector_score == pytest.approx(2.0, rel=0.001)

    def test_invalid_method_raises(self) -> None:  # AC17
        sectors = [_sector_with_changes("Banking", [1.0, 2.0, 3.0])]
        with pytest.raises(ValueError, match="Unknown ranking method"):
            _compute_price_ranks(sectors, _TODAY, "unknown", 3)


# ---------------------------------------------------------------------------
# AC7 + AC19 — top_constituent is highest absolute move (may be negative)
# ---------------------------------------------------------------------------


class TestPriceRankingTopConstituent:
    def test_top_constituent_is_highest_abs_not_highest_value(self) -> None:  # AC7
        # STOCK3 at -10% has higher absolute change than STOCK1 at +8%
        constituents = [
            _constituent("STOCK1", [_row(_TODAY, open_p=100.0, close=108.0)]),
            _constituent("STOCK2", [_row(_TODAY, open_p=100.0, close=101.0)]),
            _constituent("STOCK3", [_row(_TODAY, open_p=100.0, close=90.0)]),  # -10%
        ]
        s = _sector("Banking", constituents)
        result = _compute_price_ranks([s], _TODAY, "median", 3)
        assert result[0].top_constituent.ticker == "STOCK3"

    def test_top_constituent_score_is_raw_pct_not_abs(self) -> None:  # AC19
        # top_constituent.score should be the actual pct change, not abs(pct)
        constituents = [
            _constituent("STOCK1", [_row(_TODAY, open_p=100.0, close=108.0)]),
            _constituent("STOCK2", [_row(_TODAY, open_p=100.0, close=101.0)]),
            _constituent("STOCK3", [_row(_TODAY, open_p=100.0, close=90.0)]),  # -10%
        ]
        s = _sector("Banking", constituents)
        result = _compute_price_ranks([s], _TODAY, "median", 3)
        # score should be -10.0, not 10.0
        assert result[0].top_constituent.score < 0

    def test_top_constituent_ticker_is_correct(self) -> None:
        sectors = [_sector_with_changes("IT", [1.0, 2.0, 5.0])]
        result = _compute_price_ranks(sectors, _TODAY, "median", 3)
        # IT02, IT03 in order — the last constituent has +5% (highest abs)
        assert result[0].top_constituent.ticker == "IT03"
        assert result[0].top_constituent.score == pytest.approx(5.0, rel=0.001)


# ---------------------------------------------------------------------------
# AC8 — map_version
# ---------------------------------------------------------------------------


class TestPriceRankingMapVersion:
    def test_map_version_included(self) -> None:  # AC8
        sectors = [_sector_with_changes("Banking", [1.0, 2.0, 3.0], version=1)]
        result = _compute_price_ranks(sectors, _TODAY, "median", 3)
        assert result[0].map_version == "v1"

    def test_map_version_reflects_sector_version(self) -> None:
        sectors = [_sector_with_changes("Banking", [1.0, 2.0, 3.0], version=3)]
        result = _compute_price_ranks(sectors, _TODAY, "median", 3)
        assert result[0].map_version == "v3"


# ---------------------------------------------------------------------------
# AC12 — open=0 or open=None skipped
# ---------------------------------------------------------------------------


class TestPriceRankingBadOpenPrice:
    def test_open_none_constituent_skipped(self) -> None:  # AC12
        rows_ok = [_row(_TODAY, open_p=100.0, close=102.0)]
        rows_null_open = [
            _PriceRow(trading_date=_TODAY, open=None, close=Decimal("102"), volume=1_000_000)
        ]
        constituents = [
            _constituent("OK1", rows_ok),
            _constituent("OK2", rows_ok),
            _constituent("OK3", rows_ok),
            _constituent("BAD", rows_null_open),  # skipped
        ]
        s = _sector("Banking", constituents)
        result = _compute_price_ranks([s], _TODAY, "median", 3)
        assert result[0].constituent_count == 3  # BAD not counted

    def test_open_zero_constituent_skipped(self) -> None:
        rows_ok = [_row(_TODAY, open_p=100.0, close=102.0)]
        rows_zero_open = [
            _PriceRow(trading_date=_TODAY, open=Decimal("0"), close=Decimal("102"), volume=1_000_000)
        ]
        constituents = [
            _constituent("OK1", rows_ok),
            _constituent("OK2", rows_ok),
            _constituent("OK3", rows_ok),
            _constituent("ZERO", rows_zero_open),
        ]
        s = _sector("IT", constituents)
        result = _compute_price_ranks([s], _TODAY, "median", 3)
        assert result[0].constituent_count == 3


# ---------------------------------------------------------------------------
# AC5 — volume ratio formula
# ---------------------------------------------------------------------------


class TestVolumeRankingRatioFormula:
    def test_volume_ratio_equals_today_div_avg_times_100(self) -> None:  # AC5
        # today sector vol = 1,000,000
        # prior 4 days vol: 500,000 each → avg = 500,000
        # ratio = 1,000,000 / 500,000 × 100 = 200.0
        sectors = [
            _sector_with_volume_history(
                "Banking",
                today_vol=1_000_000,
                prior_vols=[500_000, 500_000, 500_000, 500_000],
            )
        ]
        result = _compute_volume_ranks(sectors, _TODAY, lookback_days=4, min_constituents=3)
        assert result[0].sector_score == pytest.approx(200.0, rel=0.001)

    def test_volume_ratio_rounded_to_2dp(self) -> None:
        # today = 1_000_000, prior 3 days = [300_000, 400_000, 500_000]
        # avg = 400_000 → ratio = 250.0 (exact — test with non-exact division)
        # Use today=700_000, prior=[300_000, 400_000] → avg=350_000 → 200.0
        # Use today=700_000, prior=[300_000, 400_001] → avg≠exact, verify rounding
        sectors = [
            _sector_with_volume_history(
                "IT",
                today_vol=700_000,
                prior_vols=[300_000, 400_001],
                n_constituents=3,
            )
        ]
        result = _compute_volume_ranks(sectors, _TODAY, lookback_days=2, min_constituents=3)
        # avg = 350_000.5 → ratio = 700_000 / 350_000.5 × 100 = 199.9997...
        # rounded to 2dp = 200.0
        assert result[0].sector_score == round(700_000 / 350_000.5 * 100, 2)


class TestVolumeRankingOrdering:
    def test_three_sectors_ordered_by_volume_ratio(self) -> None:
        s_high = _sector_with_volume_history("High", today_vol=2_000_000, prior_vols=[500_000] * 5)
        s_mid = _sector_with_volume_history("Mid", today_vol=1_000_000, prior_vols=[500_000] * 5)
        s_low = _sector_with_volume_history("Low", today_vol=250_000, prior_vols=[500_000] * 5)
        result = _compute_volume_ranks(
            [s_mid, s_low, s_high], _TODAY, lookback_days=5, min_constituents=3
        )
        assert [r.sector_name for r in result] == ["High", "Mid", "Low"]


# ---------------------------------------------------------------------------
# AC6 + AC14 + AC15 — volume exclusion cases
# ---------------------------------------------------------------------------


class TestVolumeRankingExclusions:
    def test_no_prior_day_data_excluded(self) -> None:  # AC6
        # Constituents only have today's row — no prior days
        sectors = [_sector_with_volume_history("NoHistory", today_vol=1_000_000, prior_vols=[])]
        result = _compute_volume_ranks(sectors, _TODAY, lookback_days=20, min_constituents=3)
        assert result == []

    def test_zero_20d_avg_excluded(self) -> None:  # AC14
        # prior days all have volume=0
        sectors = [_sector_with_volume_history("ZeroAvg", today_vol=1_000_000, prior_vols=[0] * 5)]
        result = _compute_volume_ranks(sectors, _TODAY, lookback_days=5, min_constituents=3)
        assert result == []

    def test_zero_today_vol_excluded(self) -> None:  # AC15
        sectors = [_sector_with_volume_history("ZeroToday", today_vol=0, prior_vols=[1_000_000] * 5)]
        result = _compute_volume_ranks(sectors, _TODAY, lookback_days=5, min_constituents=3)
        assert result == []

    def test_thin_sector_excluded_from_volume_ranking(self) -> None:  # AC10
        thin = _sector_with_volume_history(
            "Thin", today_vol=1_000_000, prior_vols=[500_000] * 5, n_constituents=2
        )
        result = _compute_volume_ranks([thin], _TODAY, lookback_days=5, min_constituents=3)
        assert result == []


# ---------------------------------------------------------------------------
# AC13 — volume=None or 0 skipped in daily totals
# ---------------------------------------------------------------------------


class TestVolumeRankingNullVolume:
    def test_null_volume_row_not_counted(self) -> None:  # AC13
        # Each constituent must have its OWN row list to avoid shared-list mutation.
        prior_date = _TODAY - datetime.timedelta(days=1)
        constituents = [
            _constituent("OK1", [_row(_TODAY, volume=1_000_000), _row(prior_date, volume=500_000)]),
            _constituent("OK2", [_row(_TODAY, volume=1_000_000), _row(prior_date, volume=500_000)]),
            _constituent("OK3", [_row(_TODAY, volume=1_000_000), _row(prior_date, volume=500_000)]),
            _constituent("NULL_VOL", [
                _PriceRow(trading_date=_TODAY, open=Decimal("100"), close=Decimal("102"), volume=None),
                _row(prior_date, volume=500_000),
            ]),
        ]
        s = _sector("Banking", constituents)
        result = _compute_volume_ranks([s], _TODAY, lookback_days=1, min_constituents=3)
        # Today: 3 × 1_000_000 + 0 (null) = 3_000_000
        # Prior: 3 × 500_000 + 500_000 (NULL_VOL prior has volume) = 2_000_000
        # ratio = 3_000_000 / 2_000_000 × 100 = 150.0
        assert result[0].sector_score == pytest.approx(150.0, rel=0.001)


# ---------------------------------------------------------------------------
# AC16 — fewer prior days than lookback_days
# ---------------------------------------------------------------------------


class TestVolumeRankingPartialHistory:
    def test_fewer_prior_days_uses_available(self) -> None:  # AC16
        # Only 3 prior days available, lookback_days=20
        # avg should be over those 3 days only
        sectors = [
            _sector_with_volume_history(
                "Banking",
                today_vol=1_200_000,
                prior_vols=[400_000, 400_000, 400_000],  # avg = 400_000
                n_constituents=3,
            )
        ]
        result = _compute_volume_ranks(sectors, _TODAY, lookback_days=20, min_constituents=3)
        assert len(result) == 1
        # ratio = 1_200_000 / 400_000 × 100 = 300.0
        assert result[0].sector_score == pytest.approx(300.0, rel=0.001)


# ---------------------------------------------------------------------------
# Default constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_default_min_constituents_is_three(self) -> None:
        assert SECTOR_MIN_CONSTITUENTS == 3

    def test_default_method_is_median(self) -> None:
        assert SECTOR_RANK_METHOD == "median"

    def test_default_lookback_is_twenty(self) -> None:
        assert VOLUME_LOOKBACK_DAYS == 20


# ---------------------------------------------------------------------------
# AC11 — public API with mocked session
# ---------------------------------------------------------------------------


def _mock_session_for_rankings(
    sector_rows: list[tuple],
    price_rows: list[tuple],
) -> MagicMock:
    """Return a session mock with two execute calls returning the given rows."""
    sector_result = MagicMock()
    sector_result.all.return_value = sector_rows
    price_result = MagicMock()
    price_result.all.return_value = price_rows
    session = MagicMock()
    session.execute.side_effect = [sector_result, price_result]
    return session


class TestPublicAPIWithMockedSession:
    def test_compute_price_ranking_returns_sorted_list(self) -> None:  # AC11
        # Sector 1: Banking — HDFCBANK +2%, ICICIBANK +3%, AXISBANK +1% → median 2%
        # Sector 2: IT — TCS +5%, INFY +6%, WIPRO +4% → median 5%
        sector_rows = [
            (1, "Banking", 1, 101, "HDFCBANK"),
            (1, "Banking", 1, 102, "ICICIBANK"),
            (1, "Banking", 1, 103, "AXISBANK"),
            (2, "IT", 1, 201, "TCS"),
            (2, "IT", 1, 202, "INFY"),
            (2, "IT", 1, 203, "WIPRO"),
        ]
        price_rows = [
            (101, _TODAY, Decimal("100"), Decimal("102.0"), 1_000_000),  # +2%
            (102, _TODAY, Decimal("100"), Decimal("103.0"), 1_500_000),  # +3%
            (103, _TODAY, Decimal("100"), Decimal("101.0"), 800_000),    # +1%
            (201, _TODAY, Decimal("100"), Decimal("105.0"), 2_000_000),  # +5%
            (202, _TODAY, Decimal("100"), Decimal("106.0"), 1_800_000),  # +6%
            (203, _TODAY, Decimal("100"), Decimal("104.0"), 1_600_000),  # +4%
        ]
        session = _mock_session_for_rankings(sector_rows, price_rows)
        result = compute_price_ranking(session, _TODAY)
        assert len(result) == 2
        assert result[0].sector_name == "IT"
        assert result[1].sector_name == "Banking"
        assert result[0].sector_score == pytest.approx(5.0, rel=0.001)
        assert result[1].sector_score == pytest.approx(2.0, rel=0.001)
        assert result[0].map_version == "v1"
        assert result[1].map_version == "v1"

    def test_compute_price_ranking_thin_sector_excluded(self) -> None:
        # Banking has 2 stocks (below default min=3) — should be excluded
        sector_rows = [
            (1, "Banking", 1, 101, "HDFCBANK"),
            (1, "Banking", 1, 102, "ICICIBANK"),  # only 2 — thin
            (2, "IT", 1, 201, "TCS"),
            (2, "IT", 1, 202, "INFY"),
            (2, "IT", 1, 203, "WIPRO"),
        ]
        price_rows = [
            (101, _TODAY, Decimal("100"), Decimal("102"), 1_000_000),
            (102, _TODAY, Decimal("100"), Decimal("103"), 1_500_000),
            (201, _TODAY, Decimal("100"), Decimal("105"), 2_000_000),
            (202, _TODAY, Decimal("100"), Decimal("106"), 1_800_000),
            (203, _TODAY, Decimal("100"), Decimal("104"), 1_600_000),
        ]
        session = _mock_session_for_rankings(sector_rows, price_rows)
        result = compute_price_ranking(session, _TODAY)
        names = [r.sector_name for r in result]
        assert "Banking" not in names
        assert "IT" in names

    def test_compute_volume_ranking_returns_sorted_list(self) -> None:
        # Single sector with today's volume and 3 prior days
        sector_rows = [
            (1, "Banking", 1, 101, "HDFCBANK"),
            (1, "Banking", 1, 102, "ICICIBANK"),
            (1, "Banking", 1, 103, "AXISBANK"),
        ]
        prior_day1 = _TODAY - datetime.timedelta(days=1)
        prior_day2 = _TODAY - datetime.timedelta(days=2)
        prior_day3 = _TODAY - datetime.timedelta(days=3)
        price_rows = []
        for cid in [101, 102, 103]:
            price_rows.append((cid, _TODAY, Decimal("100"), Decimal("102"), 1_000_000))
            price_rows.append((cid, prior_day1, Decimal("100"), Decimal("101"), 500_000))
            price_rows.append((cid, prior_day2, Decimal("100"), Decimal("101"), 500_000))
            price_rows.append((cid, prior_day3, Decimal("100"), Decimal("101"), 500_000))

        session = _mock_session_for_rankings(sector_rows, price_rows)
        result = compute_volume_ranking(session, _TODAY, lookback_days=3)
        assert len(result) == 1
        # today total = 3 × 1_000_000 = 3_000_000
        # prior avg = (3 × 500_000) × 3 days / 3 days = 1_500_000
        # ratio = 3_000_000 / 1_500_000 × 100 = 200.0
        assert result[0].sector_score == pytest.approx(200.0, rel=0.001)
        assert result[0].map_version == "v1"

    def test_empty_sector_map_returns_empty(self) -> None:
        session = _mock_session_for_rankings([], [])
        result_price = compute_price_ranking(session, _TODAY)
        assert result_price == []
