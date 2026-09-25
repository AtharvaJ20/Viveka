"""Create llm_usage table.

Every LLM API call is logged here by LLMClient (ADR-005). The cost ceiling
check queries this table before every call:

    SELECT SUM(cost_inr)
      FROM llm_usage
     WHERE date_trunc('month', created_at) = date_trunc('month', now())

Breaching ₹500/month is a defect (REQ-034), not an overage. The ceiling gate
runs in LLMClient.call() before the API call is made.

Revision ID: a0011
Revises: a0010
Create Date: 2026-09-25
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0011"
down_revision: str | None = "a0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE llm_usage (
            id              BIGSERIAL PRIMARY KEY,
            job_type        VARCHAR(50) NOT NULL,
            model           VARCHAR(60) NOT NULL,
            input_tokens    INT NOT NULL,
            output_tokens   INT NOT NULL,
            cost_usd        NUMERIC(10,6) NOT NULL,
            cost_inr        NUMERIC(10,4) NOT NULL,
            usd_to_inr_rate NUMERIC(8,4) NOT NULL,
            report_id       BIGINT REFERENCES reports(id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX idx_llm_usage_created ON llm_usage(created_at)
    """)
    op.execute("""
        CREATE INDEX idx_llm_usage_report
            ON llm_usage(report_id)
            WHERE report_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_usage")
