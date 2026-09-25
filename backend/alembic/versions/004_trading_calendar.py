"""Create trading_calendar table.

Revision ID: a0004
Revises: a0003
Create Date: 2026-09-25
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0004"
down_revision: str | None = "a0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # trading_date is the PK — one row per date per exchange
    # Muhurat sessions have is_trading_day = FALSE (REQ-003, REQ-035)
    op.execute("""
        CREATE TABLE trading_calendar (
            trading_date    DATE NOT NULL,
            is_trading_day  BOOLEAN NOT NULL,
            reason          VARCHAR(100),
            exchange        VARCHAR(10) NOT NULL DEFAULT 'NSE',
            source          VARCHAR(50),
            fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (trading_date, exchange)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS trading_calendar")
