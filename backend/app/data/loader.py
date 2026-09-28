"""T-VYS-02: Sector classification data loader.

Reads sector_map_v1.yaml and idempotently seeds three tables:
  - sectors          (one row per sector per version)
  - companies        (one row per NSE ticker)
  - sector_mappings  (links each company to its sector)

Decision D2 (2026-09-26): sectors.version IS the map version. The sectors
table already has version INT NOT NULL DEFAULT 1 with a UNIQUE constraint on
(name, classification_source, version). No column is added to sector_mappings;
no separate sector_map_versions table is needed. The ranking layer (T-VIS-01)
reads sector.version at query time and exposes it as SectorRank.map_version
(e.g. "v1").

Idempotency: every entity uses SELECT-before-INSERT. Running the loader twice
against a fully-seeded database produces zero new inserts.

Company names: ticker is used as the name placeholder for Phase 1. Full names
can be enriched in a later task without re-seeding.
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.market import Company, Sector, SectorMapping

log = logging.getLogger(__name__)

_DEFAULT_MAP_FILE = Path(__file__).parent / "sector_map_v1.yaml"


@dataclass
class LoadResult:
    """Counts of inserted vs. already-existing rows per entity type."""

    sectors_inserted: int = 0
    sectors_existing: int = 0
    companies_inserted: int = 0
    companies_existing: int = 0
    mappings_inserted: int = 0
    mappings_existing: int = 0

    @property
    def total_sectors(self) -> int:
        return self.sectors_inserted + self.sectors_existing

    @property
    def total_companies(self) -> int:
        return self.companies_inserted + self.companies_existing

    @property
    def total_mappings(self) -> int:
        return self.mappings_inserted + self.mappings_existing


def load_sector_map(file_path: Path | None = None) -> dict:  # type: ignore[type-arg]
    """Parse the sector map YAML file. Returns the raw dict.

    Raises FileNotFoundError if the file does not exist.
    Raises ValueError if required top-level keys are missing.
    """
    path = file_path or _DEFAULT_MAP_FILE
    with path.open(encoding="utf-8") as fh:
        data: dict = yaml.safe_load(fh)  # type: ignore[type-arg]

    for key in ("version", "classification_source", "effective_date", "sectors"):
        if key not in data:
            raise ValueError(f"sector_map YAML missing required key: '{key}'")

    return data


def seed_database(
    session: Session,
    data: dict | None = None,  # type: ignore[type-arg]
    file_path: Path | None = None,
) -> LoadResult:
    """Idempotently seed sectors, companies, and sector_mappings.

    Pass `data` to bypass file I/O (useful in tests). If `data` is None,
    the map is loaded from `file_path` (or the default sector_map_v1.yaml).

    Commits once at the end. The session must not be in an open transaction
    with unsaved work from outside this function.
    """
    if data is None:
        data = load_sector_map(file_path)

    map_version: int = int(data["version"])
    classification_source: str = str(data["classification_source"])
    effective_date: datetime.date = datetime.date.fromisoformat(data["effective_date"])
    sectors_data: list[dict] = data.get("sectors", [])  # type: ignore[type-arg]

    result = LoadResult()

    for sector_entry in sectors_data:
        sector_name: str = sector_entry["name"]
        tickers: list[str] = [str(t) for t in sector_entry.get("tickers", [])]

        sector, inserted = _get_or_create_sector(
            session,
            name=sector_name,
            classification_source=classification_source,
            version=map_version,
            effective_date=effective_date,
        )
        if inserted:
            result.sectors_inserted += 1
        else:
            result.sectors_existing += 1

        for ticker in tickers:
            company, inserted = _get_or_create_company(session, ticker_nse=ticker)
            if inserted:
                result.companies_inserted += 1
            else:
                result.companies_existing += 1

            _mapping, m_inserted = _get_or_create_mapping(
                session,
                company_id=company.id,
                sector_id=sector.id,
                effective_date=effective_date,
                classification_source=classification_source,
            )
            if m_inserted:
                result.mappings_inserted += 1
            else:
                result.mappings_existing += 1

    session.commit()
    log.info(
        "seed_database v%d: sectors=%d/%d, companies=%d/%d, mappings=%d/%d "
        "(inserted/existing)",
        map_version,
        result.sectors_inserted,
        result.sectors_existing,
        result.companies_inserted,
        result.companies_existing,
        result.mappings_inserted,
        result.mappings_existing,
    )
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_or_create_sector(
    session: Session,
    *,
    name: str,
    classification_source: str,
    version: int,
    effective_date: datetime.date,
) -> tuple[Sector, bool]:
    """Return (sector, was_inserted). Keyed by UNIQUE(name, source, version)."""
    existing = session.execute(
        select(Sector).where(
            Sector.name == name,
            Sector.classification_source == classification_source,
            Sector.version == version,
        )
    ).scalar_one_or_none()

    if existing is not None:
        return existing, False

    sector = Sector(
        name=name,
        classification_source=classification_source,
        version=version,
        effective_date=effective_date,
    )
    session.add(sector)
    session.flush()  # assign sector.id so sector_mappings FK is available
    return sector, True


def _get_or_create_company(
    session: Session,
    *,
    ticker_nse: str,
) -> tuple[Company, bool]:
    """Return (company, was_inserted). Keyed by ticker_nse.

    The partial UNIQUE index on companies(ticker_nse) WHERE NOT NULL makes
    ticker_nse the safe dedup key for NSE companies.
    """
    existing = session.execute(
        select(Company).where(Company.ticker_nse == ticker_nse)
    ).scalar_one_or_none()

    if existing is not None:
        return existing, False

    # Use ticker as the name placeholder; full name can be enriched later.
    company = Company(
        name=ticker_nse,
        ticker_nse=ticker_nse,
        exchange="NSE",
    )
    session.add(company)
    session.flush()  # assign company.id
    return company, True


def _get_or_create_mapping(
    session: Session,
    *,
    company_id: int,
    sector_id: int,
    effective_date: datetime.date,
    classification_source: str,
) -> tuple[SectorMapping, bool]:
    """Return (mapping, was_inserted). Keyed by (company_id, sector_id, is_current).

    Only one active mapping per (company, sector) pair is expected. Historical
    mappings are retained with is_current=False when a sector rebalance occurs;
    this loader only manages the current (is_current=True) rows.
    """
    existing = session.execute(
        select(SectorMapping).where(
            SectorMapping.company_id == company_id,
            SectorMapping.sector_id == sector_id,
            SectorMapping.is_current.is_(True),
        )
    ).scalar_one_or_none()

    if existing is not None:
        return existing, False

    mapping = SectorMapping(
        company_id=company_id,
        sector_id=sector_id,
        is_current=True,
        effective_date=effective_date,
        source=classification_source,
    )
    session.add(mapping)
    session.flush()
    return mapping, True
