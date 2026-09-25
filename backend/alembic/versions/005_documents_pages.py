"""Create documents and document_pages tables.

These two tables are the foundation of the document provenance model (ADR-004).
Every document row carries first_seen_at and parser_version from creation so
that the FUT-005 OCR backlog cutoff date can be enforced without retroactive
migration.

Revision ID: a0005
Revises: a0004
Create Date: 2026-09-25
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a0005"
down_revision: str | None = "a0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE documents (
            id                  BIGSERIAL PRIMARY KEY,
            company_id          INT NOT NULL REFERENCES companies(id),
            document_type       VARCHAR(20) NOT NULL
                CHECK (document_type IN ('transcript', 'presentation', 'filing', 'annual_report')),
            fiscal_year         SMALLINT,
            quarter             SMALLINT CHECK (quarter IN (1,2,3,4)),
            filing_date         DATE,
            source_url          TEXT NOT NULL,
            alt_source_url      TEXT,
            alt_source_attempts INT NOT NULL DEFAULT 0,
            file_path           TEXT,
            file_hash           CHAR(64),
            file_size_bytes     BIGINT,
            parse_status        VARCHAR(10) NOT NULL DEFAULT 'pending'
                CHECK (parse_status IN ('pending', 'read', 'partial', 'unread')),
            parse_reason        TEXT,
            parser_version      VARCHAR(20),
            first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            parsed_at           TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX idx_documents_company ON documents(company_id)")
    op.execute("""
        CREATE INDEX idx_documents_type_status
            ON documents(document_type, parse_status)
    """)
    op.execute("""
        CREATE INDEX idx_documents_company_quarter
            ON documents(company_id, fiscal_year, quarter)
    """)

    op.execute("""
        CREATE TABLE document_pages (
            id                  BIGSERIAL PRIMARY KEY,
            document_id         BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            page_number         INT NOT NULL,
            is_read             BOOLEAN NOT NULL,
            char_count          INT NOT NULL DEFAULT 0,
            number_count        INT NOT NULL DEFAULT 0,
            table_count         INT NOT NULL DEFAULT 0,
            chart_count         INT NOT NULL DEFAULT 0,
            extraction_method   VARCHAR(20) NOT NULL
                CHECK (extraction_method IN ('text_layer', 'chart_xml', 'unread')),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (document_id, page_number)
        )
    """)

    op.execute("""
        CREATE INDEX idx_doc_pages_document
            ON document_pages(document_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_pages")
    op.execute("DROP TABLE IF EXISTS documents")
