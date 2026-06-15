"""
Bug Cycle Time API endpoints.
Serves bug cycle time analysis data from kpp_bug_cycle_time.py outputs.
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any, Optional, Tuple
import pandas as pd
from pathlib import Path
import logging

from app.models.user import TokenData
from app.dependencies import require_report_access
from app.services.user_service import UserService
from app.services.role_service import RoleService
from app.services.rbac_service import RBACService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/bug-cycle-time",
    tags=["Bug Cycle Time"],
    dependencies=[Depends(require_report_access)]
)

rbac_user_service = UserService()
rbac_role_service = RoleService()
rbac_service = RBACService(rbac_role_service, rbac_user_service)

# Data file paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
BUG_CYCLE_TIME_FILE = OUTPUT_DIR / "bug_cycle_time.csv"


def _normalize_text(value: object) -> str:
    """Normalize free text for robust matching and filtering."""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null"}:
        return ""
    return text


def _normalize_person_name(value: object) -> str:
    """Normalize person names for reliable assignee matching."""
    name = _normalize_text(value)
    if not name:
        return ""

    normalized = name.replace('[External]', '').strip()
    normalized = " ".join(normalized.split())
    return normalized.lower()


def _get_accessible_bug_scope(current_user: TokenData) -> Tuple[Optional[set[str]], set[str]]:
    """Return normalized accessible assignees and teams for RBAC report scoping."""
    if current_user.role in ["Admin", "API User"]:
        return None, set()

    accessible_assignees: set[str] = set()
    accessible_teams: set[str] = set()

    for accessible_user_id in rbac_service.get_accessible_users(current_user.user_id):
        accessible_user = rbac_user_service.get_user_by_id(accessible_user_id)
        if not accessible_user:
            continue

        normalized_name = _normalize_person_name(accessible_user.name)
        if normalized_name:
            accessible_assignees.add(normalized_name)

        for team_id in accessible_user.team_ids or []:
            cleaned_team = _normalize_text(team_id)
            if cleaned_team:
                accessible_teams.add(cleaned_team)

    return accessible_assignees, accessible_teams


def _apply_bug_cycle_time_rbac(
    source_df: pd.DataFrame,
    current_user: TokenData,
) -> Tuple[pd.DataFrame, set[str]]:
    """Apply RBAC filtering to bug cycle time data and return scoped dataframe."""
    accessible_assignees, accessible_teams = _get_accessible_bug_scope(current_user)

    scoped_df = source_df.copy()
    if accessible_assignees is None:
        return scoped_df, accessible_teams

    scoped_df["_assignee_norm"] = scoped_df["Assignee"].apply(_normalize_person_name)
    scoped_df["_team_clean"] = scoped_df["Team"].fillna("").astype(str).str.strip()

    scoped_df = scoped_df[
        scoped_df["_assignee_norm"].isin(accessible_assignees)
        | scoped_df["_team_clean"].isin(accessible_teams)
    ].copy()

    return scoped_df, accessible_teams


def _build_group_summary(df: pd.DataFrame, group_column: str) -> list[dict[str, object]]:
    """Build summary rows grouped by the provided column."""
    if df.empty:
        return []

    summary_df = (
        df.groupby(group_column, dropna=False)
        .agg(
            Bug_Count=("Key", "count"),
            Avg_Cycle_Time_Days=("Total_Cycle_Time_Days", "mean"),
            Median_Cycle_Time_Days=("Total_Cycle_Time_Days", "median"),
            Min_Cycle_Time_Days=("Total_Cycle_Time_Days", "min"),
            Max_Cycle_Time_Days=("Total_Cycle_Time_Days", "max"),
            Avg_Transitions=("Transition_Count", "mean"),
            Avg_Rework_Count=("Rework_Count", "mean"),
        )
        .reset_index()
    )

    summary_df[group_column] = summary_df[group_column].fillna("Unknown").astype(str)

    numeric_columns = [
        "Avg_Cycle_Time_Days",
        "Median_Cycle_Time_Days",
        "Min_Cycle_Time_Days",
        "Max_Cycle_Time_Days",
        "Avg_Transitions",
        "Avg_Rework_Count",
    ]
    for column in numeric_columns:
        summary_df[column] = summary_df[column].fillna(0).round(2)

    summary_df["Bug_Count"] = summary_df["Bug_Count"].fillna(0).astype(int)
    summary_df = summary_df.sort_values("Bug_Count", ascending=False)

    return summary_df.to_dict("records")


def load_bug_cycle_time_data() -> pd.DataFrame:
    """Load bug cycle time data from CSV."""
    if not BUG_CYCLE_TIME_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Bug cycle time data not found. Please run kpp_bug_cycle_time.py first."
        )
    
    try:
        df = pd.read_csv(BUG_CYCLE_TIME_FILE)

        text_columns = [
            "Key", "Project", "Team", "Scrum", "Assignee", "Priority",
            "Current_Status", "First_Status", "Final_Status"
        ]
        for column in text_columns:
            if column not in df.columns:
                df[column] = "Unknown"
            df[column] = df[column].fillna("Unknown").astype(str).str.strip()

        numeric_columns = ["Total_Cycle_Time_Days", "Transition_Count", "Rework_Count"]
        for column in numeric_columns:
            if column not in df.columns:
                df[column] = 0
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

        return df
    except Exception as e:
        logger.error(f"Error loading bug cycle time data: {e}")
        raise HTTPException(status_code=500, detail=f"Error loading data: {str(e)}")


@router.get("/summary")
def get_bug_cycle_time_summary(
    current_user: TokenData = Depends(require_report_access),
) -> Dict[str, Any]:
    """Get bug cycle time summary statistics by priority, team, and scrum."""
    try:
        scoped_df, _ = _apply_bug_cycle_time_rbac(load_bug_cycle_time_data(), current_user)
        response_df = scoped_df.drop(columns=["_assignee_norm", "_team_clean"], errors="ignore")

        result = {
            "by_priority": _build_group_summary(response_df, "Priority"),
            "by_team": _build_group_summary(response_df, "Team"),
            "by_scrum": _build_group_summary(response_df, "Scrum")
        }
        
        return result
    except Exception as e:
        logger.error(f"Error getting bug cycle time summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bugs")
def get_bugs(
    team: Optional[str] = Query(None, description="Filter by team"),
    scrum: Optional[str] = Query(None, description="Filter by scrum"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    project: Optional[str] = Query(None, description="Filter by project"),
    min_cycle_time: Optional[float] = Query(None, description="Minimum cycle time in days"),
    max_cycle_time: Optional[float] = Query(None, description="Maximum cycle time in days"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page"),
    current_user: TokenData = Depends(require_report_access),
) -> Dict[str, Any]:
    """Get detailed bug cycle time data with filtering and pagination."""
    try:
        scoped_df, _ = _apply_bug_cycle_time_rbac(load_bug_cycle_time_data(), current_user)
        scoped_df = scoped_df.drop(columns=["_assignee_norm", "_team_clean"], errors="ignore")
        filtered_df = scoped_df.copy()
        
        # Apply filters
        if team and team != "All":
            filtered_df = filtered_df[filtered_df['Team'] == team]
        
        if scrum and scrum != "All":
            filtered_df = filtered_df[filtered_df['Scrum'] == scrum]
        
        if priority and priority != "All":
            filtered_df = filtered_df[filtered_df['Priority'] == priority]
        
        if project and project != "All":
            filtered_df = filtered_df[filtered_df['Project'] == project]
        
        if min_cycle_time is not None:
            filtered_df = filtered_df[filtered_df['Total_Cycle_Time_Days'] >= min_cycle_time]
        
        if max_cycle_time is not None:
            filtered_df = filtered_df[filtered_df['Total_Cycle_Time_Days'] <= max_cycle_time]
        
        # Sort by cycle time descending
        filtered_df = filtered_df.sort_values('Total_Cycle_Time_Days', ascending=False)
        
        # Calculate pagination
        total_items = len(filtered_df)
        total_pages = (total_items + page_size - 1) // page_size
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        # Get page data
        page_df = filtered_df.iloc[start_idx:end_idx]
        
        # Convert to records
        bugs = page_df.to_dict('records')
        
        # Get unique filter values
        filters = {
            "teams": sorted([str(x) for x in scoped_df['Team'].dropna().unique()]),
            "scrums": sorted([str(x) for x in scoped_df['Scrum'].dropna().unique()]),
            "priorities": sorted([str(x) for x in scoped_df['Priority'].dropna().unique()]),
            "projects": sorted([str(x) for x in scoped_df['Project'].dropna().unique()])
        }
        
        return {
            "bugs": bugs,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages
            },
            "filters": filters
        }
    except Exception as e:
        logger.error(f"Error getting bugs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-issues")
def get_top_issues(
    limit: int = Query(10, ge=1, le=100, description="Number of top issues to return"),
    sort_by: str = Query("cycle_time", description="Sort by: cycle_time, rework_count, transitions"),
    current_user: TokenData = Depends(require_report_access),
) -> Dict[str, Any]:
    """Get top issues by cycle time, rework count, or transition count."""
    try:
        scoped_df, _ = _apply_bug_cycle_time_rbac(load_bug_cycle_time_data(), current_user)
        scoped_df = scoped_df.drop(columns=["_assignee_norm", "_team_clean"], errors="ignore")

        if scoped_df.empty:
            return {
                "top_issues": [],
                "sort_by": sort_by,
                "limit": limit
            }
        
        # Determine sort column
        sort_column = {
            "cycle_time": "Total_Cycle_Time_Days",
            "rework_count": "Rework_Count",
            "transitions": "Transition_Count"
        }.get(sort_by, "Total_Cycle_Time_Days")
        
        # Get top issues
        top_df = scoped_df.nlargest(limit, sort_column)
        
        # Select relevant columns
        columns = [
            'Key', 'Project', 'Team', 'Scrum', 'Assignee', 'Priority',
            'Current_Status', 'Total_Cycle_Time_Days', 'Transition_Count',
            'Rework_Count', 'First_Status', 'Final_Status'
        ]
        
        result_columns = [column for column in columns if column in top_df.columns]
        result_df = top_df[result_columns]
        
        return {
            "top_issues": result_df.to_dict('records'),
            "sort_by": sort_by,
            "limit": limit
        }
    except Exception as e:
        logger.error(f"Error getting top issues: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    current_user: TokenData = Depends(require_report_access),
) -> Dict[str, Any]:
    """Get overall statistics for bug cycle times."""
    try:
        scoped_df, _ = _apply_bug_cycle_time_rbac(load_bug_cycle_time_data(), current_user)
        scoped_df = scoped_df.drop(columns=["_assignee_norm", "_team_clean"], errors="ignore")

        if scoped_df.empty:
            return {
                "total_bugs": 0,
                "avg_cycle_time_days": 0.0,
                "median_cycle_time_days": 0.0,
                "min_cycle_time_days": 0.0,
                "max_cycle_time_days": 0.0,
                "avg_transitions": 0.0,
                "avg_rework_count": 0.0,
                "bugs_with_rework": 0,
                "rework_percentage": 0.0
            }

        bugs_with_rework = int((scoped_df['Rework_Count'] > 0).sum())
        rework_percentage = round((bugs_with_rework / len(scoped_df) * 100), 1) if len(scoped_df) > 0 else 0.0
        
        stats = {
            "total_bugs": len(scoped_df),
            "avg_cycle_time_days": round(scoped_df['Total_Cycle_Time_Days'].mean(), 2),
            "median_cycle_time_days": round(scoped_df['Total_Cycle_Time_Days'].median(), 2),
            "min_cycle_time_days": round(scoped_df['Total_Cycle_Time_Days'].min(), 2),
            "max_cycle_time_days": round(scoped_df['Total_Cycle_Time_Days'].max(), 2),
            "avg_transitions": round(scoped_df['Transition_Count'].mean(), 2),
            "avg_rework_count": round(scoped_df['Rework_Count'].mean(), 2),
            "bugs_with_rework": bugs_with_rework,
            "rework_percentage": rework_percentage
        }
        
        return stats
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rework-by-assignee")
def get_rework_by_assignee(
    limit: int = Query(15, ge=1, le=50, description="Number of top assignees to return"),
    current_user: TokenData = Depends(require_report_access),
) -> Dict[str, Any]:
    """Get assignees with the most rework cases."""
    try:
        scoped_df, _ = _apply_bug_cycle_time_rbac(load_bug_cycle_time_data(), current_user)
        scoped_df = scoped_df.drop(columns=["_assignee_norm", "_team_clean"], errors="ignore")
        
        # Filter bugs with rework
        rework_df = scoped_df[scoped_df['Rework_Count'] > 0].copy()

        if rework_df.empty:
            return {
                "top_assignees": [],
                "total_assignees_with_rework": 0,
                "total_rework_cases": 0
            }
        
        # Group by assignee and calculate statistics
        assignee_stats = rework_df.groupby('Assignee').agg({
            'Key': 'count',
            'Rework_Count': ['sum', 'mean'],
            'Total_Cycle_Time_Days': 'mean'
        }).round(2)
        
        assignee_stats.columns = ['_'.join(col).strip() for col in assignee_stats.columns.values]
        assignee_stats = assignee_stats.rename(columns={
            'Key_count': 'bugs_with_rework',
            'Rework_Count_sum': 'total_rework_count',
            'Rework_Count_mean': 'avg_rework_per_bug',
            'Total_Cycle_Time_Days_mean': 'avg_cycle_time'
        })
        
        # Sort by total rework count and get top N
        assignee_stats = assignee_stats.sort_values('total_rework_count', ascending=False).head(limit)
        
        # Get team information for each assignee
        assignee_teams = scoped_df.groupby('Assignee')['Team'].agg(
            lambda values: values.mode().iat[0] if not values.mode().empty else 'Unknown'
        ).to_dict()
        
        # Convert to list of dictionaries
        result = []
        for assignee, row in assignee_stats.iterrows():
            result.append({
                'assignee': assignee,
                'team': assignee_teams.get(assignee, 'Unknown'),
                'bugs_with_rework': int(row['bugs_with_rework']),
                'total_rework_count': int(row['total_rework_count']),
                'avg_rework_per_bug': float(row['avg_rework_per_bug']),
                'avg_cycle_time': float(row['avg_cycle_time'])
            })
        
        return {
            "top_assignees": result,
            "total_assignees_with_rework": len(rework_df['Assignee'].unique()),
            "total_rework_cases": len(rework_df)
        }
    except Exception as e:
        logger.error(f"Error getting rework by assignee: {e}")
        raise HTTPException(status_code=500, detail=str(e))
