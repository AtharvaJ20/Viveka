"""Create financials_quarterly and financials_annual tables.

Revision ID: a0007
Revises: a0006
Create Date: 2026-09-25
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0007"
down_revision: str | None = "a0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE financials_quarterly (
            id              BIGSERIAL PRIMARY KEY,
            company_id      INT NOT NULL REFERENCES companies(id),
            fiscal_year     SMALLINT NOT NULL,
            quarter         SMALLINT NOT NULL CHECK (quarter IN (1,2,3,4)),
            revenue_cr      NUMERIC(14,2),
            ebitda_cr       NUMERIC(14,2),
            ebitda_pct      NUMERIC(6,3),
            pat_cr          NUMERIC(14,2),
            pat_pct         NUMERIC(6,3),
            eps             NUMERIC(10,4),
            yoy_revenue_pct NUMERIC(8,3),
            yoy_pat_pct     NUMERIC(8,3),
            data_source     VARCHAR(50),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (company_id, fiscal_year, quarter)
        )
    """)

    op.execute("""
        CREATE INDEX idx_fin_q_company
            ON financials_quarterly(company_id, fiscal_year, quarter)
    """)

    op.execute("""
        CREATE TABLE financials_annual (
            id                      BIGSERIAL PRIMARY KEY,
            company_id              INT NOT NULL REFERENCES companies(id),
            fiscal_year             SMALLINT NOT NULL,
            revenue_cr              NUMERIC(14,2),
            ebitda_cr               NUMERIC(14,2),
            ebitda_pct              NUMERIC(6,3),
            pat_cr                  NUMERIC(14,2),
            pat_pct                 NUMERIC(6,3),
            roce_pct                NUMERIC(6,3),
            debt_to_equity          NUMERIC(8,4),
            book_value_per_share    NUMERIC(10,4),
            data_source             VARCHAR(50),
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (company_id, fiscal_year)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS financials_annual")
    op.execute("DROP TABLE IF EXISTS financials_quarterly")
