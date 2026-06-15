"""Employee dashboard API endpoints."""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Dict, Any, Optional, Tuple
import csv
import os
import sys
from pathlib import Path
import pandas as pd
import logging

# Add src directory to path to import KppEvaluator
project_root = Path(__file__).parent.parent.parent.parent.parent
src_path = project_root / 'src'
sys.path.insert(0, str(src_path))

from KppEvaluator import KppEvaluator
from app.services.employee_score_shared import (
    calculate_rog_status as shared_calculate_rog_status,
    get_prorated_target,
    parse_ref_date,
    read_employee_kpi_value as shared_read_employee_kpi_value,
    read_employee_security_kpi_value_and_status as shared_read_employee_security_kpi_value_and_status,
)
from app.services.scoring_service import get_scoring_service
from app.dependencies import get_current_user
from app.models.user import TokenData
from app.services.user_service import UserService
from app.services.role_service import RoleService
from app.services.rbac_service import RBACService
from app.services.resources_service import ResourcesService
from app.services.dashboard_message_service import get_applicable_messages
from app.services.audit_trail_service import AuditTrailService

audit_trail_service = AuditTrailService()


async def _audit_dashboard_activity(request: Request, current_user: TokenData = Depends(get_current_user)):
    details = {
        "path": request.url.path,
        "query": dict(request.query_params),
        "dashboard": "employee",
    }
    audit_trail_service.record_dashboard_access_event(
        sapid=current_user.sapid,
        user_id=current_user.user_id,
        user_name=current_user.name,
        role=current_user.role,
        method=request.method,
        path=request.url.path,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details=details,
    )
    return current_user


router = APIRouter(prefix="/api/employee-dashboard", tags=["employee-dashboard"], dependencies=[Depends(_audit_dashboard_activity)])
logger = logging.getLogger(__name__)
user_service = UserService()
role_service = RoleService()
rbac_service = RBACService(role_service=role_service, user_service=user_service)
SECURITY_SCAN_KPIS = {"k301", "k302", "k303", "k304", "k305", "k306", "k307"}


def _normalize_resources_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize Resources.csv headers and key string fields used in lookups."""
    df.columns = [str(column).strip() for column in df.columns]
    for column in ['Name', 'SAPID', 'Team', 'Scrum', 'Primary Role', 'Secondary Role', 'Employment Status']:
        if column in df.columns:
            df[column] = df[column].apply(lambda value: str(value).strip() if pd.notna(value) else value)
    return df


def _clean_resource_value(value: Any) -> str:
    """Normalize resource field values for exact matching."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _get_accessible_sapids(viewer_id: int) -> set[str]:
    """Return SAPIDs the viewer is allowed to access."""
    accessible_user_ids = set(rbac_service.get_accessible_users(viewer_id))
    return {
        str(user.sapid).strip()
        for user in user_service.get_all_users(active_only=True)
        if user.id in accessible_user_ids and str(user.sapid).strip()
    }


def _resolve_employee_record(
    resources_df: pd.DataFrame,
    employee_identifier: str,
    viewer,
) -> Tuple[pd.Series, Optional[Any]]:
    """Resolve an employee resource row and mapped RBAC user by SAPID first, then by name."""
    identifier = _clean_resource_value(employee_identifier)
    if not identifier:
        raise HTTPException(status_code=404, detail="Employee identifier is required")

    sapid_series = resources_df['SAPID'].apply(_clean_resource_value)
    sapid_matches = resources_df[sapid_series == identifier]
    if not sapid_matches.empty:
        employee_row = sapid_matches.iloc[0]
        return employee_row, user_service.get_user_by_sapid(identifier)

    name_series = resources_df['Name'].apply(_clean_resource_value)
    name_matches = resources_df[name_series.str.lower() == identifier.lower()]
    if name_matches.empty:
        raise HTTPException(status_code=404, detail=f"Employee '{employee_identifier}' not found")

    if len(name_matches) == 1:
        employee_row = name_matches.iloc[0]
        employee_sapid = _clean_resource_value(employee_row.get('SAPID'))
        target_user = user_service.get_user_by_sapid(employee_sapid) if employee_sapid else None
        return employee_row, target_user

    if viewer.role not in ["Admin", "Admin Viewer", "API User"]:
        accessible_sapids = _get_accessible_sapids(viewer.id)
        accessible_name_matches = name_matches[
            name_matches['SAPID'].apply(lambda value: _clean_resource_value(value) in accessible_sapids)
        ]
        if len(accessible_name_matches) == 1:
            employee_row = accessible_name_matches.iloc[0]
            employee_sapid = _clean_resource_value(employee_row.get('SAPID'))
            target_user = user_service.get_user_by_sapid(employee_sapid) if employee_sapid else None
            return employee_row, target_user

        if accessible_name_matches.empty:
            raise HTTPException(status_code=403, detail="Insufficient permissions for this employee dashboard")

        raise HTTPException(
            status_code=409,
            detail=f"Multiple accessible employees named '{employee_identifier}' found. Use SAPID instead.",
        )

    raise HTTPException(
        status_code=409,
        detail=f"Multiple employees named '{employee_identifier}' found. Use SAPID instead.",
    )


def _read_employee_kpi_value(
    evaluator: KppEvaluator,
    kpi_name: str,
    period: str,
    employee_sapid: str,
    employee_name: str,
    as_of_date: Optional[str] = None,
):
    """Read the latest KPI value for a specific employee using SAPID when available."""
    return shared_read_employee_kpi_value(
        evaluator,
        kpi_name,
        period,
        employee_sapid,
        employee_name,
        as_of_date,
        logger=logger,
    )


def _read_employee_security_kpi_value_and_status(
    evaluator: KppEvaluator,
    kpi_name: str,
    period: str,
    employee_sapid: str,
    employee_name: str,
    as_of_date: Optional[str] = None,
) -> Tuple[Optional[float], str]:
    """Read scan KPI value and configuration status for a specific employee."""
    return shared_read_employee_security_kpi_value_and_status(
        evaluator,
        kpi_name,
        period,
        employee_sapid,
        employee_name,
        as_of_date,
        logger=logger,
    )


def calculate_rog_status(value: float, target: float, goal_type: str) -> str:
    """
    Calculate ROG status based on value, target, and goal type.
    
    Args:
        value: Actual value
        target: Target value
        goal_type: "Maximize" or "Minimize"
        
    Returns:
        "green", "orange", or "red"
    """
    return shared_calculate_rog_status(value, target, goal_type)


def build_employee_dashboard_payload(
    employee_row: pd.Series,
    evaluator: KppEvaluator,
    roles_df: pd.DataFrame,
    period: str = "Annual",
    as_of_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the full employee dashboard payload for a single employee row."""
    employee_data = employee_row.to_dict()
    employee_sapid = _clean_resource_value(employee_row.get('SAPID'))
    employee_name = _clean_resource_value(employee_row.get('Name'))
    employment_status = ResourcesService.normalize_employment_status(employee_row.get('Employment Status', 'Active'))

    if employment_status == 'Inactive':
        employee_profile = {}
        for key, value in employee_data.items():
            if pd.isna(value):
                employee_profile[key] = ""
            else:
                employee_profile[key] = value
        employee_profile['Employment Status'] = 'Inactive'
        return {
            "success": True,
            "inactive": True,
            "message": "Employee is marked inactive. Dashboard is unavailable.",
            "employee": employee_profile,
            "period": period,
            "category_status": {"input": {}, "output": {}, "quality": {}, "hygiene": {}},
            "kpi_performance": [],
            "total_kpis": 0,
            "ticker_messages": [],
        }

    primary_role = employee_data.get('Primary Role', '')
    secondary_role = employee_data.get('Secondary Role', '')

    from datetime import datetime as _dt
    _start_date_str = str(employee_row.get('Start Date', '')).strip()
    employee_start_date = None
    if _start_date_str and _start_date_str not in ('', 'nan'):
        try:
            employee_start_date = _dt.strptime(_start_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    filtered_roles_df = roles_df[pd.notna(roles_df['Goal Type']) & (roles_df['Goal Type'] != '')]
    role_match_mask = (
        (filtered_roles_df['Role'] == primary_role)
        | (filtered_roles_df['Role'] == secondary_role)
        | (filtered_roles_df['Role'] == 'All')
        | (filtered_roles_df['Role'] == 'Common')
    )
    filtered_roles_df = filtered_roles_df[role_match_mask]

    ref_date = parse_ref_date(as_of_date)
    all_kpis = evaluator.list_kpis()

    kpi_performance = []
    kpi_categories = {
        "input": [],
        "output": [],
        "quality": [],
        "hygiene": []
    }

    for kpi in sorted(all_kpis, key=lambda x: int(x[1:])):
        if kpi in SECURITY_SCAN_KPIS:
            employee_value, config_status = _read_employee_security_kpi_value_and_status(
                evaluator, kpi, period, employee_sapid, employee_name, as_of_date
            )
        else:
            employee_value = _read_employee_kpi_value(evaluator, kpi, period, employee_sapid, employee_name, as_of_date)
            config_status = "configured"

        kpi_info = filtered_roles_df[filtered_roles_df['Index'] == kpi]
        if kpi_info.empty:
            continue

        kpi_row = kpi_info.iloc[0]
        kpi_name = kpi_row.get('KPP Goals', kpi.upper())
        kpi_role = kpi_row.get('Role', '')

        if kpi_role == primary_role:
            role_type = 'Primary'
        elif kpi_role == secondary_role:
            role_type = 'Secondary'
        elif kpi_role == 'All':
            role_type = 'All'
        elif kpi_role == 'Common':
            role_type = 'Common'
        else:
            role_type = 'Other'

        goal_type_value = kpi_row.get('Goal Type', 'Input')
        goal_type_lower = str(goal_type_value).lower() if pd.notna(goal_type_value) else 'input'

        if goal_type_lower in ['input', 'i']:
            category = 'input'
        elif goal_type_lower in ['output', 'o']:
            category = 'output'
        elif goal_type_lower in ['quality', 'q']:
            category = 'quality'
        elif goal_type_lower in ['hygiene', 'h']:
            category = 'hygiene'
        else:
            category = 'input'

        type_code = str(kpi_row.get('Type', 'NG')).upper() if pd.notna(kpi_row.get('Type')) else 'NG'
        if 'L' in type_code:
            goal_type = 'Minimize'
        else:
            goal_type = 'Maximize'

        target_col = f"{period.lower()}_target"
        if target_col == "annual_target":
            target = kpi_row.get('Annual Target', 0)
        elif target_col == "quarterly_target":
            target = kpi_row.get('Quarterly Target', 0)
        elif target_col == "monthly_target":
            target = kpi_row.get('Monthly Target', 0)
        else:
            target = kpi_row.get('Weekly Target', 0)

        try:
            target_value = float(target) if pd.notna(target) and target != '' else 0
        except (ValueError, TypeError):
            continue

        if target_value == 0:
            continue

        prorate = str(kpi_row.get('Prorate', 'Yes')).strip().lower() != 'no'

        if kpi in SECURITY_SCAN_KPIS and config_status == "not_configured":
            kpi_entry = {
                "kpi_id": kpi.upper(),
                "kpi_name": kpi_name,
                "category": category,
                "goal_type": goal_type,
                "goal_type_category": goal_type_value,
                "role_type": role_type,
                "actual": None,
                "target": target_value,
                "prorated_target": round(get_prorated_target(target_value, period, ref_date, evaluator.fiscal_start_month, prorate=prorate, employee_start_date=employee_start_date), 1),
                "period": period,
                "prorate": prorate,
                "rog_status": "not_configured",
                "Status": "NotConfigured",
                "percentage": None,
                "measurement_criteria": str(kpi_row.get('Measurement Criteria', '')) if pd.notna(kpi_row.get('Measurement Criteria')) else '',
                "tool": str(kpi_row.get('Tool', '')) if pd.notna(kpi_row.get('Tool')) else '',
                "measure": str(kpi_row.get('Measure', '')) if pd.notna(kpi_row.get('Measure')) else '',
                "excluded_from_score": True,
                "configuration_status": "not_configured",
            }
            kpi_performance.append(kpi_entry)
            if category in kpi_categories:
                kpi_categories[category].append(kpi_entry)
            continue

        if employee_value is None or (isinstance(employee_value, float) and pd.isna(employee_value)):
            continue

        comparison_target = get_prorated_target(target_value, period, ref_date, evaluator.fiscal_start_month, prorate=prorate, employee_start_date=employee_start_date)
        rog_status = calculate_rog_status(employee_value, comparison_target, goal_type)

        try:
            percentage = (float(employee_value) / comparison_target * 100) if comparison_target != 0 else 0
        except (ValueError, TypeError):
            percentage = 0

        kpi_entry = {
            "kpi_id": kpi.upper(),
            "kpi_name": kpi_name,
            "category": category,
            "goal_type": goal_type,
            "goal_type_category": goal_type_value,
            "role_type": role_type,
            "actual": float(employee_value) if not pd.isna(employee_value) else 0,
            "target": target_value,
            "prorated_target": round(comparison_target, 1),
            "period": period,
            "prorate": prorate,
            "rog_status": rog_status,
            "Status": "Green" if rog_status == "green" else ("Orange" if rog_status == "orange" else "Red"),
            "percentage": percentage,
            "measurement_criteria": str(kpi_row.get('Measurement Criteria', '')) if pd.notna(kpi_row.get('Measurement Criteria')) else '',
            "tool": str(kpi_row.get('Tool', '')) if pd.notna(kpi_row.get('Tool')) else '',
            "measure": str(kpi_row.get('Measure', '')) if pd.notna(kpi_row.get('Measure')) else '',
            "excluded_from_score": False,
            "configuration_status": config_status,
        }

        kpi_performance.append(kpi_entry)
        if category in kpi_categories:
            kpi_categories[category].append(kpi_entry)

    category_status = {}
    for category, kpis in kpi_categories.items():
        if not kpis:
            category_status[category] = {
                "status": "green",
                "green_count": 0,
                "orange_count": 0,
                "red_count": 0,
                "total_count": 0
            }
            continue

        green = sum(1 for k in kpis if k['rog_status'] == 'green')
        orange = sum(1 for k in kpis if k['rog_status'] == 'orange')
        red = sum(1 for k in kpis if k['rog_status'] == 'red')
        not_configured = sum(1 for k in kpis if k.get('rog_status') == 'not_configured')
        total = len(kpis) - not_configured

        if total == 0 and not_configured > 0:
            overall = "not_configured"
        elif red > 0:
            overall = "red"
        elif orange > 0:
            overall = "orange"
        else:
            overall = "green"

        category_status[category] = {
            "status": overall,
            "green_count": green,
            "orange_count": orange,
            "red_count": red,
            "total_count": total,
            "not_configured_count": not_configured,
        }

    employee_profile = {}
    for key, value in employee_data.items():
        if pd.isna(value):
            employee_profile[key] = ""
        else:
            employee_profile[key] = value

    category_order = {'input': 0, 'output': 1, 'quality': 2, 'hygiene': 3}
    role_order = {'Primary': 0, 'Secondary': 1, 'All': 2, 'Common': 3, 'Other': 4}
    kpi_performance_sorted = sorted(
        kpi_performance,
        key=lambda x: (
            category_order.get(x['category'], 4),
            role_order.get(x['role_type'], 4),
            int(x['kpi_id'][1:])
        )
    )

    scoring_service = get_scoring_service()
    score_data = scoring_service.calculate_score(kpi_performance_sorted)

    red_kpi_ids = [
        str(kpi.get("kpi_id", "")).strip().lower()
        for kpi in kpi_performance_sorted
        if str(kpi.get("rog_status", "")).strip().lower() == "red"
    ]
    ticker_messages = get_applicable_messages(employee_profile, red_kpi_ids)

    return {
        "success": True,
        "employee": employee_profile,
        "employee_start_date": _start_date_str,
        "period": period,
        "category_status": category_status,
        "kpi_performance": kpi_performance_sorted,
        "total_kpis": len(kpi_performance),
        "score": score_data,
        "ticker_messages": ticker_messages,
    }


@router.get("/{employee_identifier}")
def get_employee_dashboard(
    employee_identifier: str,
    period: str = "Annual",
    as_of_date: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get comprehensive dashboard data for a specific employee.
    
    Returns employee profile, KPI performance, ROG status, and visualizations.
    """
    try:
        # Set up paths
        resources_file = project_root / 'config' / 'Resources.csv'
        jira_issues_file = project_root / 'output' / 'JIRAIssues.csv'
        github_commits_file = project_root / 'output' / 'github_commits.csv'
        output_dir = project_root / 'output'
        roles_file = project_root / 'config' / 'Roles.csv'
        
        # RBAC access check
        viewer = user_service.get_user_by_id(current_user.user_id)
        if not viewer:
            raise HTTPException(status_code=401, detail="Authenticated user not found")

        # Load employee data and resolve by SAPID first to avoid duplicate-name ambiguity
        resources_df = _normalize_resources_df(pd.read_csv(resources_file))
        employee_row, target_user = _resolve_employee_record(resources_df, employee_identifier, viewer)
        employee_sapid = _clean_resource_value(employee_row.get('SAPID'))
        employee_name = _clean_resource_value(employee_row.get('Name'))
        employment_status = ResourcesService.normalize_employment_status(employee_row.get('Employment Status', 'Active'))

        if employment_status == 'Inactive':
            employee_data = employee_row.to_dict()
            employee_profile = {}
            for key, value in employee_data.items():
                if pd.isna(value):
                    employee_profile[key] = ""
                else:
                    employee_profile[key] = value
            employee_profile['Employment Status'] = 'Inactive'
            return {
                "success": True,
                "inactive": True,
                "message": "Employee is marked inactive. Dashboard is unavailable.",
                "employee": employee_profile,
                "period": period,
                "category_status": {"input": {}, "output": {}, "quality": {}, "hygiene": {}},
                "kpi_performance": [],
                "total_kpis": 0,
                "ticker_messages": [],
            }

        if not target_user and employee_sapid:
            target_user = user_service.get_user_by_sapid(employee_sapid)

        if target_user and not rbac_service.can_view_employee_dashboard(viewer.id, target_user.id):
            raise HTTPException(status_code=403, detail="Insufficient permissions for this employee dashboard")

        if not target_user and viewer.role not in ["Admin", "Admin Viewer", "API User"]:
            # If user directory is out of sync, only Admin/API can bypass
            raise HTTPException(status_code=403, detail="Employee is not mapped in user directory")
        
        # Fast path: serve from active daily snapshot when available
        try:
            from app.services.dashboard_snapshot_service import get_dashboard_snapshot_service

            snapshot_service = get_dashboard_snapshot_service()
            snapshot_identifier = employee_sapid or employee_name
            snapshot_payload = snapshot_service.get_employee_payload(snapshot_identifier, period, as_of_date)
            if snapshot_payload:
                # Always recompute ticker_messages live so current rules apply
                # regardless of when the snapshot was generated.
                try:
                    from app.services.dashboard_message_service import get_applicable_messages
                    snap_profile = snapshot_payload.get("employee", {})
                    snap_red_kpi_ids = [
                        str(k.get("kpi_id", "")).strip().lower()
                        for k in snapshot_payload.get("kpi_performance", [])
                        if str(k.get("rog_status", "")).strip().lower() == "red"
                    ]
                    snapshot_payload = dict(snapshot_payload)
                    snapshot_payload["ticker_messages"] = get_applicable_messages(snap_profile, snap_red_kpi_ids)
                except Exception as _msg_exc:
                    logger.warning("Failed to refresh ticker_messages from snapshot: %s", _msg_exc)
                return snapshot_payload
        except Exception as exc:
            logger.warning("Snapshot lookup failed for employee dashboard (%s): %s", employee_identifier, exc)

        roles_df = pd.read_csv(roles_file)

        evaluator = KppEvaluator(
            resources_file=str(resources_file),
            jira_issues_file=str(jira_issues_file),
            github_commits_file=str(github_commits_file),
            output_dir=str(output_dir),
            fiscal_start_month=4
        )
        return build_employee_dashboard_payload(employee_row, evaluator, roles_df, period, as_of_date)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading employee dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list/employees")
def list_employees(current_user: TokenData = Depends(get_current_user)):
    """Get list of all employees for selection dropdown."""
    try:
        resources_file = project_root / 'config' / 'Resources.csv'
        resources_df = _normalize_resources_df(pd.read_csv(resources_file))

        viewer = user_service.get_user_by_id(current_user.user_id)
        if not viewer:
            raise HTTPException(status_code=401, detail="Authenticated user not found")

        accessible_sapids = _get_accessible_sapids(viewer.id)
        
        employees = []
        seen_sapids = set()
        for _, row in resources_df.iterrows():
            name = row.get('Name', '')
            sapid = row.get('SAPID', '')
            team = row.get('Team', '')
            role = row.get('Primary Role', '')
            employment_status = ResourcesService.normalize_employment_status(row.get('Employment Status', 'Active'))
            sapid_str = _clean_resource_value(sapid)
            
            if employment_status != 'Active':
                continue

            if pd.notna(name) and name:
                if viewer.role not in ["Admin", "Admin Viewer", "API User"] and sapid_str not in accessible_sapids:
                    continue
                if sapid_str and sapid_str in seen_sapids:
                    continue
                employees.append({
                    "name": str(name),
                    "sapid": sapid_str,
                    "team": str(team) if pd.notna(team) else "",
                    "role": str(role) if pd.notna(role) else ""
                })
                if sapid_str:
                    seen_sapids.add(sapid_str)
        
        # Sort by name
        employees.sort(key=lambda x: (x['name'].lower(), x['sapid']))
        
        return {
            "success": True,
            "employees": employees,
            "total": len(employees)
        }
        
    except Exception as e:
        logger.error(f"Error listing employees: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{employee_identifier}/assigned-tasks")
def get_employee_assigned_tasks(
    employee_identifier: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Get JIRA issues assigned to an employee that are not closed."""
    try:
        jira_issues_file = project_root / 'output' / 'JIRAIssues.csv'
        resources_file = project_root / 'config' / 'Resources.csv'
        
        if not jira_issues_file.exists():
            return {
                "success": True,
                "tasks": [],
                "total": 0,
                "message": "No JIRA data available"
            }

        # Load employee data to get their name and SAPID
        resources_df = _normalize_resources_df(pd.read_csv(resources_file))
        viewer = user_service.get_user_by_id(current_user.user_id)
        if not viewer:
            raise HTTPException(status_code=401, detail="Authenticated user not found")

        employee_row, target_user = _resolve_employee_record(resources_df, employee_identifier, viewer)
        employee_name = _clean_resource_value(employee_row.get('Name'))
        employee_jira_name = _clean_resource_value(employee_row.get('JIRA Name'))

        if target_user and not rbac_service.can_view_employee_dashboard(viewer.id, target_user.id):
            raise HTTPException(status_code=403, detail="Insufficient permissions for this employee dashboard")

        # Load JIRA issues
        issues_df = pd.read_csv(jira_issues_file)
        
        # Ensure required columns exist
        required_columns = ['Key', 'Summary', 'Status', 'Assignee', 'Sprint.endDate', 'Created', 'Priority', 'Issue Type']
        for column in required_columns:
            if column not in issues_df.columns:
                issues_df[column] = ''
        
        def _normalize_assignee(value: Any) -> str:
            return ' '.join(str(value or '').strip().lower().split())

        # Normalize assignee names for matching
        issues_df['Assignee_normalized'] = issues_df['Assignee'].fillna('').astype(str).apply(_normalize_assignee)
        employee_aliases = {
            _normalize_assignee(employee_name),
            _normalize_assignee(employee_jira_name),
        }
        employee_aliases.discard('')
        
        # Filter by assignee (case-insensitive) and exclude closed statuses
        closed_statuses = {'done', 'closed', 'resolved', 'removed', 'completed'}
        status_normalized = issues_df['Status'].fillna('').astype(str).str.strip().str.lower()
        
        assigned_issues = issues_df[
            (issues_df['Assignee_normalized'].isin(employee_aliases)) &
            (~status_normalized.isin(closed_statuses))
        ].copy()
        
        if assigned_issues.empty:
            return {
                "success": True,
                "tasks": [],
                "total": 0
            }

        # Process issues
        tasks = []
        today = pd.Timestamp.now(tz='UTC').normalize()
        status_order = {
            'in progress': 0,
            'approved': 1,
            'code review': 2,
            'review': 3,
            'testing': 4,
            'ready for qa': 5,
            'in test': 6,
            'to do': 7,
            'open': 8,
            'new': 9,
            'reopened': 10,
            'backlog': 11,
        }
        
        for _, issue in assigned_issues.iterrows():
            try:
                issue_key = _clean_resource_value(issue.get('Key'))
                summary = _clean_resource_value(issue.get('Summary'))
                status = _clean_resource_value(issue.get('Status', 'Unknown'))
                priority = _clean_resource_value(issue.get('Priority', 'Medium'))
                issue_type = _clean_resource_value(issue.get('Issue Type', 'Task'))
                
                # Parse sprint end date
                sprint_end_str = _clean_resource_value(issue.get('Sprint.endDate'))
                sprint_end_date = None
                is_delayed = False
                days_delayed = 0
                due_date_display = "No due date"
                due_date_sort = pd.Timestamp.max.tz_localize('UTC')
                
                if sprint_end_str:
                    try:
                        sprint_end_date = pd.to_datetime(sprint_end_str, utc=True)
                        sprint_end_normalized = sprint_end_date.normalize()
                        due_date_display = sprint_end_normalized.strftime('%Y-%m-%d')
                        due_date_sort = sprint_end_normalized
                        
                        # Check if delayed (today is after sprint end date)
                        if today > sprint_end_normalized:
                            is_delayed = True
                            days_delayed = int((today - sprint_end_normalized).days)
                    except (ValueError, TypeError):
                        pass
                
                tasks.append({
                    "key": issue_key,
                    "summary": summary,
                    "status": status,
                    "status_order": status_order.get(status.lower().strip(), 99),
                    "priority": priority,
                    "issue_type": issue_type,
                    "due_date": due_date_display,
                    "due_date_sort": due_date_sort,
                    "is_delayed": is_delayed,
                    "days_delayed": days_delayed if is_delayed else None
                })
            except Exception as e:
                logger.warning(f"Error processing issue {issue.get('Key')}: {e}")
                continue
        
        # Sort by delayed first, then status flow, then due date
        priority_order = {'Highest': 0, 'High': 1, 'Medium': 2, 'Low': 3, 'Lowest': 4}
        tasks.sort(
            key=lambda x: (
                not x['is_delayed'],  # Delayed issues first
                x['status_order'],  # Workflow status order
                x['due_date_sort'],  # Earlier due date first
                -(x['days_delayed'] or 0),  # More delayed first within same status/due date
                priority_order.get(x['priority'], 5)  # Higher priority first
            )
        )

        for task in tasks:
            task.pop('status_order', None)
            task.pop('due_date_sort', None)
        
        return {
            "success": True,
            "tasks": tasks,
            "total": len(tasks),
            "employee_name": employee_name,
            "matched_aliases": sorted(employee_aliases)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading assigned tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))
