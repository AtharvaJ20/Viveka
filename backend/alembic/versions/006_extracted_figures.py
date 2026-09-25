"""Create extracted_figures table.

Stores every numeric value extracted from a document page with full provenance:
which document, which page, which parser version, and which extraction method.
Reports embed this provenance as JSONB blocks (ADR-004).

Cannot be added retroactively — provenance must be written at extraction time.

Revision ID: a0006
Revises: a0005
Create Date: 2026-09-25
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0006"
down_revision: str | None = "a0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE extracted_figures (
            id                  BIGSERIAL PRIMARY KEY,
            document_id         BIGINT NOT NULL REFERENCES documents(id),
            page_number         INT NOT NULL,
            extraction_method   VARCHAR(20) NOT NULL
                CHECK (extraction_method IN ('text_layer', 'chart_xml', 'unread')),
            parser_version      VARCHAR(20) NOT NULL,
            raw_text            TEXT,
            value_numeric       NUMERIC,
            value_text          VARCHAR(100),
            unit                VARCHAR(50),
            label               TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX idx_extracted_figures_document
            ON extracted_figures(document_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS extracted_figures")
