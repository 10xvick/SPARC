"""Employee score comparison report generation.

Generates Weekly, Quarterly, and Annual scores for each employee based on
the same KPI-to-score flow used in employee dashboard logic:
- KPI applicability by role (Primary, Secondary, All, Common)
- ROG status from actual vs (possibly prorated) target
- Category score rollup (Input, Output, Quality, Hygiene)
- Overall score as sum of category scores
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd

_SRC_ROOT = Path(__file__).resolve().parent
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from KppEvaluator import KppEvaluator


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_ROOT = _PROJECT_ROOT / "dashboard" / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.employee_score_shared import (  # type: ignore
    calculate_rog_status,
    get_prorated_target,
    parse_ref_date,
    read_employee_kpi_value,
    read_employee_security_kpi_value_and_status,
)
from app.services.scoring_service import get_scoring_service  # type: ignore


SECURITY_SCAN_KPIS = {"k301", "k302", "k303", "k304", "k305", "k306", "k307"}
PERIODS = ("Weekly", "Quarterly", "Annual")


@dataclass(frozen=True)
class ScoringConfig:
    weightages: Dict[str, float]
    status_weights: Dict[str, float]
    role_weights: Dict[str, float]


def _clean_text(value: Any, default: str = "") -> str:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return default
    return text


def _clean_sapid(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    try:
        return str(int(float(str(value).strip())))
    except (TypeError, ValueError):
        return _clean_text(value)


def _normalize_goal_type(goal_type_raw: Any) -> Optional[str]:
    goal_type = _clean_text(goal_type_raw)
    if not goal_type:
        return None
    lowered = goal_type.lower()
    if lowered in {"input", "i"}:
        return "Input"
    if lowered in {"output", "o"}:
        return "Output"
    if lowered in {"quality", "q"}:
        return "Quality"
    if lowered in {"hygiene", "h"}:
        return "Hygiene"
    return None


def _normalize_employment_status(raw_value: Any) -> str:
    """Normalize employment status values to Active/Inactive."""
    value = _clean_text(raw_value, "Active").lower()
    if value in {"inactive", "false", "no", "n", "0", "disabled"}:
        return "Inactive"
    return "Active"


def _period_target_column(period: str) -> str:
    if period == "Weekly":
        return "Weekly Target"
    if period == "Quarterly":
        return "Quarterly Target"
    return "Annual Target"


def _load_scoring_config(scoring_config_file: Path) -> ScoringConfig:
    defaults = ScoringConfig(
        weightages={"Input": 10.0, "Output": 50.0, "Quality": 30.0, "Hygiene": 10.0},
        status_weights={"Green": 1.0, "Orange": 0.75, "Red": 0.0},
        role_weights={"Primary": 20.0, "Secondary": 10.0, "All": 5.0, "Common": 3.0, "Other": 1.0},
    )
    try:
        if not scoring_config_file.exists():
            return defaults
        raw = json.loads(scoring_config_file.read_text(encoding="utf-8"))
        return ScoringConfig(
            weightages=raw.get("weightages", defaults.weightages),
            status_weights=raw.get("status_weights", defaults.status_weights),
            role_weights=raw.get("role_weights", defaults.role_weights),
        )
    except Exception:
        return defaults


def _score_from_kpis(kpis: Iterable[Dict[str, Any]], scoring_config: ScoringConfig) -> Dict[str, float]:
    category_stats: Dict[str, Dict[str, float]] = {
        "Input": {"weighted_actual": 0.0, "weighted_max": 0.0},
        "Output": {"weighted_actual": 0.0, "weighted_max": 0.0},
        "Quality": {"weighted_actual": 0.0, "weighted_max": 0.0},
        "Hygiene": {"weighted_actual": 0.0, "weighted_max": 0.0},
    }

    for kpi in kpis:
        if kpi.get("excluded_from_score", False):
            continue

        category = _clean_text(kpi.get("goal_type_category"))
        status = _clean_text(kpi.get("Status"))
        if category not in category_stats or status in {"", "NotConfigured"}:
            continue

        role_type = _clean_text(kpi.get("role_type"), "Other")
        role_weight = float(scoring_config.role_weights.get(role_type, scoring_config.role_weights.get("Other", 1.0)))
        status_credit = float(scoring_config.status_weights.get(status, 0.0))

        category_stats[category]["weighted_actual"] += role_weight * status_credit
        category_stats[category]["weighted_max"] += role_weight

    category_scores: Dict[str, float] = {}
    for category, stats in category_stats.items():
        weighted_max = stats["weighted_max"]
        if weighted_max <= 0:
            category_scores[category] = 0.0
            continue
        score_percentage = (stats["weighted_actual"] / weighted_max) * 100.0
        category_weight = float(scoring_config.weightages.get(category, 0.0))
        category_scores[category] = round((score_percentage / 100.0) * category_weight, 2)

    return {
        "overall": round(sum(category_scores.values()), 2),
        "input": round(category_scores.get("Input", 0.0), 2),
        "output": round(category_scores.get("Output", 0.0), 2),
        "quality": round(category_scores.get("Quality", 0.0), 2),
        "hygiene": round(category_scores.get("Hygiene", 0.0), 2),
    }


def _read_security_kpi_map(
    output_dir: Path,
    base_kpi: str,
    period: str,
    as_of_date: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    kpi_file = output_dir / f"{base_kpi}-data.csv"
    if not kpi_file.exists():
        return {}

    values: Dict[str, Dict[str, Any]] = {}
    try:
        with kpi_file.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if as_of_date:
                    row_date = _clean_text(row.get("CurrentDate"))
                    if row_date != as_of_date:
                        continue

                sapid = _clean_sapid(row.get("SAPID"))
                name = _clean_text(row.get("Name"))
                key = sapid or name
                if not key:
                    continue

                config_status = _clean_text(row.get("ConfigurationStatus"), "configured").lower()
                if config_status not in {"configured", "not_configured"}:
                    config_status = "configured"

                raw_value = row.get(period)
                value = None
                if raw_value not in (None, ""):
                    try:
                        value = float(raw_value)
                    except (TypeError, ValueError):
                        value = None

                values[key] = {
                    "value": value,
                    "configuration_status": config_status,
                }
    except Exception:
        return {}

    return values


def generate_employee_score_comparison(
    resources_file: Path,
    roles_file: Path,
    output_dir: Path,
    scoring_config_file: Path,
    jira_issues_file: Optional[Path] = None,
    github_commits_file: Optional[Path] = None,
    fiscal_start_month: int = 4,
    as_of_date: Optional[str] = None,
    team: Optional[str] = None,
    scrum: Optional[str] = None,
    primary_role: Optional[str] = None,
    secondary_role: Optional[str] = None,
    allowed_sapids: Optional[set[str]] = None,
) -> Dict[str, Any]:
    """Generate employee score comparison rows and filter options."""
    if jira_issues_file is None:
        jira_issues_file = output_dir / "JIRAIssues.csv"
    if github_commits_file is None:
        github_commits_file = output_dir / "github_commits.csv"

    resources_df = pd.read_csv(resources_file)
    roles_df = pd.read_csv(roles_file)

    resources_df = resources_df.copy()
    resources_df["SAPID"] = resources_df["SAPID"].apply(_clean_sapid)
    resources_df["Name"] = resources_df["Name"].apply(_clean_text)
    resources_df["Team"] = resources_df["Team"].apply(_clean_text)
    resources_df["Scrum"] = resources_df["Scrum"].apply(_clean_text)
    resources_df["Primary Role"] = resources_df["Primary Role"].apply(_clean_text)
    resources_df["Secondary Role"] = resources_df["Secondary Role"].apply(_clean_text)
    if "Employment Status" not in resources_df.columns:
        resources_df["Employment Status"] = "Active"
    resources_df["Employment Status"] = resources_df["Employment Status"].apply(_normalize_employment_status)
    resources_df = resources_df[resources_df["SAPID"] != ""]
    resources_df = resources_df[resources_df["Employment Status"] == "Active"]

    if allowed_sapids is not None:
        resources_df = resources_df[resources_df["SAPID"].isin(allowed_sapids)]

    available_teams = sorted({value for value in resources_df["Team"].tolist() if value})
    available_scrums = sorted({value for value in resources_df["Scrum"].tolist() if value})
    available_primary_roles = sorted({value for value in resources_df["Primary Role"].tolist() if value})
    available_secondary_roles = sorted({value for value in resources_df["Secondary Role"].tolist() if value})

    team_filter = _clean_text(team)
    scrum_filter = _clean_text(scrum)
    primary_filter = _clean_text(primary_role)
    secondary_filter = _clean_text(secondary_role)

    if team_filter:
        resources_df = resources_df[resources_df["Team"] == team_filter]
    if scrum_filter:
        resources_df = resources_df[resources_df["Scrum"] == scrum_filter]
    if primary_filter:
        resources_df = resources_df[resources_df["Primary Role"] == primary_filter]
    if secondary_filter:
        resources_df = resources_df[resources_df["Secondary Role"] == secondary_filter]

    roles_df = roles_df.copy()
    roles_df["Index"] = roles_df["Index"].fillna("").astype(str).str.strip()
    roles_df["Role"] = roles_df["Role"].fillna("").astype(str).str.strip()
    roles_df = roles_df[(roles_df["Goal Type"].notna()) & (roles_df["Goal Type"].astype(str).str.strip() != "")]

    evaluator = KppEvaluator(
        resources_file=str(resources_file),
        jira_issues_file=str(jira_issues_file),
        github_commits_file=str(github_commits_file),
        output_dir=str(output_dir),
        fiscal_start_month=fiscal_start_month,
    )
    kpis = sorted(evaluator.list_kpis(), key=lambda item: int(item[1:]))
    ref_date = parse_ref_date(as_of_date)
    scoring_service = get_scoring_service()

    rows: list[Dict[str, Any]] = []
    for _, employee in resources_df.iterrows():
        sapid = _clean_sapid(employee.get("SAPID"))
        name = _clean_text(employee.get("Name"), sapid)
        emp_primary = _clean_text(employee.get("Primary Role"))
        emp_secondary = _clean_text(employee.get("Secondary Role"))

        period_scores: Dict[str, Dict[str, float]] = {}
        for period in PERIODS:
            # Mirror employee_dashboard.py logic exactly.
            role_filtered_df = roles_df[
                (roles_df["Role"] == emp_primary)
                | (roles_df["Role"] == emp_secondary)
                | (roles_df["Role"] == "All")
                | (roles_df["Role"] == "Common")
            ]

            kpi_entries: list[Dict[str, Any]] = []
            for kpi in kpis:
                kpi_info = role_filtered_df[role_filtered_df["Index"] == kpi]
                if kpi_info.empty:
                    continue

                kpi_row = kpi_info.iloc[0]
                kpi_role = _clean_text(kpi_row.get("Role"))
                if kpi_role == emp_primary:
                    role_type = "Primary"
                elif kpi_role == emp_secondary:
                    role_type = "Secondary"
                elif kpi_role == "All":
                    role_type = "All"
                elif kpi_role == "Common":
                    role_type = "Common"
                else:
                    role_type = "Other"

                goal_type_value = kpi_row.get("Goal Type", "Input")
                goal_type_lower = str(goal_type_value).lower() if pd.notna(goal_type_value) else "input"
                if goal_type_lower in ["input", "i"]:
                    category = "input"
                elif goal_type_lower in ["output", "o"]:
                    category = "output"
                elif goal_type_lower in ["quality", "q"]:
                    category = "quality"
                elif goal_type_lower in ["hygiene", "h"]:
                    category = "hygiene"
                else:
                    category = "input"

                goal_type_category = goal_type_value
                if _normalize_goal_type(goal_type_category) is None:
                    continue

                target_col = _period_target_column(period)
                raw_target = kpi_row.get(target_col, 0)
                try:
                    target_value = float(raw_target) if pd.notna(raw_target) and str(raw_target).strip() != "" else 0.0
                except (TypeError, ValueError):
                    continue
                if target_value == 0:
                    continue

                type_code = _clean_text(kpi_row.get("Type", "NG")).upper()
                goal_direction = "Minimize" if "L" in type_code else "Maximize"
                prorate = _clean_text(kpi_row.get("Prorate", "Yes")).lower() != "no"
                comparison_target = get_prorated_target(
                    target_value,
                    period,
                    ref_date,
                    fiscal_start_month,
                    prorate=prorate,
                )

                if kpi in SECURITY_SCAN_KPIS:
                    actual_value, config_status = read_employee_security_kpi_value_and_status(
                        evaluator,
                        kpi,
                        period,
                        sapid,
                        name,
                        as_of_date,
                    )
                    if config_status == "not_configured":
                        kpi_entries.append({
                            "kpi_id": kpi.upper(),
                            "category": category,
                            "goal_type_category": goal_type_category,
                            "role_type": role_type,
                            "Status": "NotConfigured",
                            "excluded_from_score": True,
                        })
                        continue
                else:
                    actual_value = read_employee_kpi_value(
                        evaluator,
                        kpi,
                        period,
                        sapid,
                        name,
                        as_of_date,
                    )

                if actual_value is None or (isinstance(actual_value, float) and pd.isna(actual_value)):
                    continue
                try:
                    actual_numeric = float(actual_value)
                except (TypeError, ValueError):
                    continue
                rog_status = calculate_rog_status(actual_numeric, comparison_target, goal_direction)
                status = "Green" if rog_status == "green" else ("Orange" if rog_status == "orange" else "Red")

                kpi_entries.append({
                    "kpi_id": kpi.upper(),
                    "category": category,
                    "goal_type_category": goal_type_category,
                    "Status": status,
                    "role_type": role_type,
                    "excluded_from_score": False,
                })

            category_order = {"input": 0, "output": 1, "quality": 2, "hygiene": 3}
            role_order = {"Primary": 0, "Secondary": 1, "All": 2, "Common": 3, "Other": 4}
            kpi_entries_sorted = sorted(
                kpi_entries,
                key=lambda item: (
                    category_order.get(item.get("category", ""), 4),
                    role_order.get(item.get("role_type", "Other"), 4),
                    int(str(item.get("kpi_id", "K0"))[1:]),
                ),
            )
            score_data = scoring_service.calculate_score(kpi_entries_sorted)
            period_scores[period] = {
                "overall": round(score_data.get("overall_score", 0), 2),
                "input": round(score_data.get("categories", {}).get("Input", {}).get("score", 0), 2),
                "output": round(score_data.get("categories", {}).get("Output", {}).get("score", 0), 2),
                "quality": round(score_data.get("categories", {}).get("Quality", {}).get("score", 0), 2),
                "hygiene": round(score_data.get("categories", {}).get("Hygiene", {}).get("score", 0), 2),
            }

        rows.append({
            "name": name,
            "sapid": sapid,
            "team": _clean_text(employee.get("Team")),
            "scrum": _clean_text(employee.get("Scrum")),
            "primary_role": emp_primary,
            "secondary_role": emp_secondary,
            "scores": period_scores,
        })

    rows.sort(key=lambda row: (_clean_text(row.get("name")).lower(), _clean_text(row.get("sapid"))))

    return {
        "rows": rows,
        "available_filters": {
            "teams": available_teams,
            "scrums": available_scrums,
            "primary_roles": available_primary_roles,
            "secondary_roles": available_secondary_roles,
        },
        "applied_filters": {
            "team": team_filter,
            "scrum": scrum_filter,
            "primary_role": primary_filter,
            "secondary_role": secondary_filter,
        },
    }


def flatten_employee_score_rows(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Flatten nested score rows into CSV-friendly dictionaries."""
    flat_rows: list[Dict[str, Any]] = []
    for row in rows:
        scores = row.get("scores", {})
        flat_rows.append({
            "Name": row.get("name", ""),
            "SAPID": row.get("sapid", ""),
            "Team": row.get("team", ""),
            "Scrum": row.get("scrum", ""),
            "PrimaryRole": row.get("primary_role", ""),
            "SecondaryRole": row.get("secondary_role", ""),
            "Weekly_Overall": scores.get("Weekly", {}).get("overall", 0),
            "Weekly_Input": scores.get("Weekly", {}).get("input", 0),
            "Weekly_Output": scores.get("Weekly", {}).get("output", 0),
            "Weekly_Quality": scores.get("Weekly", {}).get("quality", 0),
            "Weekly_Hygiene": scores.get("Weekly", {}).get("hygiene", 0),
            "Quarterly_Overall": scores.get("Quarterly", {}).get("overall", 0),
            "Quarterly_Input": scores.get("Quarterly", {}).get("input", 0),
            "Quarterly_Output": scores.get("Quarterly", {}).get("output", 0),
            "Quarterly_Quality": scores.get("Quarterly", {}).get("quality", 0),
            "Quarterly_Hygiene": scores.get("Quarterly", {}).get("hygiene", 0),
            "Annual_Overall": scores.get("Annual", {}).get("overall", 0),
            "Annual_Input": scores.get("Annual", {}).get("input", 0),
            "Annual_Output": scores.get("Annual", {}).get("output", 0),
            "Annual_Quality": scores.get("Annual", {}).get("quality", 0),
            "Annual_Hygiene": scores.get("Annual", {}).get("hygiene", 0),
        })
    return flat_rows
