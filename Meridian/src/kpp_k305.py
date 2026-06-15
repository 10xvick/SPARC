#!/usr/bin/env python3
"""
KPP K305 - Unified Security Gating Issues
Aggregates team-level security gating issue KPIs:
  k301 (DAST) + k302 (SAST) + k303 (SCA) + k304 (MEND)

The KPI is assigned to individuals based on role applicability in Roles.csv,
but values are computed by summing per-person values from k301-k304 outputs.

Output: output/k305-data.csv
"""

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year


def get_description() -> str:
    return (
        "Unified Security Gating Issues – Aggregate of DAST, SAST, SCA, and MEND "
        "gating issue counts (High + Medium only) per individual by summing k301, k302, k303, and k304."
    )


def _load_kpi_file(path: str, label: str) -> pd.DataFrame:
    if not os.path.exists(path):
        print(f"  ⚠ {label} file not found: {path}")
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, dtype={"SAPID": str})
        required = {"SAPID", "Name", "Weekly", "Monthly", "Quarterly", "Annual"}
        if not required.issubset(set(df.columns)):
            print(f"  ⚠ {label} missing expected columns; skipping")
            return pd.DataFrame()
        return df
    except Exception as exc:
        print(f"  ⚠ Failed to read {label}: {exc}")
        return pd.DataFrame()


def _latest_snapshot(df: pd.DataFrame, current_date_str: str, current_week: str) -> pd.DataFrame:
    """Get one-row-per-SAPID snapshot, preferring current date then current week then latest date."""
    if df.empty:
        return df

    candidate = df[df["CurrentDate"].astype(str) == current_date_str]
    if candidate.empty:
        candidate = df[df["Week"].astype(str) == str(current_week)]
    if candidate.empty:
        latest_date = df["CurrentDate"].astype(str).max()
        candidate = df[df["CurrentDate"].astype(str) == latest_date]

    return candidate.sort_values(["SAPID", "CurrentDate"]).drop_duplicates(subset=["SAPID"], keep="last")


def k305(resources_file: str, output_dir: str, fiscal_start_month: int = 4,
         current_date: date | None = None) -> bool:
    output_file = os.path.join(output_dir, "k305-data.csv")

    if current_date is None:
        current_date = date.today()

    current_date_str = current_date.strftime("%Y%m%d")
    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_year = get_fiscal_year(current_dt, fiscal_start_month)

    print(f"\n{'='*60}")
    print("KPP K305 - Unified Security Gating Issues")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")

    # Load resources for full roster + TeamSight output format consistency
    try:
        resources_df = pd.read_csv(resources_file)
        resources = resources_df[["SAPID", "Name"]].copy()
        resources["SAPID"] = resources["SAPID"].fillna(0).astype(int).astype(str)
        resources = resources.drop_duplicates(subset=["SAPID"], keep="last")
    except Exception as exc:
        print(f"  ✗ Error loading resources: {exc}")
        return False

    if resources.empty:
        print("  ✗ No resources data")
        return False

    # Load component KPI snapshots
    component_paths = {
        "k301": os.path.join(output_dir, "k301-data.csv"),
        "k302": os.path.join(output_dir, "k302-data.csv"),
        "k303": os.path.join(output_dir, "k303-data.csv"),
        "k304": os.path.join(output_dir, "k304-data.csv"),
    }

    component_frames: list[pd.DataFrame] = []
    for label, path in component_paths.items():
        comp_df = _load_kpi_file(path, label)
        if comp_df.empty:
            continue
        snap = _latest_snapshot(comp_df, current_date_str=current_date_str, current_week=current_week)
        if snap.empty:
            continue
        if "ConfigurationStatus" not in snap.columns:
            snap["ConfigurationStatus"] = "configured"
        snap = snap[["SAPID", "Name", "Weekly", "Monthly", "Quarterly", "Annual", "ConfigurationStatus"]].copy()
        for metric in ["Weekly", "Monthly", "Quarterly", "Annual"]:
            snap[metric] = pd.to_numeric(snap[metric], errors="coerce")
        snap["ConfigurationStatus"] = snap["ConfigurationStatus"].fillna("configured").astype(str).str.strip().str.lower()
        for metric in ["Weekly", "Monthly", "Quarterly", "Annual"]:
            snap.loc[snap["ConfigurationStatus"] == "not_configured", metric] = pd.NA
        component_frames.append(snap)
        print(f"  ✓ Loaded {label} snapshot rows: {len(snap)}")

    # Aggregate components by SAPID
    if component_frames:
        all_components = pd.concat(component_frames, ignore_index=True)
        agg = all_components.groupby("SAPID", as_index=False).agg(
            Name=("Name", "last"),
            Weekly=("Weekly", lambda s: s.sum(min_count=1)),
            Monthly=("Monthly", lambda s: s.sum(min_count=1)),
            Quarterly=("Quarterly", lambda s: s.sum(min_count=1)),
            Annual=("Annual", lambda s: s.sum(min_count=1)),
            ConfigurationStatus=(
                "ConfigurationStatus",
                lambda s: "configured" if (s.fillna("configured").astype(str).str.lower() != "not_configured").any() else "not_configured",
            ),
        )
    else:
        agg = pd.DataFrame(columns=["SAPID", "Name", "Weekly", "Monthly", "Quarterly", "Annual", "ConfigurationStatus"])
        print("  ⚠ No component KPI data found; marking all values as not configured")

    # Ensure all resources are represented
    merged = resources.merge(agg, on="SAPID", how="left", suffixes=("", "_agg"))
    merged["Name"] = merged["Name_agg"].fillna(merged["Name"])
    merged["ConfigurationStatus"] = merged["ConfigurationStatus"].fillna("not_configured")
    for metric in ["Weekly", "Monthly", "Quarterly", "Annual"]:
        merged[metric] = pd.to_numeric(merged[metric], errors="coerce")
        merged.loc[merged["ConfigurationStatus"] == "configured", metric] = merged.loc[
            merged["ConfigurationStatus"] == "configured", metric
        ].fillna(0.0)

    result = pd.DataFrame({
        "CurrentDate": current_date_str,
        "Week": current_week,
        "Month": current_month,
        "Quarter": current_quarter,
        "Year": current_year,
        "SAPID": merged["SAPID"],
        "Name": merged["Name"],
        "Weekly": merged["Weekly"],
        "Monthly": merged["Monthly"],
        "Quarterly": merged["Quarterly"],
        "Annual": merged["Annual"],
        "ConfigurationStatus": merged["ConfigurationStatus"],
    })

    # Keep historical rows; replace this week's snapshot
    if os.path.exists(output_file):
        try:
            history_df = pd.read_csv(output_file, dtype={"SAPID": str, "Week": str})
            history_df = history_df[history_df["Week"].astype(str) != str(current_week)]
            result = pd.concat([history_df, result], ignore_index=True)
        except Exception as exc:
            print(f"  ⚠ Failed to read existing k305 history: {exc}; writing fresh snapshot")

    result.to_csv(output_file, index=False)

    print(f"  ✓ Saved {output_file} ({len(result)} rows total)")
    return True


if __name__ == "__main__":
    PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ok = k305(
        resources_file=str(PROJECT_ROOT / "config" / "Resources.csv"),
        output_dir=str(PROJECT_ROOT / "output"),
    )
    sys.exit(0 if ok else 1)
