"""Scrum dashboard API endpoints."""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Dict, Any, Optional
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
from kpp_k222 import compute_k222_ratio_for_members
from kpp_k268 import compute_k268_ratio_for_members
from app.api.kpi_utils import get_prorated_target, parse_ref_date
from app.services.scoring_service import get_scoring_service
from app.dependencies import get_current_user
from app.models.user import TokenData
from app.services.user_service import UserService
from app.services.audit_trail_service import AuditTrailService

audit_trail_service = AuditTrailService()


async def _audit_dashboard_activity(request: Request, current_user: TokenData = Depends(get_current_user)):
    details = {
        "path": request.url.path,
        "query": dict(request.query_params),
        "dashboard": "scrum",
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


router = APIRouter(prefix="/api/scrum-dashboard", tags=["scrum-dashboard"], dependencies=[Depends(_audit_dashboard_activity)])
logger = logging.getLogger(__name__)
user_service = UserService()
SECURITY_SCAN_KPIS = {"k301", "k302", "k303", "k304", "k305", "k306", "k307"}
# k1 and its equivalent KPIs (same Copilot LOC data file, different roles).
# At team/scrum level these are averaged over the full group size, not just
# the role-applicable subset, because Copilot adoption spans the whole team.
K1_EQUIVALENT_KPIS = {"k1", "k6", "k75", "k88", "k111", "k148"}


def _normalize_resources_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize Resources.csv headers and key string fields used in filters."""
    df.columns = [str(column).strip() for column in df.columns]
    for column in ['Name', 'SAPID', 'Team', 'Scrum', 'Primary Role', 'Secondary Role']:
        if column in df.columns:
            df[column] = df[column].apply(lambda value: str(value).strip() if pd.notna(value) else value)
    return df


def _read_kpi_value_and_config_by_name(evaluator: KppEvaluator, kpi_name: str, period: str, as_of_date: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Read KPI values and configuration status keyed by SAPID (fallback to Name)."""
    base_kpi = evaluator.get_base_kpi(kpi_name)
    kpi_file = os.path.join(evaluator.output_dir, f'{base_kpi}-data.csv')
    if not os.path.exists(kpi_file):
        return {}

    values: Dict[str, Dict[str, Any]] = {}
    try:
        with open(kpi_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if as_of_date:
                    row_date = str(row.get('CurrentDate', '')).strip()
                    if row_date != as_of_date:
                        continue

                sapid = str(row.get('SAPID', '')).strip()
                name = str(row.get('Name', '')).strip()
                # Prefer SAPID as key to avoid same-name collisions across teams
                key = sapid if sapid else name
                if not key:
                    continue

                raw_status = str(row.get('ConfigurationStatus', 'configured')).strip().lower()
                config_status = raw_status if raw_status in ('configured', 'not_configured') else 'configured'
                raw_value = row.get(period, '')
                value = None
                if raw_value not in (None, ''):
                    try:
                        value = float(raw_value)
                    except (ValueError, TypeError):
                        value = None

                values[key] = {
                    'value': value,
                    'configuration_status': config_status,
                }
    except Exception as exc:
        logger.warning("Could not read KPI data from %s: %s", kpi_file, exc)

    return values


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
    if pd.isna(value) or pd.isna(target):
        return "green"  # Missing data treated as green
    
    if target == 0:
        return "green"
    
    percentage = (value / target) * 100
    
    if goal_type == "Maximize":
        if percentage >= 100:
            return "green"
        elif percentage >= 80:
            return "orange"
        else:
            return "red"
    else:  # Minimize
        if percentage <= 100:
            return "green"
        elif percentage <= 120:
            return "orange"
        else:
            return "red"


def aggregate_scrum_kpis(scrum_members: List[str], scrum_members_df: pd.DataFrame, evaluator: KppEvaluator, roles_df: pd.DataFrame, period: str, as_of_date: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate KPI data for a scrum team."""
    ref_date = parse_ref_date(as_of_date)
    all_kpis = evaluator.list_kpis()
    
    scrum_kpi_data = {}
    kpi_categories = {
        "input": [],
        "output": [],
        "quality": [],
        "hygiene": []
    }
    
    for kpi in sorted(all_kpis, key=lambda x: int(x[1:])):
        kpi_data = evaluator.read_kpi_data(kpi, period, as_of_date)
        security_kpi_data = _read_kpi_value_and_config_by_name(evaluator, kpi, period, as_of_date) if kpi in SECURITY_SCAN_KPIS else {}
        
        # Filter roles: only KPIs with Goal Type filled
        kpi_info = roles_df[(roles_df['Index'] == kpi) & 
                           (pd.notna(roles_df['Goal Type'])) & 
                           (roles_df['Goal Type'] != '')]
        
        if kpi_info.empty:
            continue
        
        kpi_row = kpi_info.iloc[0]
        kpi_name = kpi_row.get('KPP Goals', kpi.upper())
        kpi_role = kpi_row.get('Role', '')
        
        # Get category from Goal Type column
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
        
        # Determine maximize/minimize from Type column
        type_code = str(kpi_row.get('Type', 'NG')).upper() if pd.notna(kpi_row.get('Type')) else 'NG'
        if 'L' in type_code:
            goal_type = 'Minimize'
        else:
            goal_type = 'Maximize'
        
        # Get target based on period
        target_col = f"{period.lower()}_target"
        if target_col == "annual_target":
            target = kpi_row.get('Annual Target', 0)
        elif target_col == "quarterly_target":
            target = kpi_row.get('Quarterly Target', 0)
        elif target_col == "monthly_target":
            target = kpi_row.get('Monthly Target', 0)
        else:  # weekly
            target = kpi_row.get('Weekly Target', 0)
        
        try:
            target_value = float(target) if pd.notna(target) and target != '' else 0
        except (ValueError, TypeError):
            continue
        
        if target_value == 0:
            continue
        
        prorate = str(kpi_row.get('Prorate', 'Yes')).strip().lower() != 'no'
        
        # Aggregate values from scrum members - only count members where KPI is applicable
        scrum_values = []
        applicable_count = 0
        applicable_members = []
        for member in scrum_members:
            # Get member's roles
            member_info = scrum_members_df[scrum_members_df['Name'] == member]
            if member_info.empty:
                continue
            
            member_row = member_info.iloc[0]
            primary_role = member_row.get('Primary Role', '')
            secondary_role = member_row.get('Secondary Role', '')
            member_sapid = str(member_row.get('SAPID', '')).strip()
            # Use SAPID as lookup key (matches read_kpi_data and _read_kpi_value_and_config_by_name)
            kpi_lookup_key = member_sapid if member_sapid else member

            # Check if KPI is applicable to this member
            is_applicable = (
                kpi_role == primary_role or
                kpi_role == secondary_role or
                kpi_role in ['All', 'Common']
            )

            if is_applicable:
                applicable_count += 1
                applicable_members.append(member)

            # k222 and k268 are computed separately via ratio functions
            if kpi in ('k222', 'k268'):
                continue

            # Security KPIs: only collect from applicable members (project-scoped)
            if kpi in SECURITY_SCAN_KPIS:
                if not is_applicable:
                    continue
                security_data = security_kpi_data.get(kpi_lookup_key, {})
                if security_data.get('configuration_status') == 'not_configured':
                    continue
                member_value = security_data.get('value', None)
            elif kpi in K1_EQUIVALENT_KPIS:
                # k1 and equivalents: collect from ALL scrum members (Copilot is used
                # across the whole scrum, so absent members count as 0 in the average)
                member_value = kpi_data.get(kpi_lookup_key, None)
            else:
                # All other KPIs: only collect from role-applicable members
                if not is_applicable:
                    continue
                member_value = kpi_data.get(kpi_lookup_key, None)

            if member_value is not None and not pd.isna(member_value):
                try:
                    scrum_values.append(float(member_value))
                except (ValueError, TypeError):
                    continue
        
        if applicable_count == 0:
            continue
        
        if kpi == 'k222':
            scrum_avg, _, total_story_points, _ = compute_k222_ratio_for_members(
                resources_file=evaluator.resources_file,
                jira_issues_file=evaluator.jira_issues_file,
                github_commits_file=evaluator.github_commits_file,
                member_names=applicable_members,
                period=period,
                fiscal_start_month=evaluator.fiscal_start_month
            )

            if total_story_points <= 0:
                continue
        elif kpi == 'k268':
            # Compute as sum(k227)/sum(k1) for the scrum to avoid sentinel 9999
            # values from individual members with no Copilot usage skewing the average.
            scrum_avg = compute_k268_ratio_for_members(
                resources_file=evaluator.resources_file,
                output_dir=evaluator.output_dir,
                member_names=applicable_members,
                period=period,
            )
        else:
            if not scrum_values:
                if kpi in SECURITY_SCAN_KPIS:
                    kpi_entry = {
                        "kpi_id": kpi.upper(),
                        "kpi_name": kpi_name,
                        "category": category,
                        "goal_type": goal_type,
                        "goal_type_category": goal_type_value,
                        "role_specificity": "non_specific" if kpi_role in ('All', 'Common', 'Other') else "specific",
                        "actual": None,
                        "target": target_value,
                        "prorated_target": round(get_prorated_target(target_value, period, ref_date, evaluator.fiscal_start_month, prorate=prorate), 1),
                        "period": period,
                        "prorate": prorate,
                        "rog_status": "not_configured",
                        "Status": "NotConfigured",
                        "percentage": None,
                        "member_count": applicable_count,
                        "measurement_criteria": str(kpi_row.get('Measurement Criteria', '')) if pd.notna(kpi_row.get('Measurement Criteria')) else '',
                        "tool": str(kpi_row.get('Tool', '')) if pd.notna(kpi_row.get('Tool')) else '',
                        "measure": str(kpi_row.get('Measure', '')) if pd.notna(kpi_row.get('Measure')) else '',
                        "excluded_from_score": True,
                        "configuration_status": "not_configured",
                    }
                    if category in kpi_categories:
                        kpi_categories[category].append(kpi_entry)
                continue

            if kpi in K1_EQUIVALENT_KPIS:
                # k1 / equivalents: divide by full scrum size so that members
                # without Copilot data correctly pull the average down.
                scrum_avg = sum(scrum_values) / len(scrum_members)
            else:
                scrum_avg = sum(scrum_values) / len(scrum_values)
        
        # Prorate target for ROG comparison; keep original for display
        comparison_target = get_prorated_target(target_value, period, ref_date, evaluator.fiscal_start_month, prorate=prorate)

        # Calculate ROG status using prorated target
        rog_status = calculate_rog_status(scrum_avg, comparison_target, goal_type)
        
        # Calculate percentage against prorated target
        percentage = (scrum_avg / comparison_target * 100) if comparison_target != 0 else 0
        
        kpi_entry = {
            "kpi_id": kpi.upper(),
            "kpi_name": kpi_name,
            "category": category,
            "goal_type": goal_type,
            "goal_type_category": goal_type_value,  # For scoring
            "role_specificity": "non_specific" if kpi_role in ('All', 'Common', 'Other') else "specific",
            "actual": round(scrum_avg, 1),
            "target": target_value,
            "prorated_target": round(comparison_target, 1),
            "period": period,
            "prorate": prorate,
            "rog_status": rog_status,
            "Status": "Green" if rog_status == "green" else ("Orange" if rog_status == "orange" else "Red"),  # For scoring
            "percentage": round(percentage, 1),
            "member_count": applicable_count,  # Count only members where KPI is applicable
            "measurement_criteria": str(kpi_row.get('Measurement Criteria', '')) if pd.notna(kpi_row.get('Measurement Criteria')) else '',
            "tool": str(kpi_row.get('Tool', '')) if pd.notna(kpi_row.get('Tool')) else '',
            "measure": str(kpi_row.get('Measure', '')) if pd.notna(kpi_row.get('Measure')) else '',
            "excluded_from_score": False,
            "configuration_status": "configured",
        }
        
        if category in kpi_categories:
            kpi_categories[category].append(kpi_entry)
    
    # Calculate overall ROG status for each category
    category_status = {}
    all_kpis_list = []
    
    for category, kpis in kpi_categories.items():
        all_kpis_list.extend(kpis)
        
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
        
        # Determine overall status
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
    
    # Sort KPI list
    category_order = {'input': 0, 'output': 1, 'quality': 2, 'hygiene': 3}
    all_kpis_sorted = sorted(
        all_kpis_list,
        key=lambda x: (category_order.get(x['category'], 4), int(x['kpi_id'][1:]))
    )
    
    # Calculate overall score using scoring service
    scoring_service = get_scoring_service()
    score_data = scoring_service.calculate_score(all_kpis_sorted)
    
    return {
        "category_status": category_status,
        "kpi_performance": all_kpis_sorted,
        "total_kpis": len(all_kpis_sorted),
        "score": score_data
    }


@router.get("/{scrum_name}")
def get_scrum_dashboard(
    scrum_name: str,
    period: str = "Annual",
    as_of_date: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get comprehensive dashboard data for a specific scrum team.
    
    Returns scrum profile, aggregated KPI performance, and ROG status.
    """
    try:
        # Set up paths
        resources_file = project_root / 'config' / 'Resources.csv'
        jira_issues_file = project_root / 'output' / 'JIRAIssues.csv'
        github_commits_file = project_root / 'output' / 'github_commits.csv'
        output_dir = project_root / 'output'
        roles_file = project_root / 'config' / 'Roles.csv'
        
        # Load employee data
        resources_df = _normalize_resources_df(pd.read_csv(resources_file))
        scrum_members_df = resources_df[resources_df['Scrum'] == scrum_name]

        if scrum_members_df.empty:
            raise HTTPException(status_code=404, detail=f"Scrum '{scrum_name}' not found")

        viewer = user_service.get_user_by_id(current_user.user_id)
        if not viewer:
            raise HTTPException(status_code=401, detail="Authenticated user not found")

        if viewer.role not in ["Admin", "Admin Viewer", "API User", "Team Manager", "Lead"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions for scrum dashboard")

        if viewer.role in ["Team Manager", "Lead"]:
            scrum_teams = set(scrum_members_df['Team'].dropna().astype(str).tolist())
            allowed_teams = set(viewer.team_ids or [])
            if not scrum_teams.intersection(allowed_teams):
                raise HTTPException(status_code=403, detail="You can only view scrums for your teams")

        # Fast path: serve from active daily snapshot when available
        try:
            from app.services.dashboard_snapshot_service import get_dashboard_snapshot_service

            snapshot_service = get_dashboard_snapshot_service()
            snapshot_payload = snapshot_service.get_scrum_payload(scrum_name, period, as_of_date)
            if snapshot_payload:
                return snapshot_payload
        except Exception as exc:
            logger.warning("Snapshot lookup failed for scrum dashboard (%s): %s", scrum_name, exc)
        
        # Get scrum member names
        scrum_members = scrum_members_df['Name'].tolist()

        # Get member details with unique SAPID for employee dashboard navigation
        member_details = []
        for _, row in scrum_members_df.iterrows():
            member_details.append({
                "name": row['Name'],
                "sapid": row['SAPID'] if pd.notna(row['SAPID']) else ''
            })
        
        # Load roles data for targets
        roles_df = pd.read_csv(roles_file)
        
        # Create evaluator instance
        evaluator = KppEvaluator(
            resources_file=str(resources_file),
            jira_issues_file=str(jira_issues_file),
            github_commits_file=str(github_commits_file),
            output_dir=str(output_dir),
            fiscal_start_month=4
        )
        
        # Aggregate scrum KPI data
        scrum_data = aggregate_scrum_kpis(scrum_members, scrum_members_df, evaluator, roles_df, period, as_of_date)
        
        # Calculate role distribution
        primary_roles = scrum_members_df['Primary Role'].dropna()
        secondary_roles = scrum_members_df['Secondary Role'].dropna()
        
        primary_role_dist = primary_roles.value_counts().to_dict()
        secondary_role_dist = secondary_roles.value_counts().to_dict()
        
        # Convert to list format for frontend charts
        primary_role_distribution = [{'role': role, 'count': count} for role, count in primary_role_dist.items()]
        secondary_role_distribution = [{'role': role, 'count': count} for role, count in secondary_role_dist.items()]
        
        return {
            "success": True,
            "scrum": {
                "name": scrum_name,
                "member_count": len(scrum_members),
                "members": scrum_members,
                "member_details": member_details,
                "primary_role_distribution": primary_role_distribution,
                "secondary_role_distribution": secondary_role_distribution
            },
            "period": period,
            **scrum_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading scrum dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list/scrums")
def list_scrums(current_user: TokenData = Depends(get_current_user)):
    """Get list of all scrum teams for selection dropdown."""
    try:
        resources_file = project_root / 'config' / 'Resources.csv'
        resources_df = _normalize_resources_df(pd.read_csv(resources_file))

        viewer = user_service.get_user_by_id(current_user.user_id)
        if not viewer:
            raise HTTPException(status_code=401, detail="Authenticated user not found")

        if viewer.role not in ["Admin", "Admin Viewer", "API User", "Team Manager", "Lead"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions for scrum dashboards")
        
        # Get unique scrums
        scrums = resources_df['Scrum'].dropna().unique().tolist()
        scrums = sorted(scrums)

        if viewer.role in ["Team Manager", "Lead"]:
            allowed_teams = set(viewer.team_ids or [])
            scrums = [
                scrum
                for scrum in scrums
                if not resources_df[
                    (resources_df['Scrum'] == scrum) & (resources_df['Team'].isin(list(allowed_teams)))
                ].empty
            ]
        
        # Count members in each scrum
        scrum_list = []
        for scrum in scrums:
            member_count = len(resources_df[resources_df['Scrum'] == scrum])
            scrum_list.append({
                "name": str(scrum),
                "member_count": member_count
            })
        
        return {
            "success": True,
            "scrums": scrum_list,
            "total": len(scrum_list)
        }
        
    except Exception as e:
        logger.error(f"Error listing scrums: {e}")
        raise HTTPException(status_code=500, detail=str(e))
