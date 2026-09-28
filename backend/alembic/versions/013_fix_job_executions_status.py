"""Fix job_executions.status CHECK constraint.

Migration a0010 declared the status column as:
    CHECK (status IN ('running', 'success', 'failed', 'skipped'))

The scheduler (app/scheduler.py _mark_completed) writes 'completed', not
'success'. 'success' was the original design-time value; the implementation
settled on 'completed' (more precise — describes terminal state, not business
outcome). The mismatch means every successful live scheduler run raises a
PostgreSQL CHECK constraint violation and leaves the row in status='running'.

This migration replaces 'success' with 'completed' in the constraint.

PostgreSQL auto-names an inline CHECK constraint as
    <table>_<column>_check
when no explicit name is supplied. The original CREATE TABLE used an inline
CHECK, so the generated name is job_executions_status_check. We drop that
constraint and recreate it with the correct value set.

Revision ID: a0013
Revises: a0012
Create Date: 2026-09-28
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0013"
down_revision: str | None = "a0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop the constraint PostgreSQL auto-named at CREATE TABLE time.
    op.execute("""
        ALTER TABLE job_executions
            DROP CONSTRAINT IF EXISTS job_executions_status_check
    """)
    # Re-create with 'completed' in place of 'success'.
    op.execute("""
        ALTER TABLE job_executions
            ADD CONSTRAINT job_executions_status_check
            CHECK (status IN ('running', 'completed', 'failed', 'skipped'))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE job_executions
            DROP CONSTRAINT IF EXISTS job_executions_status_check
    """)
    # Restore the original (incorrect) constraint — downgrade restores schema
    # state, not correctness.
    op.execute("""
        ALTER TABLE job_executions
            ADD CONSTRAINT job_executions_status_check
            CHECK (status IN ('running', 'success', 'failed', 'skipped'))
    """)
