"""Create sectors, companies, and sector_mappings tables.

Revision ID: a0002
Revises: a0001
Create Date: 2026-09-25
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0002"
down_revision: str | None = "a0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sectors (
            id                      SERIAL PRIMARY KEY,
            name                    VARCHAR(100) NOT NULL,
            classification_source   VARCHAR(50) NOT NULL,
            version                 INT NOT NULL DEFAULT 1,
            effective_date          DATE NOT NULL,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (name, classification_source, version)
        )
    """)

    op.execute("""
        CREATE TABLE companies (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(255) NOT NULL,
            ticker_nse  VARCHAR(20),
            ticker_bse  VARCHAR(20),
            isin        CHAR(12),
            exchange    VARCHAR(10) NOT NULL
                CHECK (exchange IN ('NSE', 'BSE', 'NSE_BSE', 'SME_NSE', 'SME_BSE')),
            listed_date DATE,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Partial unique indexes: enforce uniqueness only where the column is not NULL
    op.execute("""
        CREATE UNIQUE INDEX idx_companies_ticker_nse
            ON companies(ticker_nse)
            WHERE ticker_nse IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_companies_ticker_bse
            ON companies(ticker_bse)
            WHERE ticker_bse IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX idx_companies_isin
            ON companies(isin)
            WHERE isin IS NOT NULL
    """)

    op.execute("""
        CREATE TABLE sector_mappings (
            id              SERIAL PRIMARY KEY,
            company_id      INT NOT NULL REFERENCES companies(id),
            sector_id       INT NOT NULL REFERENCES sectors(id),
            is_current      BOOLEAN NOT NULL DEFAULT TRUE,
            effective_date  DATE NOT NULL,
            superseded_date DATE,
            source          VARCHAR(50) NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX idx_sector_mappings_company
            ON sector_mappings(company_id, is_current)
    """)
    op.execute("""
        CREATE INDEX idx_sector_mappings_sector
            ON sector_mappings(sector_id, is_current)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sector_mappings")
    op.execute("DROP TABLE IF EXISTS companies")
    op.execute("DROP TABLE IF EXISTS sectors")
