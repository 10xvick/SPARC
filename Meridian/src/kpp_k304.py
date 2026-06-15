#!/usr/bin/env python3
"""
KPP K304 - MEND Gating Issues
Counts total Mend security issues (High + Medium severity only) per team,
derived from the Mend PDF reports downloaded by the security_scan_fetch job.
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_description() -> str:
    return (
        "MEND Gating Issues – Total Mend security issues (High + Medium severity) per team, "
        "aggregated from Mend PDF reports. Source: Severity Distribution section (Criti/High/Med/Low)."
    )


def _parse_mend_pdf(pdf_path: str) -> int:
    if not os.path.exists(pdf_path):
        print(f"    ⚠ MEND report not found: {pdf_path}")
        return 0

    try:
        from pypdf import PdfReader
    except Exception:
        print("    ⚠ pypdf is not installed; MEND counts default to 0")
        return 0

    try:
        reader = PdfReader(pdf_path)
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:8])
    except Exception as exc:
        print(f"    ⚠ Failed to parse PDF {pdf_path}: {exc}")
        return 0

    import re
    match = re.search(r"Criti\s*cal\s*(\d+)\s*High\s*(\d+)\s*Med\s*(\d+)\s*Low\s*(\d+)", text, re.IGNORECASE | re.DOTALL)
    if not match:
        print(f"    ⚠ Severity distribution not found in {os.path.basename(pdf_path)}")
        return 0

    high = int(match.group(2))
    medium = int(match.group(3))
    total = high + medium
    print(f"    ✓ {os.path.basename(pdf_path)}: High={high}, Medium={medium} → {total}")
    return total


def _load_scan_config(project_root: Path) -> dict:
    """Load config/security_scan_config.json."""
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


def _build_team_scores(scan_config: dict, scans_mend_dir: Path) -> tuple[dict[str, int], dict[str, list[str]]]:
    team_scores: dict[str, int] = {}
    team_sources: dict[str, list[str]] = {}

    for project in scan_config.get("projects", []):
        pid      = project.get("id", "").strip()
        teams    = project.get("teams", [])
        reports  = project.get("reports", [])

        # Find the MEND report filename for this project
        mend_entry = next((r for r in reports if r.get("type") == "mend"), None)
        if not mend_entry:
            print(f"  ⚠ No MEND report configured for project '{pid}' — skipping")
            continue

        pdf_path = str(scans_mend_dir / mend_entry["filename"])
        count = _parse_mend_pdf(pdf_path)

        for team in teams:
            team_scores[team] = team_scores.get(team, 0) + count
            team_sources.setdefault(team, []).append(f"{pid}({count})")

    return team_scores, team_sources


def _median(values: list[float]) -> float:
    """Return the median of a list; 0.0 if empty."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return float(s[mid] if n % 2 == 1 else (s[mid - 1] + s[mid]) / 2)


# ─────────────────────────────────────────────────────────────────────────────
# Main KPI function
# ─────────────────────────────────────────────────────────────────────────────

def k304(resources_file: str, output_dir: str, fiscal_start_month: int = 4, current_date: date | None = None) -> bool:
    """
    K304: MEND Gating Issues aggregated at Team level, propagated to all members of the team.
    """
    output_file = os.path.join(output_dir, "k304-data.csv")

    if current_date is None:
        current_date = date.today()

    current_date_str = current_date.strftime("%Y%m%d")

    print(f"\n{'='*60}")
    print("KPP K304 - MEND Gating Issues")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")

    # Derive project root from output_dir (output/ is one level below root)
    project_root = Path(output_dir).parent

    # ── Load resources ────────────────────────────────────────────────────────
    print("Loading resources data...")
    try:
        resources_df = pd.read_csv(resources_file)
        resources = resources_df[["SAPID", "Name", "Team"]].copy()
        resources["SAPID"] = resources["SAPID"].fillna(0).astype(int).astype(str)
        resources = resources[resources["Team"].notna() & (resources["Team"] != "-NA-")]
        print(f"  ✓ Loaded {len(resources)} resources")
    except Exception as exc:
        print(f"  ✗ Error loading resources: {exc}")
        return False

    if resources.empty:
        print("  ✗ No resources data")
        return False

    # ── Load scan configuration and parse MEND PDF reports ──────────────────
    print("Loading scan configuration...")
    scan_config = _load_scan_config(project_root)
    if not scan_config:
        print("  ⚠ No scan configuration found — marking all teams as not configured")
        team_scores: dict[str, int] = {}
        team_sources: dict[str, list[str]] = {}
    else:
        scans_mend_dir = Path(output_dir) / "scans" / "mend"
        print(f"  Parsing MEND reports from: {scans_mend_dir}")
        team_scores, team_sources = _build_team_scores(scan_config, scans_mend_dir)
        print(f"  Team MEND scores: {team_scores}")
        if team_sources:
            print("  Team score contributions (for reference):")
            for team in sorted(team_sources):
                src = " + ".join(team_sources[team])
                print(f"    - {team}: {src} = {team_scores.get(team, 0)}")

    # ── Period labels for the current date ───────────────────────────────────
    current_dt        = pd.Timestamp(current_date)
    current_week      = get_week_number(current_dt)
    current_month     = get_month_string(current_dt)
    current_quarter   = get_quarter_string(current_dt)
    current_fiscal_yr = get_fiscal_year(current_dt, fiscal_start_month)

    # ── Load existing history (for median calculation) ────────────────────────
    print("Loading historical k304 data for median computation...")
    if os.path.exists(output_file):
        try:
            history_df = pd.read_csv(output_file, dtype={"SAPID": str, "Week": str})
            # Drop any rows already recorded for the current week (will be replaced below)
            history_df = history_df[history_df["Week"].astype(str) != str(current_week)]
            print(f"  ✓ Loaded {len(history_df)} historical rows (current week excluded)")
        except Exception as exc:
            print(f"  ⚠ Failed to read existing history: {exc} — starting fresh")
            history_df = pd.DataFrame()
    else:
        history_df = pd.DataFrame()
        print("  ℹ No existing history file — this is the first run")

    configured_teams = set(team_scores.keys())

    # ── Build current-run rows ────────────────────────────────────────────────
    print("Computing per-member values...")
    new_rows = []

    for _, emp in resources.iterrows():
        sapid = str(emp["SAPID"])
        name  = emp["Name"]
        team  = emp["Team"]

        is_configured = team in configured_teams
        weekly_val = float(team_scores.get(team, 0)) if is_configured else None

        # Gather historical weekly values for this person in each period
        if not history_df.empty and "SAPID" in history_df.columns:
            person_hist = history_df[history_df["SAPID"].astype(str) == sapid]
        else:
            person_hist = pd.DataFrame()

        def _period_median(col: str, current_label: str) -> float:
            if weekly_val is None:
                return None
            if person_hist.empty or col not in person_hist.columns:
                return _median([weekly_val])
            past_vals = person_hist[person_hist[col] == current_label]["Weekly"].dropna().tolist()
            return _median(past_vals + [weekly_val])

        monthly_val   = _period_median("Month",   current_month)
        quarterly_val = _period_median("Quarter", current_quarter)
        annual_val    = _period_median("Year",    current_fiscal_yr)

        new_rows.append({
            "CurrentDate": current_date_str,
            "Week":        current_week,
            "Month":       current_month,
            "Quarter":     current_quarter,
            "Year":        current_fiscal_yr,
            "SAPID":       sapid,
            "Name":        name,
            "Weekly":      weekly_val,
            "Monthly":     monthly_val,
            "Quarterly":   quarterly_val,
            "Annual":      annual_val,
            "ConfigurationStatus": "configured" if is_configured else "not_configured",
        })

    new_df = pd.DataFrame(new_rows)

    # ── Merge with history and save ──────────────────────────────────────────
    if not history_df.empty:
        combined = pd.concat([history_df, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_csv(output_file, index=False)

    print(f"\n  ✓ Saved {output_file}")
    print(f"    Current run: {len(new_rows)} records  |  Total history: {len(combined)} rows")
    print(f"    Teams with MEND data: {sorted(team_scores.keys())}")
    print(
        f"    Teams with no MEND configuration: "
        f"{sorted(set(resources['Team'].unique()) - set(team_scores.keys()))}"
    )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point (for standalone testing)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    parser = argparse.ArgumentParser(description="Run KPI K304 – MEND Gating Issues")
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT),
        help="Path to the TeamSight project root",
    )
    args = parser.parse_args()

    root = Path(args.project_root)
    success = k304(
        resources_file=str(root / "config" / "Resources.csv"),
        output_dir=str(root / "output"),
    )
    sys.exit(0 if success else 1)
