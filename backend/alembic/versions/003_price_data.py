"""Create price_data table.

Revision ID: a0003
Revises: a0002
Create Date: 2026-09-25
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0003"
down_revision: str | None = "a0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE price_data (
            id                  BIGSERIAL PRIMARY KEY,
            company_id          INT NOT NULL REFERENCES companies(id),
            trading_date        DATE NOT NULL,
            exchange            VARCHAR(10) NOT NULL
                CHECK (exchange IN ('NSE', 'BSE')),
            open                NUMERIC(14,4),
            high                NUMERIC(14,4),
            low                 NUMERIC(14,4),
            close               NUMERIC(14,4) NOT NULL,
            volume              BIGINT,
            traded_value_inr    NUMERIC(20,2),
            fetcher_source      VARCHAR(30) NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (company_id, trading_date, exchange)
        )
    """)

    op.execute("""
        CREATE INDEX idx_price_data_company_date
            ON price_data(company_id, trading_date DESC)
    """)
    op.execute("""
        CREATE INDEX idx_price_data_date
            ON price_data(trading_date)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS price_data")
