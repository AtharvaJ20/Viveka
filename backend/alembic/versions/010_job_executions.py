"""Create job_executions table.

Tracks every scheduler run for audit, retry detection, and manual re-run
capability. All scheduled jobs must write a row here; a status of 'skipped'
with skip_reason='non_trading_day' is the correct outcome on market holidays.

Revision ID: a0010
Revises: a0009
Create Date: 2026-09-25
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0010"
down_revision: str | None = "a0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE job_executions (
            id              BIGSERIAL PRIMARY KEY,
            job_name        VARCHAR(50) NOT NULL,
            triggered_by    VARCHAR(20) NOT NULL
                CHECK (triggered_by IN ('scheduler', 'manual')),
            started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at    TIMESTAMPTZ,
            status          VARCHAR(10) NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'success', 'failed', 'skipped')),
            skip_reason     TEXT,
            retry_count     SMALLINT NOT NULL DEFAULT 0,
            error_message   TEXT,
            report_id       BIGINT REFERENCES reports(id)
        )
    """)

    op.execute("""
        CREATE INDEX idx_job_executions_name_date
            ON job_executions(job_name, started_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS job_executions")
