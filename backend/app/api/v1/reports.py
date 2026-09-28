"""Report endpoints: list, detail, and latest-by-type.

IMPORTANT: Do NOT add `from __future__ import annotations` to this file.
FastAPI introspects route handler and dependency signatures at registration time.
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.auth import User
from app.db.models.research import Report
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ReportSummary(BaseModel):
    id: int
    report_type: str
    trading_date: str | None
    generated_at: str | None
    status: str

    model_config = {"from_attributes": True}


class ReportListResponse(BaseModel):
    items: list[ReportSummary]
    total: int
    page: int
    page_size: int


class ReportDetail(BaseModel):
    id: int
    report_type: str
    trading_date: str | None
    generated_at: str | None
    status: str
    content: Any | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_summary(report: Report) -> ReportSummary:
    return ReportSummary(
        id=report.id,
        report_type=report.report_type,
        trading_date=str(report.trading_date) if report.trading_date else None,
        generated_at=report.generated_at.isoformat() if report.generated_at else None,
        status=report.status,
    )


def _to_detail(report: Report) -> ReportDetail:
    return ReportDetail(
        id=report.id,
        report_type=report.report_type,
        trading_date=str(report.trading_date) if report.trading_date else None,
        generated_at=report.generated_at.isoformat() if report.generated_at else None,
        status=report.status,
        content=report.content,
    )


# ---------------------------------------------------------------------------
# Endpoints — /latest MUST be declared before /{id} to avoid route shadowing
# ---------------------------------------------------------------------------

@router.get("/latest", response_model=ReportDetail)
async def get_latest_report(
    type: str = Query("daily_briefing", description="Report type to retrieve"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> ReportDetail:
    """Return the most recently generated report of the requested type.

    Returns 404 when no report of that type exists yet.
    """
    result = await db.execute(
        select(Report)
        .where(Report.report_type == type)
        .order_by(Report.trading_date.desc().nullslast(), Report.generated_at.desc().nullslast())
        .limit(1)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report found for type '{type}'")
    return _to_detail(report)


@router.get("", response_model=ReportListResponse)
async def list_reports(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    report_type: str | None = Query(None, description="Filter by report type"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> ReportListResponse:
    """Return a paginated list of reports, most-recent first.

    Optional `report_type` filter narrows results to a single type.
    """
    base_filter = []
    if report_type is not None:
        base_filter.append(Report.report_type == report_type)

    count_result = await db.execute(
        select(func.count()).select_from(Report).where(*base_filter)
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    rows_result = await db.execute(
        select(Report)
        .where(*base_filter)
        .order_by(Report.trading_date.desc().nullslast(), Report.generated_at.desc().nullslast())
        .offset(offset)
        .limit(page_size)
    )
    reports = rows_result.scalars().all()

    return ReportListResponse(
        items=[_to_summary(r) for r in reports],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{report_id}", response_model=ReportDetail)
async def get_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> ReportDetail:
    """Return the full report including its JSONB content."""
    result = await db.execute(
        select(Report).where(Report.id == report_id)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return _to_detail(report)
