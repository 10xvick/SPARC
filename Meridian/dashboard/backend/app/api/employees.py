"""
API routes for Employee Management (Resources.csv).
"""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Depends, Request
from typing import Optional, List
import math

from app.models import Employee, PaginatedResponse, SuccessResponse
from app.models.user import UserCreate, TokenData
from app.services import resources_service
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.services.notification_mail_service import NotificationMailService
from app.models.user import UserCreate
from app.dependencies import require_admin, require_admin_or_read_api

router = APIRouter(prefix="/api/employees", tags=["employees"], dependencies=[Depends(require_admin_or_read_api)])
user_service = UserService()
notification_mail_service = NotificationMailService()

@router.get("", response_model=PaginatedResponse)
def get_employees(
    team: Optional[str] = None,
    scrum: Optional[str] = None,
    primary_role: Optional[str] = None,
    secondary_role: Optional[str] = None,
    search: Optional[str] = None,
    include_inactive: bool = Query(True, description="Include inactive employees in results"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100)
):
    """Get all employees with filtering and pagination."""
    try:
        # Get filtered employees
        employees = resources_service.get_all_employees(
            team=team,
            scrum=scrum,
            primary_role=primary_role,
            secondary_role=secondary_role,
            search=search,
            include_inactive=include_inactive,
        )
        
        # Calculate pagination
        total = len(employees)
        total_pages = math.ceil(total / page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        return {
            "data": employees[start_idx:end_idx],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{sapid}", response_model=Employee)
def get_employee(sapid: str):
    """Get a single employee by SAPID."""
    employee = resources_service.get_employee_by_sapid(sapid)
    if not employee:
        raise HTTPException(status_code=404, detail=f"Employee {sapid} not found")
    return employee

@router.get("/options/teams")
def get_teams():
    """Get list of available teams."""
    return {"teams": resources_service.get_teams()}

@router.get("/options/scrums")
def get_scrums():
    """Get list of available scrums."""
    return {"scrums": resources_service.get_scrums()}

@router.get("/options/roles")
def get_role_options():
    """Get available roles for dropdowns."""
    primary_roles = resources_service.get_primary_roles()
    secondary_roles = resources_service.get_secondary_roles()
    
    return {
        "primary_roles": [{"value": r, "label": r} for r in primary_roles],
        "secondary_roles": [{"value": r, "label": r} for r in secondary_roles]
    }

@router.get("/options/managers")
def get_manager_options():
    """Get list of all employees for manager dropdown."""
    try:
        managers = resources_service.get_manager_options()
        return {"managers": managers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{sapid}")
def update_employee(sapid: str, updates: dict, current_user: TokenData = Depends(require_admin)):
    """Update employee information."""
    try:
        # Map frontend field names to CSV column names.
        field_map = {
            'ref': 'Ref',
            'sapid': 'SAPID',
            'name': 'Name',
            'team': 'Team',
            'scrum': 'Scrum',
            'primary_role': 'Primary Role',
            'secondary_role': 'Secondary Role',
            'reporting': 'Reporting',
            'manager': 'Manager',
            'manager_name': 'Manager Name',
            'email': 'EMail',
            'resource_sheet_name': 'ResourceSheetName',
            'resource_sheet_id': 'ResourceSheetID',
            'jira_name': 'JIRA Name',
            'git_email': 'GIT Email',
            'udeid': 'UDEID',
            'tacid': 'TACID',
            'url': 'URL',
            'github_name': 'GitHUB Name',
            'copilot_user': 'copilot_user',
            'employment_status': 'Employment Status',
            'start_date': 'Start Date',
        }

        mapped_updates = {}
        for key, value in (updates or {}).items():
            if key == 'create_rbac_user':
                continue
            mapped_updates[field_map.get(key, key)] = value

        result = resources_service.update_employee(sapid, mapped_updates)
        if result:
            return {"success": True, "message": "Employee updated successfully", "data": result}
        else:
            raise HTTPException(status_code=404, detail="Employee not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{sapid}/status")
def update_employee_status(sapid: str, payload: dict, current_user: TokenData = Depends(require_admin)):
    """Update employee status (Active/Inactive)."""
    status = (payload or {}).get("status", "")
    if str(status).strip().lower() not in {"active", "inactive"}:
        raise HTTPException(status_code=400, detail="Status must be Active or Inactive")

    try:
        result = resources_service.set_employee_status(sapid, status)
        if result:
            rbac_removed = False
            if str(status).strip().lower() == "inactive":
                rbac_removed = user_service.delete_user_by_sapid(sapid)
            return {
                "success": True,
                "message": f"Employee marked as {result.get('employment_status', status)}",
                "data": result,
                "rbac_user_removed": rbac_removed,
            }
        raise HTTPException(status_code=404, detail="Employee not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{sapid}")
def delete_employee(sapid: str, current_user: TokenData = Depends(require_admin)):
    """Hard delete employee from Resources.csv."""
    try:
        existing_user = user_service.get_user_by_sapid(sapid)
        if existing_user and str(existing_user.role).strip().lower() == "admin":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Employee {sapid} cannot be deleted while RBAC role is Admin. "
                    "Change role first, then delete."
                ),
            )

        deleted = resources_service.delete_employee(sapid)
        if not deleted:
            raise HTTPException(status_code=404, detail="Employee not found")

        rbac_removed = user_service.delete_user_by_sapid(sapid)
        return {
            "success": True,
            "message": f"Employee {sapid} deleted successfully",
            "rbac_user_removed": rbac_removed,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
def add_employee(
    employee: dict,
    request: Request,
    current_user: TokenData = Depends(require_admin),
):
    """Add a new employee."""
    try:
        # Map frontend field names to CSV column names.
        reporting_value = employee.get('reporting', 0.0)
        try:
            reporting_value = float(reporting_value) if reporting_value not in (None, '') else 0.0
        except Exception:
            reporting_value = 0.0

        csv_employee = {
            'SAPID': str(employee.get('sapid', '')).strip(),
            'Name': str(employee.get('name', '')).strip(),
            'Team': str(employee.get('team', '')).strip(),
            'Scrum': str(employee.get('scrum', '')).strip(),
            'Primary Role': str(employee.get('primary_role', '')).strip(),
            'Secondary Role': str(employee.get('secondary_role', '')).strip(),
            'Manager': str(employee.get('manager', '')).strip(),  # SAPID/Ref/Name; normalized in service
            'Manager Name': str(employee.get('manager_name', '')).strip(),
            'Reporting': reporting_value,
            'EMail': employee.get('email', ''),
            'Ref': employee.get('ref', ''),
            'ResourceSheetName': employee.get('resource_sheet_name', ''),
            'ResourceSheetID': employee.get('resource_sheet_id', ''),
            'JIRA Name': employee.get('jira_name', ''),
            'GIT Email': employee.get('git_email', ''),
            'UDEID': employee.get('udeid', ''),
            'TACID': employee.get('tacid', ''),
            'URL': employee.get('url', ''),
            'GitHUB Name': employee.get('github_name', ''),
            'copilot_user': employee.get('copilot_user', ''),
            'Employment Status': employee.get('employment_status', 'Active') or 'Active',
            'Start Date': employee.get('start_date', ''),
        }
        
        result = resources_service.add_employee(csv_employee)

        rbac_created = False
        generated_password = None
        rbac_email_notification_status = None
        rbac_email_notification_message = None
        create_rbac_user = bool(employee.get('create_rbac_user', False))
        if create_rbac_user:
            existing_rbac_user = user_service.get_user_by_sapid(str(result.get('sapid', '')).strip())
            if not existing_rbac_user:
                generated_password = AuthService.generate_default_password()
                user_create = UserCreate(
                    sapid=str(result.get('sapid', '')).strip(),
                    name=str(result.get('name', '')).strip(),
                    email=(result.get('email') or None),
                    role='User',
                    password=generated_password,
                    team_ids=[str(result.get('team', '')).strip()] if str(result.get('team', '')).strip() else [],
                    is_active=str(result.get('employment_status', 'Active')).strip().lower() != 'inactive',
                    source='manual',
                )
                user_service.create_user(user_create)
                rbac_created = True
                email_result = notification_mail_service.send_credentials_email(
                    to_address=(result.get('email') or None),
                    user_name=str(result.get('name', '')).strip(),
                    user_sapid=str(result.get('sapid', '')).strip(),
                    password=generated_password,
                    mode='create',
                    dashboard_url=str(request.base_url).rstrip('/'),
                )
                rbac_email_notification_status = email_result.get('status')
                rbac_email_notification_message = email_result.get('message')

        message = "Employee added successfully"
        if create_rbac_user and rbac_created:
            message = "Employee and RBAC user created successfully"
        elif create_rbac_user:
            message = "Employee added successfully (RBAC user already exists)"

        return {
            "success": True,
            "message": message,
            "data": result,
            "rbac_user_created": rbac_created,
            "rbac_default_password": generated_password,
            "rbac_email_notification_status": rbac_email_notification_status,
            "rbac_email_notification_message": rbac_email_notification_message,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export/csv")
def export_employees_csv():
    """Export all employees as CSV."""
    from fastapi.responses import StreamingResponse
    import io
    try:
        csv_data = resources_service.export_to_csv()
        return StreamingResponse(
            io.StringIO(csv_data),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=employees.csv"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/recalculate-reporting")
def recalculate_reporting_counts(current_user: TokenData = Depends(require_admin)):
    """Recalculate Reporting counts for all managers based on direct reports."""
    try:
        result = resources_service.recalculate_all_reporting_counts()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/import/csv")
async def import_employees_csv(file: UploadFile = File(...), current_user: TokenData = Depends(require_admin)):
    """Import employees from CSV file."""
    try:
        # Read file content
        content = await file.read()
        csv_content = content.decode('utf-8')
        
        # Import data
        result = resources_service.import_from_csv(csv_content)
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
