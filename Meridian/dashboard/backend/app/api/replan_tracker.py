"""
Replan Tracker API
Provides endpoints for analyzing sprint replanning metrics.
"""
import os
import io
import logging
import threading
from typing import Any, Optional, Tuple
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
import pandas as pd
import numpy as np

from app.models.user import TokenData
from app.dependencies import require_report_access
from app.services.user_service import UserService
from app.services.role_service import RoleService
from app.services.rbac_service import RBACService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/replan-tracker",
    tags=["replan-tracker"],
    dependencies=[Depends(require_report_access)]
)

rbac_user_service = UserService()
rbac_role_service = RoleService()
rbac_service = RBACService(rbac_role_service, rbac_user_service)

# Data file paths resolved from the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
REPLAN_TRACKER_FILE = os.path.join(PROJECT_ROOT, 'output', 'replan_tracker.csv')
JIRA_ISSUES_FILE = os.path.join(PROJECT_ROOT, 'output', 'JIRAIssues.csv')

# In-memory DataFrame cache — avoids re-reading the CSV on every request.
# Invalidated automatically when the file mtime changes (job re-runs).
_replan_cache: Optional[pd.DataFrame] = None
_replan_cache_mtime: float = 0.0
_replan_cache_lock = threading.Lock()


def safe_to_dict(df: pd.DataFrame, orient='records') -> list:
    """Convert DataFrame to dict, replacing NaN with None for JSON serialization."""
    return df.replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict(orient)


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


def _extract_components(value: object) -> list[str]:
    """Parse components text into normalized tokens."""
    raw_text = _normalize_text(value)
    if not raw_text:
        return []

    for separator in ['|', ';']:
        raw_text = raw_text.replace(separator, ',')

    components: list[str] = []
    for token in raw_text.split(','):
        cleaned = _normalize_text(token)
        if cleaned:
            components.append(cleaned)

    return sorted(set(components))


def _build_issue_components_map() -> dict[str, list[str]]:
    """Build issue key -> component tokens map from JIRAIssues.csv."""
    if not os.path.exists(JIRA_ISSUES_FILE):
        return {}

    try:
        jira_df = pd.read_csv(JIRA_ISSUES_FILE, usecols=['Key', 'Components'])
    except Exception:
        return {}

    issue_components: dict[str, list[str]] = {}
    for _, row in jira_df.iterrows():
        issue_key = _normalize_text(row.get('Key'))
        if not issue_key:
            continue
        issue_components[issue_key] = _extract_components(row.get('Components'))

    return issue_components


def _to_int(value: object) -> int:
    """Safely convert any numeric value to int."""
    try:
        if pd.isna(value):
            return 0
        return int(round(float(value)))
    except Exception:
        return 0


def _to_float(value: object, precision: int = 2) -> float:
    """Safely convert any numeric value to float with precision."""
    try:
        if pd.isna(value):
            return 0.0
        return round(float(value), precision)
    except Exception:
        return 0.0


def _get_accessible_replan_scope(current_user: TokenData) -> Tuple[Optional[set[str]], set[str]]:
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


def _apply_replan_rbac(source_df: pd.DataFrame, current_user: TokenData) -> Tuple[pd.DataFrame, set[str]]:
    """Apply RBAC filtering to replan data and return scoped dataframe."""
    accessible_assignees, accessible_teams = _get_accessible_replan_scope(current_user)

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


def _unique_values(series: pd.Series, exclude_unknown: bool = False) -> list[str]:
    """Collect sorted unique normalized values from a series."""
    values: set[str] = set()
    for raw_value in series.dropna().tolist():
        cleaned_value = _normalize_text(raw_value)
        if not cleaned_value:
            continue
        if exclude_unknown and cleaned_value.lower() == "unknown":
            continue
        values.add(cleaned_value)
    return sorted(values)


def _build_issue_type_summary(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Build summary grouped by issue type."""
    if df.empty:
        return []

    summary_df = (
        df.groupby("Issue_Type", dropna=False)
        .agg(
            Issue_Count=("Key", "count"),
            Total_Replans=("Replan_Count", "sum"),
            Avg_Replans_Per_Issue=("Replan_Count", "mean"),
            Max_Replans=("Replan_Count", "max"),
            Avg_Sprints_Per_Issue=("Total_Sprints", "mean"),
            Total_Story_Points=("Story_Points", "sum"),
        )
        .reset_index()
    )

    summary_df["Issue_Type"] = summary_df["Issue_Type"].replace("", "Unknown").fillna("Unknown")
    summary_df["Issue_Count"] = summary_df["Issue_Count"].apply(_to_int)
    summary_df["Total_Replans"] = summary_df["Total_Replans"].apply(_to_int)
    summary_df["Avg_Replans_Per_Issue"] = summary_df["Avg_Replans_Per_Issue"].apply(_to_float)
    summary_df["Max_Replans"] = summary_df["Max_Replans"].apply(_to_int)
    summary_df["Avg_Sprints_Per_Issue"] = summary_df["Avg_Sprints_Per_Issue"].apply(_to_float)
    summary_df["Total_Story_Points"] = summary_df["Total_Story_Points"].apply(_to_int)

    summary_df = summary_df.sort_values("Total_Replans", ascending=False)
    return safe_to_dict(summary_df)


def _build_group_summary(df: pd.DataFrame, group_column: str) -> list[dict[str, Any]]:
    """Build summary grouped by Team or Scrum."""
    if df.empty:
        return []

    grouped_df = (
        df.groupby(group_column, dropna=False)
        .agg(
            Issue_Count=("Key", "count"),
            Total_Replans=("Replan_Count", "sum"),
            Avg_Replans_Per_Issue=("Replan_Count", "mean"),
            Max_Replans=("Replan_Count", "max"),
            Avg_Sprints_Per_Issue=("Total_Sprints", "mean"),
            Total_Story_Points=("Story_Points", "sum"),
            Replanned_Issue_Count=("Replan_Count", lambda values: int((values > 0).sum())),
        )
        .reset_index()
    )

    grouped_df[group_column] = grouped_df[group_column].replace("", "Unknown").fillna("Unknown")
    grouped_df["Issue_Count"] = grouped_df["Issue_Count"].apply(_to_int)
    grouped_df["Total_Replans"] = grouped_df["Total_Replans"].apply(_to_int)
    grouped_df["Avg_Replans_Per_Issue"] = grouped_df["Avg_Replans_Per_Issue"].apply(_to_float)
    grouped_df["Max_Replans"] = grouped_df["Max_Replans"].apply(_to_int)
    grouped_df["Avg_Sprints_Per_Issue"] = grouped_df["Avg_Sprints_Per_Issue"].apply(_to_float)
    grouped_df["Total_Story_Points"] = grouped_df["Total_Story_Points"].apply(_to_int)

    grouped_df["Replan_Rate_%"] = grouped_df.apply(
        lambda row: round(
            (float(row["Replanned_Issue_Count"]) / float(row["Issue_Count"]) * 100.0)
            if float(row["Issue_Count"]) > 0
            else 0.0,
            1,
        ),
        axis=1,
    )

    grouped_df = grouped_df.drop(columns=["Replanned_Issue_Count"], errors="ignore")
    grouped_df = grouped_df.sort_values("Total_Replans", ascending=False)

    return safe_to_dict(grouped_df)


def _build_priority_summary(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Build summary grouped by issue type and priority."""
    if df.empty:
        return []

    priority_df = (
        df.groupby(["Issue_Type", "Priority"], dropna=False)
        .agg(
            Count=("Key", "count"),
            Total_Replans=("Replan_Count", "sum"),
            Avg_Replans=("Replan_Count", "mean"),
        )
        .reset_index()
    )

    priority_df["Issue_Type"] = priority_df["Issue_Type"].replace("", "Unknown").fillna("Unknown")
    priority_df["Priority"] = priority_df["Priority"].replace("", "Unknown").fillna("Unknown")
    priority_df["Count"] = priority_df["Count"].apply(_to_int)
    priority_df["Total_Replans"] = priority_df["Total_Replans"].apply(_to_int)
    priority_df["Avg_Replans"] = priority_df["Avg_Replans"].apply(_to_float)

    priority_df = priority_df.sort_values(["Total_Replans", "Count"], ascending=[False, False])

    return safe_to_dict(priority_df)


def _build_issue_filters(df: pd.DataFrame) -> dict[str, list[str]]:
    """Build scoped filters for issue list endpoint."""
    return {
        "teams": _unique_values(df["Team"], exclude_unknown=True),
        "scrums": _unique_values(df["Scrum"], exclude_unknown=True),
        "issue_types": _unique_values(df["Issue_Type"]),
        "priorities": _unique_values(df["Priority"]),
        "projects": _unique_values(df["Project"]),
        "statuses": _unique_values(df["Current_Status"]),
        "components": sorted({
            component
            for values in df.get("_component_tokens", pd.Series(dtype=object)).tolist()
            for component in (values or [])
            if _normalize_text(component)
        }),
    }


def _apply_issue_filters(
    source_df: pd.DataFrame,
    *,
    team: Optional[str] = None,
    scrum: Optional[str] = None,
    issue_type: Optional[str] = None,
    priority: Optional[str] = None,
    component: Optional[str] = None,
    project: Optional[str] = None,
    min_replans: Optional[int] = None,
    current_status: Optional[str] = None,
) -> pd.DataFrame:
    """Apply issue list filters consistently across list and export endpoints."""
    filtered_df = source_df.copy()

    if team and team != "All":
        filtered_df = filtered_df[filtered_df['Team'] == team]
    if scrum and scrum != "All":
        filtered_df = filtered_df[filtered_df['Scrum'] == scrum]
    if issue_type and issue_type != "All":
        filtered_df = filtered_df[filtered_df['Issue_Type'] == issue_type]
    if priority and priority != "All":
        filtered_df = filtered_df[filtered_df['Priority'] == priority]
    if component and component != "All":
        filtered_df = filtered_df[
            filtered_df['_component_tokens'].apply(lambda values: component in (values or []))
        ]
    if project and project != "All":
        filtered_df = filtered_df[filtered_df['Project'] == project]
    if min_replans is not None:
        filtered_df = filtered_df[filtered_df['Replan_Count'] >= min_replans]
    if current_status and current_status != "All":
        filtered_df = filtered_df[filtered_df['Current_Status'] == current_status]

    return filtered_df.sort_values('Replan_Count', ascending=False)


def _parse_replan_history(issue: pd.Series) -> list[dict[str, Any]]:
    """Parse sprint timeline into structured replan history entries."""
    sprint_timeline = str(issue['Sprint_Timeline']) if pd.notna(issue['Sprint_Timeline']) else ""

    replan_history: list[dict[str, Any]] = []
    if sprint_timeline and sprint_timeline != 'nan':
        timeline_entries = sprint_timeline.split(' → ')

        for idx, entry in enumerate(timeline_entries):
            if '(' not in entry or ')' not in entry:
                continue

            sprint_part = entry[:entry.rfind('(')].strip()
            date_part = entry[entry.rfind('(') + 1:entry.rfind(')')].strip()

            replan_history.append({
                "sequence": idx + 1,
                "sprint": sprint_part,
                "date": date_part,
                "is_replan": idx > 0,
            })

    return replan_history


def _build_issue_replan_details_payload(issue_key: str, issue: pd.Series) -> dict[str, Any]:
    """Build issue replan detail payload shared by detail and export endpoints."""
    epic_key = str(issue['Epic_Key']) if pd.notna(issue.get('Epic_Key')) else 'NA'
    return {
        "issue_key": issue_key,
        "project": str(issue['Project']) if pd.notna(issue['Project']) else None,
        "team": str(issue['Team']) if pd.notna(issue['Team']) else None,
        "scrum": str(issue['Scrum']) if pd.notna(issue['Scrum']) else None,
        "assignee": str(issue['Assignee']) if pd.notna(issue['Assignee']) else None,
        "issue_type": str(issue['Issue_Type']) if pd.notna(issue['Issue_Type']) else None,
        "priority": str(issue['Priority']) if pd.notna(issue['Priority']) else None,
        "story_points": float(issue['Story_Points']) if pd.notna(issue['Story_Points']) else 0,
        "current_sprint": str(issue['Current_Sprint']) if pd.notna(issue['Current_Sprint']) else None,
        "current_status": str(issue['Current_Status']) if pd.notna(issue['Current_Status']) else None,
        "created": str(issue['Created']) if pd.notna(issue['Created']) else None,
        "replan_count": int(issue['Replan_Count']) if pd.notna(issue['Replan_Count']) else 0,
        "total_sprints": int(issue['Total_Sprints']) if pd.notna(issue['Total_Sprints']) else 0,
        "first_sprint": str(issue['First_Sprint']) if pd.notna(issue['First_Sprint']) else None,
        "final_sprint": str(issue['Final_Sprint']) if pd.notna(issue['Final_Sprint']) else None,
        "replan_history": _parse_replan_history(issue),
        "description": str(issue['Description']) if pd.notna(issue.get('Description')) else None,
        "epic_key": epic_key if epic_key != 'NA' else None,
        "epic_summary": str(issue['Epic_Summary']) if pd.notna(issue.get('Epic_Summary')) and str(issue.get('Epic_Summary', '')) else None,
    }


def _build_replan_export_rows(filtered_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Expand filtered issues into CSV-ready rows with one row per history entry."""
    export_rows: list[dict[str, Any]] = []

    for _, issue in filtered_df.iterrows():
        details = _build_issue_replan_details_payload(str(issue['Key']), issue)
        history_entries = details['replan_history'] or [
            {
                'sequence': None,
                'sprint': '',
                'date': '',
                'is_replan': False,
            }
        ]

        for history_entry in history_entries:
            export_rows.append({
                'Issue_Key': details['issue_key'],
                'Project': details['project'] or '',
                'Team': details['team'] or '',
                'Scrum': details['scrum'] or '',
                'Assignee': details['assignee'] or '',
                'Issue_Type': details['issue_type'] or '',
                'Priority': details['priority'] or '',
                'Story_Points': details['story_points'],
                'Current_Status': details['current_status'] or '',
                'Created': details['created'] or '',
                'Replan_Count': details['replan_count'],
                'Total_Sprints': details['total_sprints'],
                'First_Sprint': details['first_sprint'] or '',
                'Final_Sprint': details['final_sprint'] or '',
                'Current_Sprint': details['current_sprint'] or '',
                'Description': details['description'] or '',
                'Epic_Key': details['epic_key'] or 'NA',
                'Epic_Summary': details['epic_summary'] or '',
                'Replan_Sequence': history_entry['sequence'] if history_entry['sequence'] is not None else '',
                'Replan_Label': 'Initial Plan' if not history_entry['is_replan'] else f"Replan {history_entry['sequence'] - 1}",
                'Replan_Date': history_entry['date'],
                'Sprint': history_entry['sprint'],
                'Is_Replan': 'Yes' if history_entry['is_replan'] else 'No',
            })

    return export_rows


def _build_epic_info_map() -> dict[str, dict[str, str]]:
    """Build a map from issue key -> {epic_key, epic_summary, description}.

    Resolution logic:
    - If the issue is an Epic → epic_key = issue key itself.
    - Otherwise traverse Parent up to 2 levels to find an Epic parent.
    - If no Epic found → epic_key = "NA", epic_summary = "".
    """
    if not os.path.exists(JIRA_ISSUES_FILE):
        return {}

    try:
        jira_df = pd.read_csv(JIRA_ISSUES_FILE, usecols=['Key', 'Issue Type', 'Parent', 'Summary'])
    except Exception:
        return {}

    jira_df['Key'] = jira_df['Key'].fillna('').astype(str).str.strip()
    jira_df['Issue Type'] = jira_df['Issue Type'].fillna('').astype(str).str.strip().str.lower()
    jira_df['Parent'] = jira_df['Parent'].fillna('').astype(str).str.strip()
    jira_df['Summary'] = jira_df['Summary'].fillna('').astype(str).str.strip()

    # Build lookup dicts
    type_map: dict[str, str] = {}        # key -> lowercase issue type
    parent_map: dict[str, str] = {}      # key -> parent key
    summary_map: dict[str, str] = {}     # key -> summary

    for _, row in jira_df.iterrows():
        k = row['Key']
        if not k:
            continue
        type_map[k] = row['Issue Type']
        parent_map[k] = row['Parent']
        summary_map[k] = row['Summary']

    def resolve_epic(key: str) -> tuple[str, str]:
        """Return (epic_key, epic_summary) for a given issue key."""
        if not key or key not in type_map:
            return 'NA', ''
        issue_type = type_map[key]
        if issue_type == 'epic':
            return key, summary_map.get(key, '')
        # Level 1: direct parent
        parent = parent_map.get(key, '')
        if parent and parent in type_map:
            if type_map[parent] == 'epic':
                return parent, summary_map.get(parent, '')
            # Level 2: grandparent
            grandparent = parent_map.get(parent, '')
            if grandparent and grandparent in type_map and type_map[grandparent] == 'epic':
                return grandparent, summary_map.get(grandparent, '')
        return 'NA', ''

    info_map: dict[str, dict[str, str]] = {}
    for k in type_map:
        epic_key, epic_summary = resolve_epic(k)
        info_map[k] = {
            'epic_key': epic_key,
            'epic_summary': epic_summary,
            'description': summary_map.get(k, ''),
        }

    return info_map


def load_replan_data() -> pd.DataFrame:
    """Load replan tracker data from CSV with in-memory mtime caching.

    The DataFrame is read from disk only when the file has changed since the
    last load (i.e. after the scheduled job re-runs).  All subsequent requests
    within the same file-version are served from memory.
    """
    global _replan_cache, _replan_cache_mtime

    if not os.path.exists(REPLAN_TRACKER_FILE):
        logger.error(f"Replan tracker file not found: {REPLAN_TRACKER_FILE}")
        raise HTTPException(status_code=404, detail="Replan tracker data not found")

    try:
        current_mtime = os.path.getmtime(REPLAN_TRACKER_FILE)
    except OSError:
        current_mtime = 0.0

    # Fast path: return cached DataFrame if file hasn't changed
    if _replan_cache is not None and current_mtime == _replan_cache_mtime:
        return _replan_cache

    # Serialize expensive cold-load work so parallel requests don't all parse CSV.
    with _replan_cache_lock:
        # Re-check after waiting for lock; another request may have loaded cache.
        if _replan_cache is not None and current_mtime == _replan_cache_mtime:
            return _replan_cache

        logger.info("Replan tracker CSV changed or first load — reading from disk")

        try:
            df = pd.read_csv(REPLAN_TRACKER_FILE)

            text_columns_defaults = {
                "Key": "",
                "Project": "Unknown",
                "Team": "Unknown",
                "Scrum": "Unknown",
                "Assignee": "Unknown",
                "Issue_Type": "Unknown",
                "Priority": "Unknown",
                "Component": "Unknown",
                "Current_Sprint": "Unknown",
                "Current_Status": "Unknown",
                "Created": "",
                "First_Sprint": "",
                "Final_Sprint": "",
                "Sprint_Timeline": "",
            }

            for column, default_value in text_columns_defaults.items():
                if column not in df.columns:
                    df[column] = default_value
                df[column] = df[column].apply(_normalize_text)
                if default_value:
                    df[column] = df[column].replace("", default_value)

            # Convert numeric columns
            numeric_cols = ['Story_Points', 'Replan_Count', 'Total_Sprints']
            for col in numeric_cols:
                if col not in df.columns:
                    df[col] = 0
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            # Epic / Description enrichment.
            # If the scheduled job has already written these columns into the CSV
            # (preferred path), use them directly — no need to touch JIRAIssues.csv.
            # Fall back to on-the-fly computation only if the columns are absent
            # (e.g. old CSV written by a pre-enrichment job version).
            if 'Epic_Key' not in df.columns or 'Description' not in df.columns:
                logger.info("Epic columns missing from CSV — computing from JIRAIssues.csv (fallback)")
                epic_info = _build_epic_info_map()
                df['Epic_Key'] = df['Key'].map(lambda k: epic_info.get(k, {}).get('epic_key', 'NA'))
                df['Epic_Summary'] = df['Key'].map(lambda k: epic_info.get(k, {}).get('epic_summary', ''))
                df['Description'] = df['Key'].map(lambda k: epic_info.get(k, {}).get('description', ''))
            else:
                # Normalise nulls that may appear in the CSV
                df['Epic_Key'] = df['Epic_Key'].fillna('NA').astype(str).str.strip()
                df['Epic_Summary'] = df['Epic_Summary'].fillna('').astype(str).str.strip()
                df['Description'] = df['Description'].fillna('').astype(str).str.strip()

            # Avoid loading JIRAIssues component map unless component tokens are
            # actually missing after parsing CSV component text.
            if 'Component' in df.columns:
                df['_component_tokens'] = df['Component'].apply(_extract_components)
                missing_components_mask = df['_component_tokens'].apply(lambda values: len(values) == 0)
                if missing_components_mask.any():
                    issue_components_map = _build_issue_components_map()
                    if issue_components_map:
                        fallback_tokens = df.loc[missing_components_mask, 'Key'].map(
                            lambda issue_key: issue_components_map.get(_normalize_text(issue_key), [])
                        )
                        df.loc[missing_components_mask, '_component_tokens'] = fallback_tokens
            else:
                issue_components_map = _build_issue_components_map()
                df['_component_tokens'] = df['Key'].map(
                    lambda issue_key: issue_components_map.get(_normalize_text(issue_key), [])
                )

            df['Component'] = df['_component_tokens'].apply(
                lambda values: ', '.join(values) if values else 'Unknown'
            )

            # Store in module-level cache
            _replan_cache = df
            _replan_cache_mtime = current_mtime
            logger.info(f"Replan tracker cache updated — {len(df)} rows")
            return df

        except Exception as e:
            logger.error(f"Error loading replan tracker data: {e}")
            raise HTTPException(status_code=500, detail="Error loading replan tracker data")


@router.get("/summary")
def get_replan_summary(
    current_user: TokenData = Depends(require_report_access),
):
    """Get replan summary statistics."""
    try:
        scoped_df, _ = _apply_replan_rbac(load_replan_data(), current_user)
        response_df = scoped_df.drop(columns=["_assignee_norm", "_team_clean", "_component_tokens"], errors="ignore")
        
        return {
            "by_issue_type": _build_issue_type_summary(response_df),
            "by_team": _build_group_summary(response_df, "Team"),
            "by_scrum": _build_group_summary(response_df, "Scrum"),
            "by_priority": _build_priority_summary(response_df),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting replan summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/issues")
def get_replan_issues(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    team: Optional[str] = None,
    scrum: Optional[str] = None,
    issue_type: Optional[str] = None,
    priority: Optional[str] = None,
    component: Optional[str] = None,
    project: Optional[str] = None,
    min_replans: Optional[int] = None,
    current_status: Optional[str] = None,
    current_user: TokenData = Depends(require_report_access),
):
    """Get filtered list of issues with replan data."""
    try:
        scoped_df, _ = _apply_replan_rbac(load_replan_data(), current_user)
        response_df = scoped_df.drop(columns=["_assignee_norm", "_team_clean"], errors="ignore")
        filtered_df = _apply_issue_filters(
            response_df,
            team=team,
            scrum=scrum,
            issue_type=issue_type,
            priority=priority,
            component=component,
            project=project,
            min_replans=min_replans,
            current_status=current_status,
        )
        
        # Pagination
        total_count = len(filtered_df)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        issues_page = filtered_df.iloc[start_idx:end_idx].drop(columns=["_component_tokens"], errors="ignore")
        
        filters = _build_issue_filters(response_df)
        
        return {
            "issues": safe_to_dict(issues_page),
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            },
            "filters": filters
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting replan issues: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/issues/export/csv")
def export_replan_issues_csv(
    team: Optional[str] = None,
    scrum: Optional[str] = None,
    issue_type: Optional[str] = None,
    priority: Optional[str] = None,
    component: Optional[str] = None,
    project: Optional[str] = None,
    min_replans: Optional[int] = None,
    current_status: Optional[str] = None,
    current_user: TokenData = Depends(require_report_access),
):
    """Export filtered replan issues as CSV with one row per issue/history entry."""
    try:
        scoped_df, _ = _apply_replan_rbac(load_replan_data(), current_user)
        response_df = scoped_df.drop(columns=["_assignee_norm", "_team_clean"], errors="ignore")
        filtered_df = _apply_issue_filters(
            response_df,
            team=team,
            scrum=scrum,
            issue_type=issue_type,
            priority=priority,
            component=component,
            project=project,
            min_replans=min_replans,
            current_status=current_status,
        )

        export_rows = _build_replan_export_rows(filtered_df)
        export_df = pd.DataFrame(export_rows)
        if export_df.empty:
            export_df = pd.DataFrame(columns=[
                'Issue_Key', 'Project', 'Team', 'Scrum', 'Assignee', 'Issue_Type', 'Priority',
                'Story_Points', 'Current_Status', 'Created', 'Replan_Count', 'Total_Sprints',
                'First_Sprint', 'Final_Sprint', 'Current_Sprint', 'Description', 'Epic_Key',
                'Epic_Summary', 'Replan_Sequence', 'Replan_Label', 'Replan_Date', 'Sprint', 'Is_Replan'
            ])

        csv_buffer = io.StringIO()
        export_df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        return StreamingResponse(
            csv_buffer,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=replan_tracker_all_issues.csv"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting replan issues CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/high-replans")
def get_high_replan_issues(
    limit: int = Query(10, ge=1, le=100),
    current_user: TokenData = Depends(require_report_access),
):
    """Get issues with highest replan counts."""
    try:
        scoped_df, _ = _apply_replan_rbac(load_replan_data(), current_user)
        response_df = scoped_df.drop(columns=["_assignee_norm", "_team_clean", "_component_tokens"], errors="ignore")
        filtered_df = response_df[response_df['Replan_Count'] > 0].copy()
        filtered_df = filtered_df.sort_values('Replan_Count', ascending=False)
        
        top_issues = filtered_df.head(limit)
        
        return {
            "high_replan_issues": safe_to_dict(top_issues),
            "count": len(top_issues)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting high replan issues: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_replan_statistics(
    current_user: TokenData = Depends(require_report_access),
):
    """Get overall replan statistics."""
    try:
        scoped_df, _ = _apply_replan_rbac(load_replan_data(), current_user)
        response_df = scoped_df.drop(columns=["_assignee_norm", "_team_clean", "_component_tokens"], errors="ignore")

        if response_df.empty:
            return {
                "total_issues": 0,
                "total_replans": 0,
                "issues_with_replans": 0,
                "issues_without_replans": 0,
                "replan_rate_percent": 0.0,
                "avg_replans_per_issue": 0.0,
                "avg_replans_when_replanned": 0.0,
                "max_replans": 0,
                "median_replans": 0.0,
                "avg_sprints_per_issue": 0.0,
                "total_story_points": 0,
                "by_issue_type": {},
            }
        
        total_issues = len(response_df)
        total_replans = response_df['Replan_Count'].sum()
        replanned_df = response_df[response_df['Replan_Count'] > 0]
        issues_with_replans = len(replanned_df)
        
        stats = {
            "total_issues": int(total_issues),
            "total_replans": _to_int(total_replans),
            "issues_with_replans": int(issues_with_replans),
            "issues_without_replans": int(total_issues - issues_with_replans),
            "replan_rate_percent": round((issues_with_replans / total_issues * 100) if total_issues > 0 else 0, 1),
            "avg_replans_per_issue": _to_float(response_df['Replan_Count'].mean()),
            "avg_replans_when_replanned": _to_float(replanned_df['Replan_Count'].mean()) if issues_with_replans > 0 else 0.0,
            "max_replans": _to_int(response_df['Replan_Count'].max()),
            "median_replans": _to_float(response_df['Replan_Count'].median()),
            "avg_sprints_per_issue": _to_float(response_df['Total_Sprints'].mean()),
            "total_story_points": _to_int(response_df['Story_Points'].sum())
        }
        
        # Issue type breakdown
        issue_type_stats = response_df.groupby('Issue_Type').agg({
            'Key': 'count',
            'Replan_Count': 'sum'
        }).to_dict('index')
        
        stats['by_issue_type'] = {
            issue_type: {
                "count": _to_int(data['Key']),
                "total_replans": _to_int(data['Replan_Count'])
            }
            for issue_type, data in issue_type_stats.items()
        }
        
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting replan statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trends-by-team")
def get_replan_trends_by_team(
    current_user: TokenData = Depends(require_report_access),
):
    """Get replan trends by team for visualization."""
    try:
        scoped_df, _ = _apply_replan_rbac(load_replan_data(), current_user)
        response_df = scoped_df.drop(columns=["_assignee_norm", "_team_clean", "_component_tokens"], errors="ignore")

        by_team = _build_group_summary(response_df, "Team")

        if not by_team:
            return {"teams": []}

        return {
            "teams": by_team
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting replan trends by team: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/issue/{issue_key}/replan-details")
def get_issue_replan_details(
    issue_key: str,
    current_user: TokenData = Depends(require_report_access),
):
    """Get detailed replan history for a specific issue."""
    try:
        scoped_df, _ = _apply_replan_rbac(load_replan_data(), current_user)
        response_df = scoped_df.drop(columns=["_assignee_norm", "_team_clean", "_component_tokens"], errors="ignore")
        
        # Find the issue
        issue_data = response_df[response_df['Key'] == issue_key]
        
        if issue_data.empty:
            raise HTTPException(status_code=404, detail=f"Issue {issue_key} not found")
        
        issue = issue_data.iloc[0]

        return _build_issue_replan_details_payload(issue_key, issue)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting replan details for {issue_key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
