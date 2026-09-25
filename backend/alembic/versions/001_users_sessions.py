"""Create users and sessions tables.

Revision ID: a0001
Revises: None
Create Date: 2026-09-25
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE users (
            id              SERIAL PRIMARY KEY,
            email           VARCHAR(255) NOT NULL UNIQUE,
            hashed_password TEXT NOT NULL,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_login_at   TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE sessions (
            id          BIGSERIAL PRIMARY KEY,
            user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash  CHAR(64) NOT NULL UNIQUE,
            expires_at  TIMESTAMPTZ NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            user_agent  TEXT,
            ip_address  INET
        )
    """)

    op.execute("CREATE INDEX idx_sessions_token_hash ON sessions(token_hash)")
    op.execute("CREATE INDEX idx_sessions_user_id    ON sessions(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS users")
