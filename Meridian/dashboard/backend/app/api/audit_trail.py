"""
API endpoints for audit trail data.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies import require_permission
from app.models.user import TokenData
from app.services.audit_trail_service import AuditTrailService

router = APIRouter(prefix="/api/audit-trail", tags=["audit-trail"])
audit_trail_service = AuditTrailService()


@router.get("/logins")
def get_login_audit_events(
    sapid: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    success: Optional[bool] = Query(default=None),
    search: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
    current_user: TokenData = Depends(require_permission("view:audit_trail")),
):
    """Return login audit events with filterable summary for dashboard view."""
    _ = current_user
    return audit_trail_service.list_login_events(
        sapid=sapid,
        role=role,
        success=success,
        search=search,
        start_date=start_date,
        end_date=end_date,
        offset=offset,
        limit=limit,
    )


@router.get("/events")
def get_audit_events(
    event_type: Optional[str] = Query(default="all"),
    sapid: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    success: Optional[bool] = Query(default=None),
    search: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
    current_user: TokenData = Depends(require_permission("view:audit_trail")),
):
    """Return audit events with event-type filtering (login/system admin access/change)."""
    _ = current_user
    return audit_trail_service.list_events(
        event_type=event_type,
        sapid=sapid,
        role=role,
        success=success,
        search=search,
        start_date=start_date,
        end_date=end_date,
        offset=offset,
        limit=limit,
    )
