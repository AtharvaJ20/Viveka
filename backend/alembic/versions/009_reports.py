"""Create reports table.

The content column is JSONB — structured report output with embedded provenance
blocks per ADR-004. GIN index enables archive search (WEB-006).

Revision ID: a0009
Revises: a0008
Create Date: 2026-09-25
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0009"
down_revision: str | None = "a0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE reports (
            id              BIGSERIAL PRIMARY KEY,
            report_type     VARCHAR(30) NOT NULL
                CHECK (report_type IN (
                    'daily_briefing', 'weekly_report', 'deep_dive',
                    'watchlist_news', 'bse_sme_section'
                )),
            trading_date    DATE,
            week_start_date DATE,
            week_end_date   DATE,
            company_id      INT REFERENCES companies(id),
            requested_by    INT REFERENCES users(id),
            status          VARCHAR(10) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'published', 'failed')),
            content         JSONB,
            generated_at    TIMESTAMPTZ,
            published_at    TIMESTAMPTZ,
            error_message   TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX idx_reports_type_date
            ON reports(report_type, trading_date DESC)
    """)
    op.execute("""
        CREATE INDEX idx_reports_company
            ON reports(company_id)
            WHERE company_id IS NOT NULL
    """)
    op.execute("CREATE INDEX idx_reports_status ON reports(status)")
    op.execute("""
        CREATE INDEX idx_reports_content_gin
            ON reports USING GIN(content)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reports")
