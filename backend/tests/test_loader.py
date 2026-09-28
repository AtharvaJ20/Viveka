"""Unit tests for T-VYS-02: sector classification loader.

Coverage (acceptance criteria):
  AC1 — fresh DB: loader inserts all sectors (>= 10) and companies/mappings
  AC2 — D2 decision: every inserted Sector has version=1 and
         classification_source="NIFTY_INDEX"
  AC3 — idempotency: second run produces zero inserts (all entities existing)
  AC4 — load_sector_map: YAML file parses correctly, all required keys present
  AC5 — sector with tickers produces one Sector row and N SectorMapping rows

All DB interactions are mocked. No real database connection is required.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call

import pytest

# Set required env vars before importing app modules (matches test_fetchers.py pattern)
import os
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_viveka")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-exactly-thirty-two-chars")

from app.data.loader import (
    LoadResult,
    _get_or_create_company,
    _get_or_create_mapping,
    _get_or_create_sector,
    load_sector_map,
    seed_database,
)
from app.db.models.market import Company, Sector, SectorMapping


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_MINIMAL_DATA: dict[str, Any] = {
    "version": 1,
    "classification_source": "NIFTY_INDEX",
    "effective_date": "2026-09-01",
    "sectors": [
        {"name": "Banking", "tickers": ["HDFCBANK", "ICICIBANK"]},
        {"name": "IT", "tickers": ["TCS"]},
    ],
}
# Banking: 2 companies, 2 mappings; IT: 1 company, 1 mapping → totals: 3/3


_EFFECTIVE = datetime.date(2026, 9, 1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_session() -> MagicMock:
    """Mock session where all queries return None (empty DB).

    session.add.side_effect assigns incrementing IDs so FK references in
    subsequent helpers (e.g. company.id in _get_or_create_mapping) are not None.
    """
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None

    _id: list[int] = [0]

    def _add_with_id(obj: Any) -> None:
        _id[0] += 1
        obj.id = _id[0]

    session.add.side_effect = _add_with_id
    return session


def _full_session() -> MagicMock:
    """Mock session where all queries return an existing mock object (full DB)."""
    session = MagicMock()
    existing = MagicMock()
    existing.id = 99
    session.execute.return_value.scalar_one_or_none.return_value = existing
    return session


# ---------------------------------------------------------------------------
# AC4 — YAML loading (pure function, reads real sector_map_v1.yaml)
# ---------------------------------------------------------------------------

class TestLoadSectorMap:
    def test_returns_dict_with_required_keys(self) -> None:
        data = load_sector_map()
        for key in ("version", "classification_source", "effective_date", "sectors"):
            assert key in data, f"Missing key: {key}"

    def test_version_is_one(self) -> None:
        data = load_sector_map()
        assert data["version"] == 1

    def test_classification_source_is_nifty_index(self) -> None:
        data = load_sector_map()
        assert data["classification_source"] == "NIFTY_INDEX"

    def test_has_at_least_ten_sectors(self) -> None:
        data = load_sector_map()
        assert len(data["sectors"]) >= 10, (
            f"Expected >= 10 sectors, got {len(data['sectors'])}"
        )

    def test_each_sector_has_name_and_tickers(self) -> None:
        data = load_sector_map()
        for sector in data["sectors"]:
            assert "name" in sector, f"Sector missing 'name': {sector}"
            assert "tickers" in sector, f"Sector missing 'tickers': {sector}"
            assert len(sector["tickers"]) > 0, f"Sector '{sector['name']}' has no tickers"

    def test_raises_for_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_sector_map(Path("/nonexistent/path/sector_map.yaml"))

    def test_raises_for_missing_required_key(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("version: 1\nclassification_source: X\n")
        with pytest.raises(ValueError, match="missing required key"):
            load_sector_map(bad_yaml)


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------

class TestGetOrCreateSector:
    def test_inserts_new_sector(self) -> None:
        session = _fresh_session()
        sector, inserted = _get_or_create_sector(
            session,
            name="Banking",
            classification_source="NIFTY_INDEX",
            version=1,
            effective_date=_EFFECTIVE,
        )
        assert inserted is True
        assert sector.name == "Banking"
        assert sector.version == 1
        assert sector.classification_source == "NIFTY_INDEX"
        session.add.assert_called_once_with(sector)
        session.flush.assert_called_once()

    def test_returns_existing_sector(self) -> None:
        session = _full_session()
        sector, inserted = _get_or_create_sector(
            session,
            name="Banking",
            classification_source="NIFTY_INDEX",
            version=1,
            effective_date=_EFFECTIVE,
        )
        assert inserted is False
        session.add.assert_not_called()

    def test_inserted_sector_has_version_one(self) -> None:
        session = _fresh_session()
        sector, _ = _get_or_create_sector(
            session,
            name="Banking",
            classification_source="NIFTY_INDEX",
            version=1,
            effective_date=_EFFECTIVE,
        )
        assert sector.version == 1  # D2 decision verification


class TestGetOrCreateCompany:
    def test_inserts_new_company(self) -> None:
        session = _fresh_session()
        company, inserted = _get_or_create_company(session, ticker_nse="HDFCBANK")
        assert inserted is True
        assert company.ticker_nse == "HDFCBANK"
        assert company.exchange == "NSE"
        session.add.assert_called_once_with(company)
        session.flush.assert_called_once()

    def test_returns_existing_company(self) -> None:
        session = _full_session()
        company, inserted = _get_or_create_company(session, ticker_nse="HDFCBANK")
        assert inserted is False
        session.add.assert_not_called()

    def test_company_name_is_ticker_placeholder(self) -> None:
        session = _fresh_session()
        company, _ = _get_or_create_company(session, ticker_nse="TCS")
        assert company.name == "TCS"


class TestGetOrCreateMapping:
    def test_inserts_new_mapping(self) -> None:
        session = _fresh_session()
        mapping, inserted = _get_or_create_mapping(
            session,
            company_id=1,
            sector_id=1,
            effective_date=_EFFECTIVE,
            classification_source="NIFTY_INDEX",
        )
        assert inserted is True
        assert mapping.is_current is True
        assert mapping.source == "NIFTY_INDEX"
        session.add.assert_called_once_with(mapping)

    def test_returns_existing_mapping(self) -> None:
        session = _full_session()
        mapping, inserted = _get_or_create_mapping(
            session,
            company_id=1,
            sector_id=1,
            effective_date=_EFFECTIVE,
            classification_source="NIFTY_INDEX",
        )
        assert inserted is False
        session.add.assert_not_called()


# ---------------------------------------------------------------------------
# AC1 — fresh DB inserts correct counts
# ---------------------------------------------------------------------------

class TestSeedDatabaseFresh:
    def test_insert_counts_match_minimal_data(self) -> None:
        session = _fresh_session()
        result = seed_database(session, data=_MINIMAL_DATA)

        assert result.sectors_inserted == 2
        assert result.companies_inserted == 3
        assert result.mappings_inserted == 3
        assert result.sectors_existing == 0
        assert result.companies_existing == 0
        assert result.mappings_existing == 0

    def test_commits_exactly_once(self) -> None:
        session = _fresh_session()
        seed_database(session, data=_MINIMAL_DATA)
        session.commit.assert_called_once()

    def test_total_properties(self) -> None:
        session = _fresh_session()
        result = seed_database(session, data=_MINIMAL_DATA)
        assert result.total_sectors == 2
        assert result.total_companies == 3
        assert result.total_mappings == 3

    # AC2 — D2 decision: version=1 stored on every sector
    def test_inserted_sectors_carry_version_one(self) -> None:
        session = _fresh_session()
        inserted_sectors: list[Sector] = []

        original_add = session.add.side_effect

        def _capture_add(obj: Any) -> None:
            original_add(obj)
            if isinstance(obj, Sector):
                inserted_sectors.append(obj)

        session.add.side_effect = _capture_add
        seed_database(session, data=_MINIMAL_DATA)

        assert len(inserted_sectors) == 2
        assert all(s.version == 1 for s in inserted_sectors)
        assert all(s.classification_source == "NIFTY_INDEX" for s in inserted_sectors)

    def test_inserted_companies_have_nse_exchange(self) -> None:
        session = _fresh_session()
        inserted_companies: list[Company] = []

        original_add = session.add.side_effect

        def _capture_add(obj: Any) -> None:
            original_add(obj)
            if isinstance(obj, Company):
                inserted_companies.append(obj)

        session.add.side_effect = _capture_add
        seed_database(session, data=_MINIMAL_DATA)

        assert len(inserted_companies) == 3
        assert all(c.exchange == "NSE" for c in inserted_companies)

    def test_inserted_mappings_are_current(self) -> None:
        session = _fresh_session()
        inserted_mappings: list[SectorMapping] = []

        original_add = session.add.side_effect

        def _capture_add(obj: Any) -> None:
            original_add(obj)
            if isinstance(obj, SectorMapping):
                inserted_mappings.append(obj)

        session.add.side_effect = _capture_add
        seed_database(session, data=_MINIMAL_DATA)

        assert len(inserted_mappings) == 3
        assert all(m.is_current is True for m in inserted_mappings)


# ---------------------------------------------------------------------------
# AC3 — idempotency: second run produces zero new inserts
# ---------------------------------------------------------------------------

class TestSeedDatabaseIdempotent:
    def test_all_existing_produces_zero_inserts(self) -> None:
        session = _full_session()
        result = seed_database(session, data=_MINIMAL_DATA)

        assert result.sectors_inserted == 0
        assert result.companies_inserted == 0
        assert result.mappings_inserted == 0
        assert result.sectors_existing == 2
        assert result.companies_existing == 3
        assert result.mappings_existing == 3
        session.add.assert_not_called()

    def test_idempotent_run_still_commits(self) -> None:
        session = _full_session()
        seed_database(session, data=_MINIMAL_DATA)
        session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# AC5 — sector with no tickers produces sector row but no mappings
# ---------------------------------------------------------------------------

class TestSeedDatabaseEdgeCases:
    def test_sector_with_no_tickers_inserts_sector_only(self) -> None:
        data = {
            "version": 1,
            "classification_source": "NIFTY_INDEX",
            "effective_date": "2026-09-01",
            "sectors": [{"name": "EmptySector", "tickers": []}],
        }
        session = _fresh_session()
        result = seed_database(session, data=data)

        assert result.sectors_inserted == 1
        assert result.companies_inserted == 0
        assert result.mappings_inserted == 0

    def test_real_yaml_file_seeds_correct_sector_count(self) -> None:
        """Smoke test: actual YAML file produces at least 10 sectors."""
        session = _fresh_session()
        result = seed_database(session)
        assert result.total_sectors >= 10
