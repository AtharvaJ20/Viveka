"""Create watchlist table.

Max 50 entries per user is enforced at the application layer (REQ-007),
not here — a DB constraint would make limit increases require a migration.

Revision ID: a0008
Revises: a0007
Create Date: 2026-09-25
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0008"
down_revision: str | None = "a0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE watchlist (
            id          SERIAL PRIMARY KEY,
            user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_id  INT NOT NULL REFERENCES companies(id),
            added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            notes       TEXT,
            UNIQUE (user_id, company_id)
        )
    """)

    op.execute("CREATE INDEX idx_watchlist_user ON watchlist(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS watchlist")
