"""Create news_items table.

Stores exchange announcements and financial news fetched by REQ-021. Persistent
storage is required because:

  - REQ-008 (watchlist news) surfaces items with source links to the UI — a query
    pattern that requires a dedicated table (ticker + time-window lookup).
  - REQ-006 (weekly trigger analysis) spans 7 days; exchange APIs only serve a
    24h window, so re-fetching historical news is not possible.
  - Manual re-runs (T-BHM-03) must produce deterministic trigger summaries; that
    requires the same news rows to exist at re-run time.

Deduplication is enforced by UNIQUE(url) — the same URL from two sources or a
re-fetch is silently ignored (INSERT ... ON CONFLICT DO NOTHING).

Revision ID: a0012
Revises: a0011
Create Date: 2026-09-26
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0012"
down_revision: str | None = "a0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE news_items (
            id              BIGSERIAL PRIMARY KEY,
            company_id      INT REFERENCES companies(id),
            ticker          VARCHAR(20),
            exchange        VARCHAR(10)
                CHECK (exchange IN ('NSE', 'BSE', 'BOTH')),
            source_type     VARCHAR(20) NOT NULL DEFAULT 'exchange_announcement'
                CHECK (source_type IN ('exchange_announcement', 'news')),
            headline        TEXT NOT NULL,
            source_name     VARCHAR(100) NOT NULL,
            url             TEXT NOT NULL,
            published_at    TIMESTAMPTZ NOT NULL,
            fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (url)
        )
    """)

    op.execute("""
        CREATE INDEX idx_news_items_company_published
            ON news_items(company_id, published_at DESC)
            WHERE company_id IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX idx_news_items_ticker_published
            ON news_items(ticker, published_at DESC)
            WHERE ticker IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX idx_news_items_published
            ON news_items(published_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS news_items")
