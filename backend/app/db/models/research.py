"""ORM models: financials_quarterly, financials_annual, reports, watchlist,
job_executions, llm_usage.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Integer,
    Numeric, SmallInteger, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FinancialQuarterly(Base):
    __tablename__ = "financials_quarterly"
    __table_args__ = (
        UniqueConstraint("company_id", "fiscal_year", "quarter"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    quarter: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    revenue_cr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    ebitda_cr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    ebitda_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    pat_cr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    pat_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    eps: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    yoy_revenue_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    yoy_pat_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    data_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped["Company"] = relationship(  # type: ignore[name-defined]
        "Company", back_populates="financials_quarterly"
    )


class FinancialAnnual(Base):
    __tablename__ = "financials_annual"
    __table_args__ = (
        UniqueConstraint("company_id", "fiscal_year"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    revenue_cr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    ebitda_cr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    ebitda_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    pat_cr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    pat_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    roce_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    book_value_per_share: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    data_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped["Company"] = relationship(  # type: ignore[name-defined]
        "Company", back_populates="financials_annual"
    )


class Report(Base):
    """A generated report of any type.

    content is JSONB with embedded provenance blocks (ADR-004). The GIN index
    on content is created by migration 009 and enables archive keyword search.
    """
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    report_type: Mapped[str] = mapped_column(String(30), nullable=False)
    trading_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    week_start_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    week_end_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True, index=True
    )
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="draft")
    content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    generated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    llm_usage: Mapped[list[LLMUsage]] = relationship(
        "LLMUsage", back_populates="report"
    )
    job_executions: Mapped[list[JobExecution]] = relationship(
        "JobExecution", back_populates="report"
    )


class Watchlist(Base):
    __tablename__ = "watchlist"
    __table_args__ = (
        UniqueConstraint("user_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    added_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="watchlist")  # type: ignore[name-defined]
    company: Mapped["Company"] = relationship("Company", back_populates="watchlist_entries")  # type: ignore[name-defined]


class JobExecution(Base):
    """Execution log for every scheduled or manual job run.

    Every scheduled job must write a row here, including skipped runs.
    skip_reason='non_trading_day' is correct on market holidays (REQ-003).
    """
    __tablename__ = "job_executions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(50), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="running")
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reports.id"), nullable=True
    )

    report: Mapped[Report | None] = relationship("Report", back_populates="job_executions")


class LLMUsage(Base):
    """Cost log for every LLM API call.

    Written by LLMClient.call() after every successful API call (ADR-005).
    The monthly ceiling check queries SUM(cost_inr) on this table.
    """
    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    cost_inr: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    usd_to_inr_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    report_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reports.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    report: Mapped[Report | None] = relationship("Report", back_populates="llm_usage")
