"""ORM models: sectors, companies, sector_mappings, price_data, trading_calendar."""
from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey,
    Integer, Numeric, SmallInteger, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Sector(Base):
    __tablename__ = "sectors"
    __table_args__ = (
        UniqueConstraint("name", "classification_source", "version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    classification_source: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    effective_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    mappings: Mapped[list[SectorMapping]] = relationship(
        "SectorMapping", back_populates="sector"
    )


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ticker_nse: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ticker_bse: Mapped[str | None] = mapped_column(String(20), nullable=True)
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True)
    # CHECK constraint is enforced by the migration DDL, not repeated here
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)
    listed_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sector_mappings: Mapped[list[SectorMapping]] = relationship(
        "SectorMapping", back_populates="company"
    )
    price_data: Mapped[list[PriceData]] = relationship(
        "PriceData", back_populates="company"
    )
    documents: Mapped[list["Document"]] = relationship(  # type: ignore[name-defined]
        "Document", back_populates="company"
    )
    financials_quarterly: Mapped[list["FinancialQuarterly"]] = relationship(  # type: ignore[name-defined]
        "FinancialQuarterly", back_populates="company"
    )
    financials_annual: Mapped[list["FinancialAnnual"]] = relationship(  # type: ignore[name-defined]
        "FinancialAnnual", back_populates="company"
    )
    watchlist_entries: Mapped[list["Watchlist"]] = relationship(  # type: ignore[name-defined]
        "Watchlist", back_populates="company"
    )
    news_items: Mapped[list["NewsItem"]] = relationship(
        "NewsItem", back_populates="company"
    )


class SectorMapping(Base):
    __tablename__ = "sector_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    superseded_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped[Company] = relationship("Company", back_populates="sector_mappings")
    sector: Mapped[Sector] = relationship("Sector", back_populates="mappings")


class PriceData(Base):
    __tablename__ = "price_data"
    __table_args__ = (
        UniqueConstraint("company_id", "trading_date", "exchange"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    trading_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    close: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    traded_value_inr: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    fetcher_source: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped[Company] = relationship("Company", back_populates="price_data")


class NewsItem(Base):
    """Exchange announcement or financial news item fetched by REQ-021.

    UNIQUE(url) enforces deduplication — INSERT ... ON CONFLICT DO NOTHING
    makes repeated fetches idempotent. Both company_id and ticker are nullable:
    company_id is populated when the announcement maps to a tracked company;
    ticker holds the raw symbol from the source when a match hasn't been made.
    """
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="exchange_announcement"
    )
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    published_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped[Company | None] = relationship("Company", back_populates="news_items")


class TradingCalendar(Base):
    """One row per (trading_date, exchange) pair.

    The schema doc defines trading_date as a single-column PK — changed here
    to a composite PK on (trading_date, exchange) so NSE and BSE holidays can
    differ (REQ-035). Migration 004 reflects this correction.
    """
    __tablename__ = "trading_calendar"
    __table_args__ = (
        UniqueConstraint("trading_date", "exchange"),
    )

    trading_date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    exchange: Mapped[str] = mapped_column(String(10), primary_key=True, default="NSE")
    is_trading_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
