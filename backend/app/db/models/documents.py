"""ORM models: documents, document_pages, extracted_figures.

These models implement the document provenance contract from ADR-003 and ADR-004.
- first_seen_at and parser_version are set at document creation time, not at parse time.
- parse_status tracks the DocumentParser Protocol result: pending → read | partial | unread.
- ExtractedFigure rows are written atomically with the parse result, never retroactively.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer,
    Numeric, SmallInteger, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    fiscal_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    quarter: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    filing_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    alt_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    alt_source_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # CHECK constraint on parse_status enforced by migration DDL
    parse_status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    parse_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # FUT-005: set at row creation — never update. Used for OCR backlog cutoff.
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    parsed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped["Company"] = relationship(  # type: ignore[name-defined]
        "Company", back_populates="documents"
    )
    pages: Mapped[list[DocumentPage]] = relationship(
        "DocumentPage", back_populates="document", cascade="all, delete-orphan"
    )
    figures: Mapped[list[ExtractedFigure]] = relationship(
        "ExtractedFigure", back_populates="document"
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_read: Mapped[bool] = mapped_column(nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    number_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chart_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # CHECK constraint on extraction_method enforced by migration DDL
    extraction_method: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[Document] = relationship("Document", back_populates="pages")


class ExtractedFigure(Base):
    """A single numeric or text value extracted from a document page.

    Written atomically with the parse result — never updated or back-filled.
    The combination of document_id + page_number + parser_version establishes
    the provenance chain embedded in report JSONB blocks (ADR-004).
    """
    __tablename__ = "extracted_figures"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(20), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[Document] = relationship("Document", back_populates="figures")
