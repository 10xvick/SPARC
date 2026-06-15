"""
Assignee Attributable Delay Report API
Provides endpoints for assignee/team/scrum level delay analytics.
"""

from pathlib import Path
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends

from app.models.user import TokenData
from app.dependencies import require_report_access
from app.services.user_service import UserService
from app.services.role_service import RoleService
from app.services.rbac_service import RBACService


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/assignee-delay",
    tags=["assignee-delay"],
    dependencies=[Depends(require_report_access)]
)

rbac_user_service = UserService()
rbac_role_service = RoleService()
rbac_service = RBACService(rbac_role_service, rbac_user_service)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
CONFIG_DIR = PROJECT_ROOT / "config"

ASSIGNEE_DELAY_FILE = OUTPUT_DIR / "assignee_attributable_delay.csv"
ASSIGNEE_DELAY_CACHE_DIR = OUTPUT_DIR / "AssigneeDelayCache"
RESOURCES_FILE = CONFIG_DIR / "Resources.csv"
JIRA_ISSUES_FILE = OUTPUT_DIR / "JIRAIssues.csv"
JIRA_HISTORY_FILE = OUTPUT_DIR / "JIRAIssues_History.csv"

# In-memory mtime cache for assignee delay data
_assignee_delay_cache: Optional[pd.DataFrame] = None
_assignee_delay_cache_mtime: float = 0.0


def _load_sapid_map() -> Dict[str, Dict[str, str]]:
    """Return normalized JIRA/resource name -> {sapid, display_name} from Resources.csv."""
    sapid_map: Dict[str, Dict[str, str]] = {}
    if not RESOURCES_FILE.exists():
        return sapid_map
    try:
        resources_df = pd.read_csv(RESOURCES_FILE)
    except Exception:
        return sapid_map
    for _, row in resources_df.iterrows():
        sapid = _normalize_text(row.get("SAPID"))
        if not sapid:
            continue
        display_name = _normalize_text(row.get("Name"))
        for name_col in ("JIRA Name", "Name"):
            candidate = _normalize_text(row.get(name_col))
            if not candidate:
                continue
            key = candidate.lower().strip()
            if key and key not in sapid_map:
                sapid_map[key] = {"sapid": sapid, "display_name": display_name or candidate}
    return sapid_map

DONE_STATUSES = {
    "done",
    "closed",
    "resolved",
    "removed",
    "completed",
}

IN_PROGRESS_STATUSES = {
    "in progress",
    "approved",
    "code review",
    "review",
    "testing",
    "ready for qa",
    "in test",
}

FIRST_ACTIVE_STATUSES = DONE_STATUSES | IN_PROGRESS_STATUSES
EXCLUDED_ISSUE_TYPES = {"epic"}
EXCLUDED_STATUSES = {"deferred", "defferred"}
MIN_DELAY_THRESHOLD_DAYS = 1.0


def _get_accessible_assignee_scope(current_user: TokenData) -> Tuple[Optional[set[str]], set[str]]:
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


def _apply_assignee_delay_rbac(
    enriched_df: pd.DataFrame,
    current_user: TokenData,
) -> Tuple[pd.DataFrame, set[str]]:
    """Apply RBAC filtering to assignee delay data and return scoped dataframe."""
    accessible_assignees, accessible_teams = _get_accessible_assignee_scope(current_user)

    scoped_df = enriched_df.copy()
    if accessible_assignees is None:
        return scoped_df, accessible_teams

    scoped_df["_assignee_norm"] = scoped_df["Assignee"].apply(_normalize_person_name)
    scoped_df["_team_clean"] = scoped_df["Team"].fillna("").astype(str).str.strip()

    scoped_df = scoped_df[
        scoped_df["_assignee_norm"].isin(accessible_assignees)
        | scoped_df["_team_clean"].isin(accessible_teams)
    ].copy()

    return scoped_df, accessible_teams


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
    """Parse components field into normalized tokens."""
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


def _load_assignee_components_map() -> Dict[str, list[str]]:
    """Build normalized assignee -> unique component tokens map from JIRAIssues.csv."""
    assignee_components: Dict[str, set[str]] = {}
    if not JIRA_ISSUES_FILE.exists():
        return {}

    try:
        issues_df = pd.read_csv(JIRA_ISSUES_FILE, usecols=["Assignee", "Components"])
    except Exception:
        return {}

    for _, row in issues_df.iterrows():
        assignee = _normalize_person_name(row.get("Assignee"))
        if not assignee:
            continue

        components = _extract_components(row.get("Components"))
        if not components:
            continue

        if assignee not in assignee_components:
            assignee_components[assignee] = set()
        assignee_components[assignee].update(components)

    return {
        assignee: sorted(values)
        for assignee, values in assignee_components.items()
    }


def _safe_number(value: object) -> float:
    """Safely convert any value to a float."""
    try:
        number = float(value)
        if pd.isna(number):
            return 0.0
        return number
    except Exception:
        return 0.0


def _load_jira_issues_data() -> pd.DataFrame:
    """Load issue-level Jira data used to compute assignee attribution details."""
    if not JIRA_ISSUES_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="JIRA issue data not found. Run jira fetch before opening assignee issue details.",
        )

    try:
        issues_df = pd.read_csv(JIRA_ISSUES_FILE)
    except Exception as exc:
        logger.error("Error loading JIRA issues data: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load JIRA issue data")

    if "Issue Type" not in issues_df.columns and "Issue_Type" in issues_df.columns:
        issues_df["Issue Type"] = issues_df["Issue_Type"]

    required_columns = [
        "Key",
        "Issue Type",
        "Summary",
        "Status",
        "Assignee",
        "Created",
        "Sprint.endDate",
        "Team",
        "Sprint",
    ]
    for column in required_columns:
        if column not in issues_df.columns:
            issues_df[column] = ""

    issues_df["Key"] = issues_df["Key"].fillna("").astype(str).str.strip()
    issues_df["Status"] = issues_df["Status"].fillna("").astype(str).str.strip()
    issues_df["Assignee"] = (
        issues_df["Assignee"].fillna("").astype(str).str.strip().replace("", "Unassigned")
    )
    issues_df["_created_dt"] = pd.to_datetime(issues_df["Created"], errors="coerce", utc=True)
    issues_df["_sprint_end_dt"] = pd.to_datetime(issues_df["Sprint.endDate"], errors="coerce", utc=True)
    issues_df["_status_norm"] = issues_df["Status"].str.lower().str.strip()
    issues_df["_issue_type_norm"] = issues_df["Issue Type"].fillna("").astype(str).str.strip().str.lower()
    issues_df["_is_done"] = issues_df["_status_norm"].isin(DONE_STATUSES)

    issues_df = issues_df[issues_df["Key"] != ""].copy()
    return issues_df


def _load_jira_history_data() -> pd.DataFrame:
    """Load Jira history data used to derive transitions and assignment windows."""
    if not JIRA_HISTORY_FILE.exists():
        return pd.DataFrame(columns=["Key", "Field", "FromValue", "ToValue", "ChangeDate"])

    try:
        history_df = pd.read_csv(JIRA_HISTORY_FILE)
    except Exception as exc:
        logger.error("Error loading JIRA history data: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load JIRA history data")

    required_columns = ["Key", "Field", "FromValue", "ToValue", "ChangeDate"]
    for column in required_columns:
        if column not in history_df.columns:
            history_df[column] = ""

    history_df["Key"] = history_df["Key"].fillna("").astype(str).str.strip()
    history_df["Field"] = history_df["Field"].fillna("").astype(str).str.strip()
    history_df["FromValue"] = history_df["FromValue"].fillna("").astype(str).str.strip()
    history_df["ToValue"] = history_df["ToValue"].fillna("").astype(str).str.strip()
    history_df["_field_norm"] = history_df["Field"].str.lower().str.strip()
    history_df["_from_norm"] = history_df["FromValue"].str.lower().str.strip()
    history_df["_to_norm"] = history_df["ToValue"].str.lower().str.strip()
    history_df["ChangeDate"] = pd.to_datetime(history_df["ChangeDate"], errors="coerce", utc=True)

    history_df = history_df[(history_df["Key"] != "") & history_df["ChangeDate"].notna()].copy()
    return history_df


def _build_first_transition_maps(history_df: pd.DataFrame) -> Tuple[Dict[str, pd.Timestamp], Dict[str, pd.Timestamp]]:
    """Build first done and first active transition maps for each issue key."""
    if history_df.empty:
        return {}, {}

    status_history = history_df[history_df["_field_norm"] == "status"].copy()

    first_done_map: Dict[str, pd.Timestamp] = {}
    done_rows = status_history[status_history["_to_norm"].isin(DONE_STATUSES)].copy()
    if not done_rows.empty:
        done_rows = done_rows.sort_values(["Key", "ChangeDate"])
        first_done = done_rows.groupby("Key", as_index=False).first()
        first_done_map = {
            _normalize_text(row["Key"]): row["ChangeDate"]
            for _, row in first_done.iterrows()
            if _normalize_text(row["Key"])
        }

    first_active_map: Dict[str, pd.Timestamp] = {}
    active_rows = status_history[status_history["_to_norm"].isin(FIRST_ACTIVE_STATUSES)].copy()
    if not active_rows.empty:
        active_rows = active_rows.sort_values(["Key", "ChangeDate"])
        first_active = active_rows.groupby("Key", as_index=False).first()
        first_active_map = {
            _normalize_text(row["Key"]): row["ChangeDate"]
            for _, row in first_active.iterrows()
            if _normalize_text(row["Key"])
        }

    return first_done_map, first_active_map


def _build_assignee_transition_map(history_df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
    """Build assignment transition events by issue key sorted by change timestamp."""
    if history_df.empty:
        return {}

    assignment_rows = history_df[history_df["_field_norm"] == "assignee"].copy()
    if assignment_rows.empty:
        return {}

    assignment_rows = assignment_rows.sort_values(["Key", "ChangeDate"])
    transition_map: Dict[str, List[Dict[str, Any]]] = {}

    for issue_key, issue_history in assignment_rows.groupby("Key"):
        clean_key = _normalize_text(issue_key)
        if not clean_key:
            continue

        events: List[Dict[str, Any]] = []
        for _, row in issue_history.iterrows():
            changed_at = pd.to_datetime(row.get("ChangeDate"), errors="coerce", utc=True)
            if changed_at is None or pd.isna(changed_at):
                continue

            events.append(
                {
                    "changed_at": changed_at,
                    "from_assignee": _normalize_text(row.get("FromValue"),) or "Unassigned",
                    "to_assignee": _normalize_text(row.get("ToValue"),) or "Unassigned",
                }
            )

        if events:
            transition_map[clean_key] = events

    return transition_map


def _segment_assignee_attribution(
    issue_assignee: str,
    created_dt: pd.Timestamp,
    effective_end_dt: pd.Timestamp,
    delay_baseline_dt: pd.Timestamp,
    assignee_events: List[Dict[str, Any]],
) -> Dict[str, float]:
    """Calculate attributable delay overlap per assignee for a single issue."""
    attribution: Dict[str, float] = {}

    if (
        delay_baseline_dt is None
        or pd.isna(delay_baseline_dt)
        or effective_end_dt is None
        or pd.isna(effective_end_dt)
        or effective_end_dt <= delay_baseline_dt
    ):
        return attribution

    raw_delay_days = max(0.0, (effective_end_dt - delay_baseline_dt).total_seconds() / 86400)
    if raw_delay_days < MIN_DELAY_THRESHOLD_DAYS:
        return attribution

    start_ts = pd.to_datetime(created_dt, errors="coerce", utc=True)
    if start_ts is None or pd.isna(start_ts):
        if assignee_events:
            start_ts = assignee_events[0]["changed_at"]
        else:
            start_ts = effective_end_dt

    if start_ts > effective_end_dt:
        start_ts = effective_end_dt

    current_assignee = _normalize_text(issue_assignee) or "Unassigned"
    if assignee_events:
        first_from = _normalize_text(assignee_events[0].get("from_assignee"))
        if first_from:
            current_assignee = first_from

    def add_segment(assignee_name: str, segment_start: pd.Timestamp, segment_end: pd.Timestamp):
        if segment_start is None or segment_end is None or pd.isna(segment_start) or pd.isna(segment_end):
            return
        if segment_end <= segment_start:
            return

        overlap_start = max(segment_start, delay_baseline_dt)
        overlap_end = min(segment_end, effective_end_dt)
        if overlap_end <= overlap_start:
            return

        overlap_days = max(0.0, (overlap_end - overlap_start).total_seconds() / 86400)
        if overlap_days <= 0:
            return

        clean_assignee = _normalize_text(assignee_name) or "Unassigned"
        attribution[clean_assignee] = attribution.get(clean_assignee, 0.0) + overlap_days

    period_start = start_ts

    for event in assignee_events:
        changed_at = event.get("changed_at")
        if changed_at is None or pd.isna(changed_at):
            continue

        if changed_at < period_start:
            next_assignee = _normalize_text(event.get("to_assignee"))
            if next_assignee:
                current_assignee = next_assignee
            continue

        event_boundary = min(changed_at, effective_end_dt)
        add_segment(current_assignee, period_start, event_boundary)

        period_start = event_boundary
        next_assignee = _normalize_text(event.get("to_assignee"))
        if next_assignee:
            current_assignee = next_assignee

        if period_start >= effective_end_dt:
            break

    add_segment(current_assignee, period_start, effective_end_dt)
    return attribution


def _load_assignee_delay_data() -> pd.DataFrame:
    """Load assignee attributable delay data from CSV with in-memory mtime caching."""
    global _assignee_delay_cache, _assignee_delay_cache_mtime

    if not ASSIGNEE_DELAY_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Assignee attributable delay data not found. Run assignee_attributable_delay job first.",
        )

    try:
        current_mtime = os.path.getmtime(ASSIGNEE_DELAY_FILE)
    except OSError:
        current_mtime = 0.0

    if _assignee_delay_cache is not None and current_mtime == _assignee_delay_cache_mtime:
        return _assignee_delay_cache

    logger.info("Assignee delay CSV changed or first load — reading from disk")

    try:
        df = pd.read_csv(ASSIGNEE_DELAY_FILE)
    except Exception as exc:
        logger.error("Error loading assignee delay file: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load assignee delay data")

    required_columns = [
        "Assignee",
        "Total_Attributable_Delay_Days",
        "Issues_With_Delay",
        "Avg_Delay_Per_Issue_Days",
    ]
    for column in required_columns:
        if column not in df.columns:
            df[column] = 0 if column != "Assignee" else "Unknown"

    df["Assignee"] = df["Assignee"].apply(lambda value: _normalize_text(value) or "Unknown")
    df["Total_Attributable_Delay_Days"] = pd.to_numeric(
        df["Total_Attributable_Delay_Days"], errors="coerce"
    ).fillna(0.0)
    df["Issues_With_Delay"] = pd.to_numeric(df["Issues_With_Delay"], errors="coerce").fillna(0).astype(int)
    df["Avg_Delay_Per_Issue_Days"] = pd.to_numeric(
        df["Avg_Delay_Per_Issue_Days"], errors="coerce"
    ).fillna(0.0)

    _assignee_delay_cache = df
    _assignee_delay_cache_mtime = current_mtime
    return df


def _load_resources_mapping() -> Tuple[Dict[str, str], Dict[str, str]]:
    """Build assignee to team/scrum mapping using Resources.csv names and JIRA names."""
    team_map: Dict[str, str] = {}
    scrum_map: Dict[str, str] = {}

    if not RESOURCES_FILE.exists():
        logger.warning("Resources file not found: %s", RESOURCES_FILE)
        return team_map, scrum_map

    try:
        resources_df = pd.read_csv(RESOURCES_FILE)
    except Exception as exc:
        logger.warning("Unable to load resources mapping: %s", exc)
        return team_map, scrum_map

    for _, row in resources_df.iterrows():
        team = _normalize_text(row.get("Team")) or "Unknown"
        scrum = _normalize_text(row.get("Scrum")) or "Unknown"

        for name_col in ["Name", "JIRA Name"]:
            candidate = _normalize_text(row.get(name_col))
            if not candidate:
                continue
            normalized = candidate.lower()
            if normalized not in team_map:
                team_map[normalized] = team
                scrum_map[normalized] = scrum

    return team_map, scrum_map


def _enrich_with_org_context(df: pd.DataFrame) -> pd.DataFrame:
    """Attach Team and Scrum to assignee delay rows."""
    team_map, scrum_map = _load_resources_mapping()
    assignee_components_map = _load_assignee_components_map()

    enriched_df = df.copy()
    normalized_assignee = enriched_df["Assignee"].astype(str).str.strip().str.lower()

    enriched_df["Team"] = normalized_assignee.map(team_map).fillna("Unknown")
    enriched_df["Scrum"] = normalized_assignee.map(scrum_map).fillna("Unknown")
    enriched_df["_component_tokens"] = normalized_assignee.map(assignee_components_map).apply(
        lambda values: values if isinstance(values, list) else []
    )
    enriched_df["Components"] = enriched_df["_component_tokens"].apply(
        lambda values: ", ".join(values) if values else "Unknown"
    )

    enriched_df["Total_Attributable_Delay_Days"] = enriched_df["Total_Attributable_Delay_Days"].round(2)
    enriched_df["Avg_Delay_Per_Issue_Days"] = enriched_df["Avg_Delay_Per_Issue_Days"].round(2)

    return enriched_df


def _build_group_summary(df: pd.DataFrame, group_column: str) -> list:
    """Build grouped summary rows for team/scrum analytics."""
    if df.empty:
        return []

    grouped_df = (
        df.groupby(group_column, dropna=False)
        .agg(
            Assignee_Count=("Assignee", "nunique"),
            Total_Attributable_Delay_Days=("Total_Attributable_Delay_Days", "sum"),
            Issues_With_Delay=("Issues_With_Delay", "sum"),
        )
        .reset_index()
    )

    grouped_df["Avg_Delay_Per_Issue_Days"] = grouped_df.apply(
        lambda row: (
            float(row["Total_Attributable_Delay_Days"]) / float(row["Issues_With_Delay"])
            if float(row["Issues_With_Delay"]) > 0
            else 0.0
        ),
        axis=1,
    )

    total_delay = float(grouped_df["Total_Attributable_Delay_Days"].sum())
    grouped_df["Delay_Share_Percent"] = grouped_df["Total_Attributable_Delay_Days"].apply(
        lambda value: round((float(value) / total_delay * 100.0) if total_delay > 0 else 0.0, 2)
    )

    grouped_df["Total_Attributable_Delay_Days"] = grouped_df["Total_Attributable_Delay_Days"].round(2)
    grouped_df["Avg_Delay_Per_Issue_Days"] = grouped_df["Avg_Delay_Per_Issue_Days"].round(2)
    grouped_df = grouped_df.sort_values("Total_Attributable_Delay_Days", ascending=False)

    return grouped_df.to_dict("records")


@router.get("/summary")
def get_assignee_delay_summary(
    top_n: int = Query(15, ge=1, le=100),
    current_user: TokenData = Depends(require_report_access),
):
    """Get summary statistics and cut-based aggregates for assignee delay analytics."""
    df = _load_assignee_delay_data()
    enriched_df = _enrich_with_org_context(df)
    enriched_df, accessible_teams = _apply_assignee_delay_rbac(enriched_df, current_user)
    response_df = enriched_df.drop(columns=["_assignee_norm", "_team_clean"], errors="ignore")

    total_delay = float(response_df["Total_Attributable_Delay_Days"].sum())
    total_issues = int(response_df["Issues_With_Delay"].sum())
    total_assignees = int(len(response_df))

    avg_delay_per_issue = (total_delay / total_issues) if total_issues > 0 else 0.0
    avg_delay_per_assignee = (total_delay / total_assignees) if total_assignees > 0 else 0.0

    mapped_assignees = int((response_df["Team"] != "Unknown").sum())
    unmapped_assignees = total_assignees - mapped_assignees

    top_assignees_df = (
        response_df
        .sort_values("Total_Attributable_Delay_Days", ascending=False)
        .head(top_n)
        .drop(columns=["_component_tokens"], errors="ignore")
    )

    teams_from_data = sorted(response_df["Team"].dropna().astype(str).unique().tolist())
    if current_user.role in ["Admin", "API User"]:
        team_filters = teams_from_data
    else:
        team_filters = sorted(set(teams_from_data) | accessible_teams)

    data_timestamp = None
    try:
        data_timestamp = pd.Timestamp(ASSIGNEE_DELAY_FILE.stat().st_mtime, unit="s", tz="UTC").isoformat()
    except Exception:
        data_timestamp = None

    return {
        "statistics": {
            "total_assignees": total_assignees,
            "total_delay_days": round(total_delay, 2),
            "total_issues_with_delay": total_issues,
            "avg_delay_per_issue_days": round(avg_delay_per_issue, 2),
            "avg_delay_per_assignee_days": round(avg_delay_per_assignee, 2),
            "mapped_assignees": mapped_assignees,
            "unmapped_assignees": unmapped_assignees,
        },
        "by_team": _build_group_summary(response_df, "Team"),
        "by_scrum": _build_group_summary(response_df, "Scrum"),
        "top_assignees": top_assignees_df.to_dict("records"),
        "filters": {
            "teams": team_filters,
            "scrums": sorted(response_df["Scrum"].dropna().astype(str).unique().tolist()),
            "components": sorted({
                component
                for values in response_df.get("_component_tokens", pd.Series(dtype=object)).tolist()
                for component in (values or [])
                if _normalize_text(component)
            }),
        },
        "data_timestamp": data_timestamp,
    }


@router.get("/assignees")
def get_assignee_delay_assignees(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    team: Optional[str] = Query(None),
    scrum: Optional[str] = Query(None),
    component: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("total_delay", pattern="^(total_delay|issues|avg_delay|assignee)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: TokenData = Depends(require_report_access),
):
    """Get assignee level delay rows with filters, sorting, and pagination."""
    df = _load_assignee_delay_data()
    enriched_df = _enrich_with_org_context(df)
    enriched_df, _accessible_teams = _apply_assignee_delay_rbac(enriched_df, current_user)

    if team and team != "All":
        enriched_df = enriched_df[enriched_df["Team"] == team]

    if scrum and scrum != "All":
        enriched_df = enriched_df[enriched_df["Scrum"] == scrum]

    if component and component != "All":
        enriched_df = enriched_df[
            enriched_df["_component_tokens"].apply(lambda values: component in (values or []))
        ]

    if search:
        term = search.strip().lower()
        if term:
            enriched_df = enriched_df[
                enriched_df["Assignee"].astype(str).str.lower().str.contains(term, na=False)
            ]

    sort_column_map = {
        "total_delay": "Total_Attributable_Delay_Days",
        "issues": "Issues_With_Delay",
        "avg_delay": "Avg_Delay_Per_Issue_Days",
        "assignee": "Assignee",
    }
    sort_column = sort_column_map.get(sort_by, "Total_Attributable_Delay_Days")
    is_ascending = sort_order == "asc"
    enriched_df = enriched_df.sort_values(sort_column, ascending=is_ascending)

    total_count = int(len(enriched_df))
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    page_df = enriched_df.iloc[start_idx:end_idx].copy()
    page_df = page_df.drop(columns=["_assignee_norm", "_team_clean", "_component_tokens"], errors="ignore")

    top_assignees = (
        enriched_df.sort_values("Total_Attributable_Delay_Days", ascending=False)
        .head(15)
        .drop(columns=["_assignee_norm", "_team_clean", "_component_tokens"], errors="ignore")
        .to_dict("records")
    )

    return {
        "assignees": page_df.to_dict("records"),
        "top_assignees": top_assignees,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
        },
        "applied_filters": {
            "team": team or "All",
            "scrum": scrum or "All",
            "component": component or "All",
            "search": search or "",
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    }


@router.get("/health")
def get_assignee_delay_health():
    """Health endpoint to validate report data availability."""
    file_exists = ASSIGNEE_DELAY_FILE.exists()
    row_count = 0

    if file_exists:
        try:
            df = _load_assignee_delay_data()
            row_count = int(len(df))
        except HTTPException:
            row_count = 0

    return {
        "ready": file_exists,
        "data_file": str(ASSIGNEE_DELAY_FILE),
        "rows": row_count,
    }


@router.get("/assignee-issues")
def get_assignee_issue_delays(
    assignee: str = Query(..., min_length=1),
    current_user: TokenData = Depends(require_report_access),
):
    """Return issue-level attributable delay rows for a selected assignee."""
    assignee_name = _normalize_text(assignee)
    if not assignee_name:
        raise HTTPException(status_code=400, detail="Assignee is required")

    # Resolve SAPID — no SAPID means no data to present
    sapid_map = _load_sapid_map()
    resource = sapid_map.get(assignee_name.lower().strip())
    if not resource:
        return {
            "assignee": assignee_name,
            "issues": [],
            "total_issues": 0,
            "total_attributable_delay_days": 0.0,
        }
    assignee_sapid = resource["sapid"]
    assignee_display = resource["display_name"]

    # Fast path: read pre-generated cache written by the scheduled job (keyed by SAPID)
    cache_file = ASSIGNEE_DELAY_CACHE_DIR / f"assignee_{assignee_sapid}.json"
    if cache_file.exists():
        try:
            cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
            now_ts_cache = pd.Timestamp.now(tz="UTC")

            # The cache was frozen at job-run time. For open issues, effective_end_dt
            # was "now at job time", which grows staler each day. Rescale attributable
            # and total delay proportionally so the drawer matches the Issue Transition
            # History endpoint (which always uses live now_ts as effective_end_dt).
            for issue in cache_data.get("issues", []):
                status_norm = _normalize_text(issue.get("status", "")).lower()
                if status_norm in DONE_STATUSES:
                    continue  # closed — effective_end is fixed at completion date, no drift

                baseline_raw = issue.get("delay_baseline_date", "")
                if not baseline_raw:
                    continue
                baseline_dt = pd.to_datetime(baseline_raw, errors="coerce", utc=True)
                if baseline_dt is None or pd.isna(baseline_dt):
                    continue

                old_total = float(issue.get("issue_delay_days") or 0)
                new_total = max(0.0, (now_ts_cache - baseline_dt).total_seconds() / 86400)
                if old_total > 0 and abs(new_total - old_total) > 0.001:
                    scale = new_total / old_total
                    old_attr = float(issue.get("attributable_delay_days") or 0)
                    issue["attributable_delay_days"] = round(min(old_attr * scale, new_total), 2)
                    issue["issue_delay_days"] = round(new_total, 2)
                    issue["effective_end_date"] = now_ts_cache.isoformat()

            # Recalculate totals after rescaling
            all_issues = cache_data.get("issues", [])
            cache_data["total_attributable_delay_days"] = round(
                sum(float(r.get("attributable_delay_days") or 0) for r in all_issues), 2
            )

            accessible_assignees, accessible_teams = _get_accessible_assignee_scope(current_user)
            if accessible_assignees is not None:
                target_norm = assignee_name.lower()
                if target_norm not in accessible_assignees:
                    filtered = [
                        row for row in all_issues
                        if _normalize_text(row.get("team", "")).lower() in accessible_teams
                    ]
                    cache_data["issues"] = filtered
                    cache_data["total_issues"] = len(filtered)
                    cache_data["total_attributable_delay_days"] = round(
                        sum(float(r.get("attributable_delay_days") or 0) for r in filtered), 2
                    )
            return {
                "assignee": cache_data.get("assignee", assignee_name),
                "issues": cache_data.get("issues", []),
                "total_issues": cache_data.get("total_issues", 0),
                "total_attributable_delay_days": cache_data.get("total_attributable_delay_days", 0.0),
            }
        except Exception:
            pass  # Fall through to live computation

    target_assignee_norm = assignee_name.lower()
    issues_df = _load_jira_issues_data()
    history_df = _load_jira_history_data()

    first_done_map, first_active_map = _build_first_transition_maps(history_df)
    assignee_transition_map = _build_assignee_transition_map(history_df)

    candidate_keys = set(
        issues_df[
            issues_df["Assignee"].astype(str).str.strip().str.lower() == target_assignee_norm
        ]["Key"].tolist()
    )

    assignment_rows = history_df[history_df["_field_norm"] == "assignee"]
    if not assignment_rows.empty:
        candidate_from_history = assignment_rows[
            (assignment_rows["_from_norm"] == target_assignee_norm)
            | (assignment_rows["_to_norm"] == target_assignee_norm)
        ]["Key"].tolist()
        candidate_keys.update(candidate_from_history)

    if not candidate_keys:
        return {
            "assignee": assignee_name,
            "issues": [],
            "total_issues": 0,
            "total_attributable_delay_days": 0.0,
        }

    candidate_df = issues_df[issues_df["Key"].isin(candidate_keys)].copy()

    accessible_assignees, accessible_teams = _get_accessible_assignee_scope(current_user)
    if accessible_assignees is not None:
        candidate_df["_assignee_norm"] = candidate_df["Assignee"].apply(_normalize_person_name)
        candidate_df["_team_clean"] = candidate_df["Team"].fillna("").astype(str).str.strip()
        candidate_df = candidate_df[
            candidate_df["_assignee_norm"].isin(accessible_assignees)
            | candidate_df["_team_clean"].isin(accessible_teams)
        ].copy()

    if candidate_df.empty:
        return {
            "assignee": assignee_name,
            "issues": [],
            "total_issues": 0,
            "total_attributable_delay_days": 0.0,
        }

    now_ts = pd.Timestamp.now(tz="UTC")
    issue_rows: List[Dict[str, Any]] = []

    for _, issue in candidate_df.iterrows():
        issue_key = _normalize_text(issue.get("Key"))
        if not issue_key:
            continue

        issue_type_norm = _normalize_text(issue.get("_issue_type_norm")).lower()
        if issue_type_norm in EXCLUDED_ISSUE_TYPES:
            continue

        issue_status_norm = _normalize_text(issue.get("_status_norm")).lower()
        if issue_status_norm in EXCLUDED_STATUSES:
            continue

        issue_assignee = _normalize_text(issue.get("Assignee")) or "Unassigned"
        created_dt = pd.to_datetime(issue.get("_created_dt"), errors="coerce", utc=True)
        sprint_end_dt = pd.to_datetime(issue.get("_sprint_end_dt"), errors="coerce", utc=True)
        is_done = bool(issue.get("_is_done", False))

        completion_dt = pd.to_datetime(first_done_map.get(issue_key), errors="coerce", utc=True)
        effective_end_dt = completion_dt if is_done else now_ts

        if effective_end_dt is None or pd.isna(effective_end_dt):
            continue
        if sprint_end_dt is None or pd.isna(sprint_end_dt):
            continue

        first_active_dt = pd.to_datetime(first_active_map.get(issue_key), errors="coerce", utc=True)
        delay_reference_dt = first_active_dt
        if delay_reference_dt is None or pd.isna(delay_reference_dt):
            delay_reference_dt = created_dt

        delay_baseline_dt = sprint_end_dt
        if (
            delay_reference_dt is not None
            and not pd.isna(delay_reference_dt)
            and delay_reference_dt > sprint_end_dt
        ):
            delay_baseline_dt = delay_reference_dt

        issue_attribution = _segment_assignee_attribution(
            issue_assignee=issue_assignee,
            created_dt=created_dt,
            effective_end_dt=effective_end_dt,
            delay_baseline_dt=delay_baseline_dt,
            assignee_events=assignee_transition_map.get(issue_key, []),
        )

        attributable_delay = 0.0
        for assignee_key, delay_value in issue_attribution.items():
            if _normalize_text(assignee_key).lower() == target_assignee_norm:
                attributable_delay += float(delay_value)

        if attributable_delay <= 0:
            continue

        issue_delay_days = max(0.0, (effective_end_dt - delay_baseline_dt).total_seconds() / 86400)

        issue_rows.append(
            {
                "issue_key": issue_key,
                "summary": _normalize_text(issue.get("Summary")),
                "issue_type": _normalize_text(issue.get("Issue Type")),
                "status": _normalize_text(issue.get("Status")),
                "team": _normalize_text(issue.get("Team")) or "Unknown",
                "scrum": _normalize_text(issue.get("Sprint")) or "Unknown",
                "attributable_delay_days": round(attributable_delay, 2),
                "issue_delay_days": round(issue_delay_days, 2),
                "delay_baseline_date": pd.to_datetime(delay_baseline_dt, errors="coerce", utc=True).isoformat(),
                "effective_end_date": pd.to_datetime(effective_end_dt, errors="coerce", utc=True).isoformat(),
            }
        )

    issue_rows.sort(key=lambda row: row["attributable_delay_days"], reverse=True)
    total_delay = round(sum(row["attributable_delay_days"] for row in issue_rows), 2)

    return {
        "assignee": assignee_name,
        "issues": issue_rows,
        "total_issues": len(issue_rows),
        "total_attributable_delay_days": total_delay,
    }
