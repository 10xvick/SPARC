#!/usr/bin/env python3
"""
KPP K303 - SCA Gating Issues
Counts total SCA security issues (High + Medium severity only) per team,
derived from the SCA HTML reports downloaded by the security_scan_fetch job.
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year


def get_description() -> str:
    return (
        "SCA Gating Issues – Total SCA security issues (High + Medium severity) per team, "
        "aggregated from AppScan SCA HTML reports. Source: Summary of security issues section."
    )


def _parse_sca_html(html_path: str) -> int:
    if not os.path.exists(html_path):
        print(f"    ⚠ SCA report not found: {html_path}")
        return 0
    try:
        with open(html_path, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read()
    except Exception as exc:
        print(f"    ⚠ Failed to read {html_path}: {exc}")
        return 0

    section_match = re.search(r"Summary of security issues.*?</table>", content, re.DOTALL | re.IGNORECASE)
    if not section_match:
        print(f"    ⚠ Summary section not found in {os.path.basename(html_path)}")
        return 0
    section = section_match.group()

    def _extract_count(label: str) -> int:
        m = re.search(rf"{re.escape(label)}.*?<td[^>]*>\s*(\d+)\s*</td>", section, re.DOTALL | re.IGNORECASE)
        return int(m.group(1)) if m else 0

    high = _extract_count("High severity issues:")
    medium = _extract_count("Medium severity issues:")
    total = high + medium
    print(f"    ✓ {os.path.basename(html_path)}: High={high}, Medium={medium} → {total}")
    return total


def _load_scan_config(project_root: Path) -> dict:
    cfg_path = project_root / "config" / "security_scan_config.json"
    if not cfg_path.exists():
        print(f"  ⚠ Scan config not found: {cfg_path}")
        return {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        print(f"  ⚠ Failed to read scan config: {exc}")
        return {}


def _build_team_scores(scan_config: dict, scans_sca_dir: Path) -> tuple[dict[str, int], dict[str, list[str]]]:
    team_scores: dict[str, int] = {}
    team_sources: dict[str, list[str]] = {}

    for project in scan_config.get("projects", []):
        pid = project.get("id", "").strip()
        teams = project.get("teams", [])
        reports = project.get("reports", [])

        sca_entry = next((r for r in reports if r.get("type") == "sca"), None)
        if not sca_entry:
            print(f"  ⚠ No SCA report configured for project '{pid}' — skipping")
            continue

        html_path = str(scans_sca_dir / sca_entry["filename"])
        count = _parse_sca_html(html_path)
        for team in teams:
            team_scores[team] = team_scores.get(team, 0) + count
            team_sources.setdefault(team, []).append(f"{pid}({count})")

    return team_scores, team_sources


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    n = len(values)
    mid = n // 2
    return float(values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2)


def k303(resources_file: str, output_dir: str, fiscal_start_month: int = 4, current_date: date | None = None) -> bool:
    output_file = os.path.join(output_dir, "k303-data.csv")
    if current_date is None:
        current_date = date.today()
    current_date_str = current_date.strftime("%Y%m%d")

    print(f"\n{'='*60}")
    print("KPP K303 - SCA Gating Issues")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")

    project_root = Path(output_dir).parent
    resources_df = pd.read_csv(resources_file)
    resources = resources_df[["SAPID", "Name", "Team"]].copy()
    resources["SAPID"] = resources["SAPID"].fillna(0).astype(int).astype(str)
    resources = resources[resources["Team"].notna() & (resources["Team"] != "-NA-")]

    scan_config = _load_scan_config(project_root)
    if not scan_config:
        print("  ⚠ No scan configuration found — marking all teams as not configured")
        team_scores: dict[str, int] = {}
        team_sources: dict[str, list[str]] = {}
    else:
        scans_sca_dir = Path(output_dir) / "scans" / "sca"
        print(f"  Parsing SCA reports from: {scans_sca_dir}")
        team_scores, team_sources = _build_team_scores(scan_config, scans_sca_dir)
        print(f"  Team SCA scores: {team_scores}")
        if team_sources:
            print("  Team score contributions (for reference):")
            for team in sorted(team_sources):
                print(f"    - {team}: {' + '.join(team_sources[team])} = {team_scores.get(team, 0)}")

    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_year = get_fiscal_year(current_dt, fiscal_start_month)

    if os.path.exists(output_file):
        history_df = pd.read_csv(output_file, dtype={"SAPID": str, "Week": str})
        history_df = history_df[history_df["Week"].astype(str) != str(current_week)]
    else:
        history_df = pd.DataFrame()

    configured_teams = set(team_scores.keys())

    rows = []
    for _, emp in resources.iterrows():
        sapid = str(emp["SAPID"])
        team = emp["Team"]
        is_configured = team in configured_teams
        weekly = float(team_scores.get(team, 0)) if is_configured else None

        person_hist = history_df[history_df["SAPID"].astype(str) == sapid] if (not history_df.empty and "SAPID" in history_df.columns) else pd.DataFrame()

        def _period_median(period_col: str, period_label: str) -> float:
            if weekly is None:
                return None
            if person_hist.empty or period_col not in person_hist.columns:
                return _median([weekly])
            vals = person_hist[person_hist[period_col] == period_label]["Weekly"].dropna().tolist()
            return _median(vals + [weekly])

        rows.append({
            "CurrentDate": current_date_str,
            "Week": current_week,
            "Month": current_month,
            "Quarter": current_quarter,
            "Year": current_year,
            "SAPID": sapid,
            "Name": emp["Name"],
            "Weekly": weekly,
            "Monthly": _period_median("Month", current_month),
            "Quarterly": _period_median("Quarter", current_quarter),
            "Annual": _period_median("Year", current_year),
            "ConfigurationStatus": "configured" if is_configured else "not_configured",
        })

    new_df = pd.DataFrame(rows)
    combined = pd.concat([history_df, new_df], ignore_index=True) if not history_df.empty else new_df
    combined.to_csv(output_file, index=False)
    print(f"  ✓ Saved {output_file} ({len(new_df)} rows this run)")
    return True


if __name__ == "__main__":
    PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ok = k303(resources_file=str(PROJECT_ROOT / "config" / "Resources.csv"), output_dir=str(PROJECT_ROOT / "output"))
    sys.exit(0 if ok else 1)
