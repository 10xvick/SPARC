"""
API routes for Role Management (Roles.csv).
"""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Depends, Request
from typing import Optional, Any
from pydantic import BaseModel
import math

from app.models import Role, PaginatedResponse, SuccessResponse, RoleUpdate
from app.services import roles_service
from app.dependencies import require_admin, require_admin_or_read_api
from app.models.user import TokenData
from app.services.audit_trail_service import AuditTrailService

router = APIRouter(prefix="/api/roles", tags=["roles"], dependencies=[Depends(require_admin_or_read_api)])
audit_trail_service = AuditTrailService()


def _sanitize_roles_payload(payload: Any) -> Any:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return {str(k): _sanitize_roles_payload(v) for k, v in list(payload.items())[:50]}
    if isinstance(payload, list):
        return [_sanitize_roles_payload(item) for item in payload[:50]]
    if isinstance(payload, str):
        return payload[:500]
    if isinstance(payload, (int, float, bool)):
        return payload
    return str(payload)


def _record_roles_change_event(
    request: Request,
    current_user: TokenData,
    change: dict[str, Any],
) -> None:
    details = {
        "path": request.url.path,
        "query": _sanitize_roles_payload(dict(request.query_params)),
        "change": _sanitize_roles_payload(change),
        "module": "roles",
    }

    audit_trail_service.record_configuration_event(
        sapid=current_user.sapid,
        user_id=current_user.user_id,
        user_name=current_user.name,
        role=current_user.role,
        method=request.method.upper(),
        path=request.url.path,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details=details,
    )

class TargetUpdateRequest(BaseModel):
    weekly_target: float
    quarterly_target: float
    annual_target: float

@router.get("", response_model=PaginatedResponse)
def get_roles(
    primary_role: Optional[str] = None,
    secondary_role: Optional[str] = None,
    goal_type: Optional[str] = None,
    active: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    sort_by: str = Query("index", regex="^(index|name|goal_type|primary_role)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$")
):
    """Get all roles/KPIs with filtering and pagination."""
    try:
        # Get filtered roles
        roles = roles_service.get_all_roles(
            primary_role=primary_role,
            secondary_role=secondary_role,
            goal_type=goal_type,
            active=active,
            search=search
        )
        
        # Sort
        reverse = sort_order == "desc"
        if sort_by == "index":
            # Sort index numerically (k1, k2, k3... not k1, k10, k2)
            def get_index_num(x):
                try:
                    return int(x['index'].replace('k', ''))
                except:
                    return 0
            roles.sort(key=get_index_num, reverse=reverse)
        elif sort_by == "name":
            roles.sort(key=lambda x: x['name'], reverse=reverse)
        elif sort_by == "goal_type":
            roles.sort(key=lambda x: x['goal_type'], reverse=reverse)
        elif sort_by == "primary_role":
            roles.sort(key=lambda x: x['primary_role'], reverse=reverse)
        
        # Calculate pagination
        total = len(roles)
        total_pages = math.ceil(total / page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        return {
            "data": roles[start_idx:end_idx],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{index}", response_model=Role)
def get_role(index: str):
    """Get a single role/KPI by index."""
    role = roles_service.get_role_by_index(index)
    if not role:
        raise HTTPException(status_code=404, detail=f"Role {index} not found")
    return role

@router.put("/{index}/targets")
def update_role_targets(
    index: str,
    request: TargetUpdateRequest,
    http_request: Request,
    current_user: TokenData = Depends(require_admin),
):
    """Update targets for a specific role/KPI."""
    try:
        updated_role = roles_service.update_targets(
            index=index,
            weekly=request.weekly_target,
            quarterly=request.quarterly_target,
            annual=request.annual_target
        )

        _record_roles_change_event(
            http_request,
            current_user,
            {
                "action": "update_targets",
                "index": index,
                "weekly_target": request.weekly_target,
                "quarterly_target": request.quarterly_target,
                "annual_target": request.annual_target,
            },
        )
        
        return {
            "success": True,
            "message": f"Targets updated successfully for {index}",
            "data": updated_role
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/options/goal-types")
def get_goal_types():
    """Get list of available goal types."""
    return {"goal_types": roles_service.get_goal_types()}

@router.get("/options/primary-roles")
def get_primary_roles():
    """Get list of available primary roles."""
    return {"primary_roles": roles_service.get_primary_roles()}

@router.get("/options/aggregation-types")
def get_aggregation_types():
    """Get list of available aggregation types."""
    return {"aggregation_types": roles_service.get_aggregation_types()}

@router.get("/export/csv")
def export_roles_csv():
    """Export all roles as CSV."""
    from fastapi.responses import StreamingResponse
    import io
    try:
        csv_data = roles_service.export_to_csv()
        return StreamingResponse(
            io.StringIO(csv_data),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=roles.csv"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/import/csv")
async def import_roles_csv(
    http_request: Request,
    file: UploadFile = File(...),
    current_user: TokenData = Depends(require_admin),
):
    """Import roles/KPIs from CSV file."""
    try:
        # Read file content
        content = await file.read()
        csv_content = content.decode('utf-8')
        
        # Import data
        result = roles_service.import_from_csv(csv_content)
        if result["success"]:
            _record_roles_change_event(
                http_request,
                current_user,
                {
                    "action": "import_roles_csv",
                    "filename": file.filename,
                    "size_bytes": len(content),
                    "result": result,
                },
            )
            return result
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
