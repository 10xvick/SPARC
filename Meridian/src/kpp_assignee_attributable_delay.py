#!/usr/bin/env python3
"""
Assignee Attributable Delay Analysis

Calculates attributable delay for each assignee across non-Epic and non-Deferred JIRA issues.

Output:
- output/assignee_attributable_delay.csv

CSV columns:
- Assignee
- Total_Attributable_Delay_Days
- Issues_With_Delay
- Avg_Delay_Per_Issue_Days
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from typing import Any, Dict, List

import pandas as pd


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
ISSUES_FILE = os.path.join(PROJECT_ROOT, "output", "JIRAIssues.csv")
HISTORY_FILE = os.path.join(PROJECT_ROOT, "output", "JIRAIssues_History.csv")
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "output", "assignee_attributable_delay.csv")
RESOURCES_FILE = os.path.join(PROJECT_ROOT, "config", "Resources.csv")
ASSIGNEE_DELAY_CACHE_DIR = os.path.join(PROJECT_ROOT, "output", "AssigneeDelayCache")

MIN_DELAY_THRESHOLD_DAYS = 1.0

DONE_STATUSES = {
    "done",
    "closed",
    "resolved",
    "removed",
    "completed",
}

EXCLUDED_ISSUE_TYPES = {
    "epic",
}

EXCLUDED_STATUSES = {
    "deferred",
    "defferred",
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


def _clean_text(value: Any, default: str = "") -> str:
    """Normalize text values from CSV cells."""
    if pd.isna(value):
        return default

    text = str(value).strip()
    if not text:
        return default

    if text.lower() in {"nan", "none", "null"}:
        return default

    return text


def _load_sapid_mapping() -> Dict[str, Dict[str, str]]:
    """Load Resources.csv and return normalized JIRA name -> {sapid, display_name}.

    Both 'Name' and 'JIRA Name' columns are used for matching. Only rows with a
    non-empty SAPID are included.
    """
    sapid_map: Dict[str, Dict[str, str]] = {}
    if not os.path.exists(RESOURCES_FILE):
        return sapid_map
    try:
        resources_df = pd.read_csv(RESOURCES_FILE)
    except Exception:
        return sapid_map

    for _, row in resources_df.iterrows():
        sapid = _clean_text(row.get("SAPID"))
        if not sapid:
            continue
        display_name = _clean_text(row.get("Name"))
        for name_col in ("JIRA Name", "Name"):
            candidate = _clean_text(row.get(name_col))
            if not candidate:
                continue
            key = candidate.lower().strip()
            if key and key not in sapid_map:
                sapid_map[key] = {"sapid": sapid, "display_name": display_name or candidate}
    return sapid_map


def _load_issues_data() -> pd.DataFrame:
    """Load JIRA issues data."""
    if not os.path.exists(ISSUES_FILE):
        print(f"❌ Error: JIRA issues file not found: {ISSUES_FILE}")
        print("   Run jira_fetch.py first.")
        sys.exit(1)

    issues_df = pd.read_csv(ISSUES_FILE)

    if "Issue Type" not in issues_df.columns and "Issue_Type" in issues_df.columns:
        issues_df["Issue Type"] = issues_df["Issue_Type"]

    required_columns = ["Key", "Issue Type", "Status", "Assignee", "Created", "Sprint.endDate"]
    for column in required_columns:
        if column not in issues_df.columns:
            issues_df[column] = ""

    issues_df["Key"] = issues_df["Key"].fillna("").astype(str).str.strip()
    issues_df["Status"] = issues_df["Status"].fillna("").astype(str).str.strip()
    issues_df["Assignee"] = issues_df["Assignee"].replace("", "Unassigned").fillna("Unassigned").astype(str).str.strip()

    issues_df["_created_dt"] = pd.to_datetime(issues_df["Created"], errors="coerce", utc=True)
    issues_df["_sprint_end_dt"] = pd.to_datetime(issues_df["Sprint.endDate"], errors="coerce", utc=True)
    issues_df["_status_norm"] = issues_df["Status"].str.lower().str.strip()
    issues_df["_issue_type_norm"] = issues_df["Issue Type"].fillna("").astype(str).str.strip().str.lower()
    issues_df["_is_done"] = issues_df["_status_norm"].isin(DONE_STATUSES)

    issues_df = issues_df[issues_df["Key"] != ""].copy()
    return issues_df


def _load_history_data() -> pd.DataFrame:
    """Load JIRA history data, returning empty dataframe if unavailable."""
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame(columns=["Key", "Field", "FromValue", "ToValue", "ChangeDate"])

    history_df = pd.read_csv(HISTORY_FILE)
    for column in ["Key", "Field", "FromValue", "ToValue", "ChangeDate"]:
        if column not in history_df.columns:
            history_df[column] = ""

    history_df["Key"] = history_df["Key"].fillna("").astype(str).str.strip()
    history_df["Field"] = history_df["Field"].fillna("").astype(str).str.strip().str.lower()
    history_df["FromValue"] = history_df["FromValue"].fillna("").astype(str).str.strip()
    history_df["ToValue"] = history_df["ToValue"].fillna("").astype(str).str.strip()
    history_df["ChangeDate"] = pd.to_datetime(history_df["ChangeDate"], errors="coerce", utc=True)

    history_df = history_df[(history_df["Key"] != "") & history_df["ChangeDate"].notna()].copy()
    return history_df


def _build_first_transition_maps(history_df: pd.DataFrame) -> tuple[Dict[str, pd.Timestamp], Dict[str, pd.Timestamp]]:
    """Build issue->first_done and issue->first_active transition maps."""
    if history_df.empty:
        return {}, {}

    status_history = history_df[history_df["Field"] == "status"].copy()
    status_history["_to_norm"] = status_history["ToValue"].fillna("").astype(str).str.strip().str.lower()

    first_done_map: Dict[str, pd.Timestamp] = {}
    done_rows = status_history[status_history["_to_norm"].isin(DONE_STATUSES)].copy()
    if not done_rows.empty:
        done_rows = done_rows.sort_values(["Key", "ChangeDate"])
        first_done = done_rows.groupby("Key", as_index=False).first()
        first_done_map = {
            _clean_text(row["Key"]): row["ChangeDate"]
            for _, row in first_done.iterrows()
            if _clean_text(row["Key"])
        }

    first_active_map: Dict[str, pd.Timestamp] = {}
    active_rows = status_history[status_history["_to_norm"].isin(FIRST_ACTIVE_STATUSES)].copy()
    if not active_rows.empty:
        active_rows = active_rows.sort_values(["Key", "ChangeDate"])
        first_active = active_rows.groupby("Key", as_index=False).first()
        first_active_map = {
            _clean_text(row["Key"]): row["ChangeDate"]
            for _, row in first_active.iterrows()
            if _clean_text(row["Key"])
        }

    return first_done_map, first_active_map


def _build_assignee_transition_map(history_df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
    """Build issue->assignee transition events map sorted by time."""
    if history_df.empty:
        return {}

    assignment_rows = history_df[history_df["Field"] == "assignee"].copy()
    if assignment_rows.empty:
        return {}

    assignment_rows = assignment_rows.sort_values(["Key", "ChangeDate"])
    transition_map: Dict[str, List[Dict[str, Any]]] = {}

    for issue_key, issue_history in assignment_rows.groupby("Key"):
        clean_key = _clean_text(issue_key)
        if not clean_key:
            continue

        events: List[Dict[str, Any]] = []
        for _, row in issue_history.iterrows():
            changed_at = pd.to_datetime(row.get("ChangeDate"), errors="coerce", utc=True)
            if changed_at is None or pd.isna(changed_at):
                continue

            events.append({
                "changed_at": changed_at,
                "from_assignee": _clean_text(row.get("FromValue"), "Unassigned"),
                "to_assignee": _clean_text(row.get("ToValue"), "Unassigned"),
            })

        if events:
            transition_map[clean_key] = events

    return transition_map


def _segment_assignee_attribution(
    issue_key: str,
    issue_assignee: str,
    created_dt: pd.Timestamp,
    effective_end_dt: pd.Timestamp,
    delay_baseline_dt: pd.Timestamp,
    assignee_events: List[Dict[str, Any]],
) -> Dict[str, float]:
    """Compute attributable delay contribution per assignee for one issue."""
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

    current_assignee = _clean_text(issue_assignee, "Unassigned")
    if assignee_events:
        first_from = _clean_text(assignee_events[0].get("from_assignee"))
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

        clean_assignee = _clean_text(assignee_name, "Unassigned")
        attribution[clean_assignee] = attribution.get(clean_assignee, 0.0) + overlap_days

    period_start = start_ts

    for event in assignee_events:
        changed_at = event.get("changed_at")
        if changed_at is None or pd.isna(changed_at):
            continue

        if changed_at < period_start:
            next_assignee = _clean_text(event.get("to_assignee"))
            if next_assignee:
                current_assignee = next_assignee
            continue

        event_boundary = min(changed_at, effective_end_dt)
        add_segment(current_assignee, period_start, event_boundary)

        period_start = event_boundary
        next_assignee = _clean_text(event.get("to_assignee"))
        if next_assignee:
            current_assignee = next_assignee

        if period_start >= effective_end_dt:
            break

    add_segment(current_assignee, period_start, effective_end_dt)

    return attribution


def calculate_assignee_attributable_delay() -> pd.DataFrame:
    """Calculate assignee attributable delay across all JIRA issues."""
    issues_df = _load_issues_data()
    history_df = _load_history_data()

    first_done_map, first_active_map = _build_first_transition_maps(history_df)
    assignee_transition_map = _build_assignee_transition_map(history_df)

    now_ts = pd.Timestamp.now(tz="UTC")

    assignee_stats: Dict[str, Dict[str, Any]] = {}
    assignee_issue_details: Dict[str, List[Dict[str, Any]]] = {}
    processed_issues = 0
    skipped_epics = 0
    skipped_deferred = 0

    for _, issue in issues_df.iterrows():
        issue_key = _clean_text(issue.get("Key"))
        if not issue_key:
            continue

        issue_type_norm = _clean_text(issue.get("_issue_type_norm")).lower()
        if issue_type_norm in EXCLUDED_ISSUE_TYPES:
            skipped_epics += 1
            continue

        issue_status_norm = _clean_text(issue.get("_status_norm")).lower()
        if issue_status_norm in EXCLUDED_STATUSES:
            skipped_deferred += 1
            continue

        processed_issues += 1
        issue_assignee = _clean_text(issue.get("Assignee"), "Unassigned")
        created_dt = pd.to_datetime(issue.get("_created_dt"), errors="coerce", utc=True)
        sprint_end_dt = pd.to_datetime(issue.get("_sprint_end_dt"), errors="coerce", utc=True)
        is_done = bool(issue.get("_is_done", False))

        completion_dt = pd.to_datetime(first_done_map.get(issue_key), errors="coerce", utc=True)
        if is_done:
            effective_end_dt = completion_dt
        else:
            effective_end_dt = now_ts

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
            issue_key=issue_key,
            issue_assignee=issue_assignee,
            created_dt=created_dt,
            effective_end_dt=effective_end_dt,
            delay_baseline_dt=delay_baseline_dt,
            assignee_events=assignee_transition_map.get(issue_key, []),
        )

        issue_delay_days = max(
            0.0, (effective_end_dt - delay_baseline_dt).total_seconds() / 86400
        )
        delay_baseline_iso = (
            delay_baseline_dt.isoformat()
            if delay_baseline_dt is not None and not pd.isna(delay_baseline_dt)
            else ""
        )
        effective_end_iso = (
            effective_end_dt.isoformat()
            if effective_end_dt is not None and not pd.isna(effective_end_dt)
            else ""
        )

        for assignee_name, attributable_delay in issue_attribution.items():
            if attributable_delay <= 0:
                continue

            stats = assignee_stats.setdefault(
                assignee_name,
                {
                    "total_delay_days": 0.0,
                    "issue_keys": set(),
                },
            )
            stats["total_delay_days"] += attributable_delay
            stats["issue_keys"].add(issue_key)

            assignee_issue_details.setdefault(assignee_name, []).append({
                "issue_key": issue_key,
                "summary": _clean_text(issue.get("Summary")),
                "issue_type": _clean_text(issue.get("Issue Type")),
                "status": _clean_text(issue.get("Status")),
                "team": _clean_text(issue.get("Team")) or "Unknown",
                "scrum": _clean_text(issue.get("Sprint")) or "Unknown",
                "attributable_delay_days": round(float(attributable_delay), 2),
                "issue_delay_days": round(issue_delay_days, 2),
                "delay_baseline_date": delay_baseline_iso,
                "effective_end_date": effective_end_iso,
            })

    rows: List[Dict[str, Any]] = []
    for assignee_name, stats in assignee_stats.items():
        issue_count = len(stats["issue_keys"])
        total_delay_days = float(stats["total_delay_days"])
        avg_delay_days = total_delay_days / issue_count if issue_count > 0 else 0.0

        rows.append(
            {
                "Assignee": assignee_name,
                "Total_Attributable_Delay_Days": round(total_delay_days, 2),
                "Issues_With_Delay": issue_count,
                "Avg_Delay_Per_Issue_Days": round(avg_delay_days, 2),
            }
        )

    result_df = pd.DataFrame(rows)
    if not result_df.empty:
        result_df = result_df.sort_values(
            ["Total_Attributable_Delay_Days", "Issues_With_Delay", "Assignee"],
            ascending=[False, False, True],
        )

    print(
        "Processed "
        f"{processed_issues} issues "
        f"(excluding {skipped_epics} epic issues and {skipped_deferred} deferred issues)"
    )
    print(f"Assignees with attributable delay: {len(result_df)}")

    # Write per-assignee issue detail cache for fast endpoint reads.
    # Only write for assignees with a SAPID mapping; files are keyed by SAPID.
    sapid_map = _load_sapid_mapping()
    tmp_cache_dir = ASSIGNEE_DELAY_CACHE_DIR + "_tmp"
    cache_file_count = 0
    skipped_no_sapid = 0
    try:
        if os.path.exists(tmp_cache_dir):
            shutil.rmtree(tmp_cache_dir)
        os.makedirs(tmp_cache_dir, exist_ok=True)
        generated_at = now_ts.isoformat()
        for assignee_name, issue_details in assignee_issue_details.items():
            # Look up SAPID via normalized name
            resource = sapid_map.get(assignee_name.lower().strip())
            if not resource:
                skipped_no_sapid += 1
                continue
            sapid = resource["sapid"]
            display_name = resource["display_name"]
            issue_details.sort(key=lambda r: r["attributable_delay_days"], reverse=True)
            total_delay = round(sum(r["attributable_delay_days"] for r in issue_details), 2)
            cache_data = {
                "sapid": sapid,
                "assignee": display_name,
                "jira_name": assignee_name,
                "issues": issue_details,
                "total_issues": len(issue_details),
                "total_attributable_delay_days": total_delay,
                "generated_at": generated_at,
            }
            filename = f"assignee_{sapid}.json"
            with open(os.path.join(tmp_cache_dir, filename), "w", encoding="utf-8") as fh:
                json.dump(cache_data, fh)
            cache_file_count += 1
        if os.path.exists(ASSIGNEE_DELAY_CACHE_DIR):
            shutil.rmtree(ASSIGNEE_DELAY_CACHE_DIR)
        os.rename(tmp_cache_dir, ASSIGNEE_DELAY_CACHE_DIR)
        print(
            f"Per-assignee issue cache: {cache_file_count} files -> {ASSIGNEE_DELAY_CACHE_DIR}"
            f" (skipped {skipped_no_sapid} with no SAPID mapping)"
        )
    except Exception as exc:
        print(f"Warning: could not write per-assignee issue cache: {exc}")
        if os.path.exists(tmp_cache_dir):
            shutil.rmtree(tmp_cache_dir, ignore_errors=True)

    return result_df


def main():
    print("=" * 70)
    print("Assignee Attributable Delay Analysis")
    print("=" * 70)
    print()

    result_df = calculate_assignee_attributable_delay()

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    result_df.to_csv(OUTPUT_FILE, index=False)

    print(f"✅ Saved assignee attributable delay metrics: {OUTPUT_FILE}")

    if not result_df.empty:
        print("\nTop assignees by attributable delay:")
        print(result_df.head(10).to_string(index=False))
    else:
        print("\nNo attributable delay found in current data.")


if __name__ == "__main__":
    main()
