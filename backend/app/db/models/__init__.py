"""Import all ORM models so they register with Base.metadata.

Alembic env.py does `import app.db.models` which triggers this file,
making all models available for schema diffing and autogenerate.
"""
from app.db.models.auth import User, UserSession
from app.db.models.documents import Document, DocumentPage, ExtractedFigure
from app.db.models.market import (
    Company,
    PriceData,
    Sector,
    SectorMapping,
    TradingCalendar,
)
from app.db.models.research import (
    FinancialAnnual,
    FinancialQuarterly,
    JobExecution,
    LLMUsage,
    Report,
    Watchlist,
)

__all__ = [
    "User",
    "UserSession",
    "Sector",
    "Company",
    "SectorMapping",
    "PriceData",
    "TradingCalendar",
    "Document",
    "DocumentPage",
    "ExtractedFigure",
    "FinancialQuarterly",
    "FinancialAnnual",
    "Report",
    "Watchlist",
    "JobExecution",
    "LLMUsage",
]
