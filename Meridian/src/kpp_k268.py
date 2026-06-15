#!/usr/bin/env python3
"""
KPP K268 - Code Generation Ratio (k227 / k1)
Computes the ratio of total GIT lines committed (k227) to Copilot-generated
lines (k1) per employee, for each reporting period.

If k1 (Copilot LOC) is 0 for a period, the ratio is set to 0.
If either dependent file is missing or stale, dependent KPIs are re-run first.
Any error in individual ratio computation falls back to 0.
"""

import pandas as pd
import os
from datetime import date


def get_description():
    """Return KPI description."""
    return (
        "Code Generation Ratio (k227 / k1). "
        "Individual: GIT LOC committed divided by Copilot LOC; 9999 sentinel when Copilot LOC = 0 (RED — no AI usage). "
        "Team/Scrum aggregation: sum(k227) / sum(k1) using only Developer-role members, "
        "so numerator and denominator share the same member base and 9999 sentinel rows do not inflate the average."
    )


def _ensure_kpi_current(kpi_label, data_file, current_date_str,
                        resources_file, jira_issues_file, github_commits_file,
                        output_dir, fiscal_start_month, current_date):
    """
    Check that data_file exists and has a row for current_date_str.
    If not, run the corresponding KPI to refresh it.
    Returns True if data is available (after possible refresh), False on failure.
    """
    needs_run = True
    if os.path.exists(data_file):
        try:
            df = pd.read_csv(data_file)
            if not df.empty and current_date_str in df['CurrentDate'].astype(str).values:
                needs_run = False
                print(f"  ✓ {kpi_label} data is current")
        except Exception as e:
            print(f"  ⚠ Could not read {kpi_label} data: {e}")
    else:
        print(f"  ⚠ {kpi_label} data file not found")

    if needs_run:
        print(f"  ↻ Running {kpi_label} to refresh data...")
        try:
            if kpi_label == 'K227':
                from kpp_k227 import k227
                ok = k227(
                    resources_file=resources_file,
                    github_commits_file=github_commits_file,
                    output_dir=output_dir,
                    fiscal_start_month=fiscal_start_month,
                    current_date=current_date
                )
            elif kpi_label == 'K1':
                from kpp_k1 import k1
                ok = k1(
                    resources_file=resources_file,
                    jira_issues_file=jira_issues_file,
                    output_dir=output_dir,
                    fiscal_start_month=fiscal_start_month,
                    current_date=current_date
                )
            else:
                ok = False
            if not ok:
                print(f"  ✗ {kpi_label} refresh failed")
                return False
            print(f"  ✓ {kpi_label} refreshed")
        except Exception as e:
            print(f"  ✗ Error running {kpi_label}: {e}")
            return False
    return True


def k268(resources_file, jira_issues_file, output_dir,
         github_commits_file=None, fiscal_start_month=4, current_date=None):
    """
    K268: Code Generation Ratio = k227 / k1 per employee per period.

    Args:
        resources_file (str): Path to Resources.csv
        jira_issues_file (str): Path to JIRAIssues.csv (passed through to k1 if needed)
        output_dir (str): Directory for output files
        github_commits_file (str): Path to github_commits.csv (passed through to k227 if needed)
        fiscal_start_month (int): Fiscal year start month (default: 4 for April)
        current_date (date): Reporting date (default: today)

    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k268-data.csv')
    k227_file   = os.path.join(output_dir, 'k227-data.csv')
    k1_file     = os.path.join(output_dir, 'k1-data.csv')

    if current_date is None:
        current_date = date.today()

    current_date_str = current_date.strftime('%Y%m%d')

    print(f"\n{'='*60}")
    print(f"KPP K268 - Code Generation Ratio (k227 / k1)")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")

    # ── 1. Ensure k227 and k1 are current ────────────────────────────────────
    print("Checking dependent KPIs...")

    k227_ok = _ensure_kpi_current(
        'K227', k227_file, current_date_str,
        resources_file, jira_issues_file, github_commits_file,
        output_dir, fiscal_start_month, current_date
    )
    k1_ok = _ensure_kpi_current(
        'K1', k1_file, current_date_str,
        resources_file, jira_issues_file, github_commits_file,
        output_dir, fiscal_start_month, current_date
    )

    if not k227_ok:
        print("  ✗ K227 data unavailable – cannot compute K268")
        return False
    if not k1_ok:
        print("  ✗ K1 data unavailable – cannot compute K268")
        return False

    # ── 2. Load both datasets (latest date only) ──────────────────────────────
    def load_latest(filepath, label):
        df = pd.read_csv(filepath)
        df['SAPID'] = df['SAPID'].astype(str)
        df['CurrentDate'] = pd.to_numeric(df['CurrentDate'], errors='coerce').fillna(0).astype(int).astype(str)
        latest = df['CurrentDate'].max()
        df = df[df['CurrentDate'] == latest].copy()

        # Ensure numeric KPI columns are clean
        for col in ['Weekly', 'Monthly', 'Quarterly', 'Annual']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        # Collapse duplicate SAPID rows (can happen due to historical merges)
        # Use max for KPI values so accidental duplicate rows don't double count.
        if df['SAPID'].duplicated().any():
            df = (
                df.sort_values(['CurrentDate', 'SAPID'])
                  .groupby('SAPID', as_index=False)
                  .agg({
                      'CurrentDate': 'max',
                      'Week': 'last',
                      'Month': 'last',
                      'Quarter': 'last',
                      'Year': 'last',
                      'Name': 'last',
                      'Weekly': 'max',
                      'Monthly': 'max',
                      'Quarterly': 'max',
                      'Annual': 'max',
                  })
            )

        print(f"  ✓ Loaded {len(df)} {label} records (date {latest})")
        return df

    try:
        df_k227 = load_latest(k227_file, 'K227')
        df_k1   = load_latest(k1_file,   'K1')
    except Exception as e:
        print(f"  ✗ Error loading dependency data: {e}")
        return False

    # ── 3. Index both by SAPID for fast lookup ────────────────────────────────
    k227_idx = df_k227.set_index('SAPID')
    k1_idx   = df_k1.set_index('SAPID')

    # Only include SAPIDs that have k227 data — users with no GIT commits
    # should NOT get a row at all (avoids a 0 value on a "minimize" KPI showing as green).
    # EXCEPTION: if a user has k1 data (Copilot usage) but no k227 (no GIT commits),
    # they must still appear with a sentinel value (9999) so the dashboard shows RED —
    # it means they used Copilot but committed nothing, which is a genuine problem.
    all_sapids = sorted(set(k227_idx.index) | set(k1_idx.index))

    # Grab period labels from whichever file has them (prefer k227)
    ref_row = df_k227.iloc[0] if not df_k227.empty else df_k1.iloc[0]
    week_label    = ref_row['Week']
    month_label   = ref_row['Month']
    quarter_label = ref_row['Quarter']
    year_label    = ref_row['Year']

    # Build SAPID → Name lookup (from both files)
    sapid_name = {}
    for df in [df_k227, df_k1]:
        for _, row in df.iterrows():
            sapid_name[str(row['SAPID'])] = row['Name']

    # ── 4. Compute ratio for each employee ────────────────────────────────────
    def safe_ratio(num, den):
        """
        Return num/den rounded to 4 dp.
        Special cases:
          - den (k1) == 0 → 9999  (no Copilot usage → force RED)
          - num (k227) == 0, den > 0 → 0.0  (no GIT commits is OK → GREEN)
          - any error → 9999  (conservative / red)
        """
        try:
            num = float(num)
            den = float(den)
            if den == 0:
                # k1=0: developer hasn't used Copilot → red
                return 9999.0
            if num == 0:
                # k227=0 but k1>0: no GIT commits is acceptable → green
                return 0.0
            return round(num / den, 4)
        except Exception:
            return 9999.0

    result = []
    for sapid in all_sapids:
        try:
            k227_row = k227_idx.loc[sapid] if sapid in k227_idx.index else None
            k1_row   = k1_idx.loc[sapid]   if sapid in k1_idx.index   else None

            w227 = float(k227_row['Weekly'])    if k227_row is not None else 0.0
            m227 = float(k227_row['Monthly'])   if k227_row is not None else 0.0
            q227 = float(k227_row['Quarterly']) if k227_row is not None else 0.0
            a227 = float(k227_row['Annual'])    if k227_row is not None else 0.0

            w1   = float(k1_row['Weekly'])    if k1_row is not None else 0.0
            m1   = float(k1_row['Monthly'])   if k1_row is not None else 0.0
            q1   = float(k1_row['Quarterly']) if k1_row is not None else 0.0
            a1   = float(k1_row['Annual'])    if k1_row is not None else 0.0

            result.append({
                'CurrentDate': current_date_str,
                'Week':        week_label,
                'Month':       month_label,
                'Quarter':     quarter_label,
                'Year':        year_label,
                'SAPID':       sapid,
                'Name':        sapid_name.get(sapid, ''),
                'Weekly':      safe_ratio(w227, w1),
                'Monthly':     safe_ratio(m227, m1),
                'Quarterly':   safe_ratio(q227, q1),
                'Annual':      safe_ratio(a227, a1),
            })
        except Exception as e:
            print(f"  ⚠ Error computing ratio for SAPID {sapid}: {e} – defaulting to 0")
            result.append({
                'CurrentDate': current_date_str,
                'Week': week_label, 'Month': month_label,
                'Quarter': quarter_label, 'Year': year_label,
                'SAPID': sapid, 'Name': sapid_name.get(sapid, ''),
                'Weekly': 0.0, 'Monthly': 0.0, 'Quarterly': 0.0, 'Annual': 0.0,
            })

    new_df = pd.DataFrame(result)[[
        'CurrentDate', 'Week', 'Month', 'Quarter', 'Year',
        'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
    ]]

    # Merge with existing file — purge ALL rows for today's date first,
    # then append new_df. This prevents stale rows (e.g. from a previous
    # broader run) from persisting for employees no longer in new_df.
    if os.path.exists(output_file):
        try:
            existing_df = pd.read_csv(output_file)
            existing_df['SAPID'] = existing_df['SAPID'].astype(str)
            existing_df['CurrentDate'] = existing_df['CurrentDate'].astype(str)
            new_df['SAPID'] = new_df['SAPID'].astype(str)
            new_df['CurrentDate'] = new_df['CurrentDate'].astype(str)

            # Remove ALL rows for today — not just those in new_df
            existing_df = existing_df[existing_df['CurrentDate'] != current_date_str]

            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df = combined_df.sort_values(['CurrentDate', 'SAPID'])
            combined_df.to_csv(output_file, index=False)
            print(f"  ✓ Updated {output_file} with {len(new_df)} records")
        except Exception as e:
            print(f"  ⚠ Error reading existing file, creating new: {e}")
            new_df.to_csv(output_file, index=False)
            print(f"  ✓ Created {output_file} with {len(new_df)} records")
    else:
        new_df.to_csv(output_file, index=False)
        print(f"  ✓ Created {output_file} with {len(new_df)} records")

    print(f"{'='*60}\n")
    return True


def compute_k268_ratio_for_members(
    resources_file: str,
    output_dir: str,
    member_names: list,
    period: str = 'Annual',
) -> float:
    """Compute team-level k268 = sum(k227) / sum(k1) for the given members.

    Returns the ratio (float) or 9999.0 if no Copilot usage (k1 total == 0).
    Using sum/sum instead of avg(individual ratios) avoids the 9999 sentinel
    values inflating the team average.
    """
    import csv as _csv

    k227_file = os.path.join(output_dir, 'k227-data.csv')
    k1_file   = os.path.join(output_dir, 'k1-data.csv')
    col_map   = {'Weekly': 'Weekly', 'Monthly': 'Monthly', 'Quarterly': 'Quarterly', 'Annual': 'Annual'}
    col       = col_map.get(period, 'Annual')

    # Build name -> SAPID map from Resources.csv
    name_to_sapid: dict = {}
    try:
        with open(resources_file) as f:
            for row in _csv.DictReader(f):
                name = str(row.get('Name', '')).strip()
                raw  = str(row.get('SAPID', '')).strip()
                try:
                    name_to_sapid[name] = str(int(float(raw)))
                except Exception:
                    pass
    except Exception:
        pass

    member_sapids = {name_to_sapid[n] for n in member_names if n in name_to_sapid}

    def _sum_for_members(filepath: str) -> float:
        """Sum `col` values for member_sapids using the latest row per SAPID.
        Mirrors read_kpi_data behaviour: last row in the file wins for each SAPID,
        so members whose most recent data point is on an earlier date are still counted.
        """
        total = 0.0
        try:
            df = pd.read_csv(filepath)
            df['SAPID'] = df['SAPID'].astype(str)
            df['CurrentDate'] = df['CurrentDate'].astype(str)
            # Keep latest row per SAPID (sort ascending → last row = latest date)
            df = df.sort_values('CurrentDate')
            latest_per_sapid = df.groupby('SAPID', as_index=False).last()
            for _, row in latest_per_sapid.iterrows():
                if str(row['SAPID']) in member_sapids:
                    total += float(row.get(col, 0) or 0)
        except Exception:
            pass
        return total

    total_k227 = _sum_for_members(k227_file)
    total_k1   = _sum_for_members(k1_file)

    if total_k1 == 0:
        return 9999.0  # No one used Copilot → RED
    return round(total_k227 / total_k1, 4)
