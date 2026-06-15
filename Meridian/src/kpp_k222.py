#!/usr/bin/env python3
"""
KPP K222 - LOC per Story Point
Calculates lines of code per story point using completed JIRAs and associated GitHub commits.
"""

import os
import re
from datetime import date
from typing import Dict, Iterable, Tuple

import pandas as pd

from kpi_helpers import get_fiscal_year, get_month_string, get_quarter_string, get_week_number


JIRA_KEY_PATTERN = re.compile(r'[A-Z][A-Z0-9]+-\d+')


def get_description():
    """Return KPI description."""
    return "LOC per Story Point - Total LOC linked to completed JIRAs divided by total story points"


def _extract_jira_keys(jira_id_value: str) -> list[str]:
    """Extract one or more JIRA keys from a jira_id cell."""
    if pd.isna(jira_id_value):
        return []
    return JIRA_KEY_PATTERN.findall(str(jira_id_value).upper())


def _resolve_period_context(period: str, fiscal_start_month: int, current_date: date) -> Tuple[str, str]:
    """Resolve period column name and current period value."""
    period_key = str(period).strip().lower()
    current_dt = pd.Timestamp(current_date)

    if period_key == 'weekly':
        return 'Week', get_week_number(current_dt)
    if period_key == 'monthly':
        return 'Month', get_month_string(current_dt)
    if period_key == 'quarterly':
        return 'Quarter', get_quarter_string(current_dt)
    return 'FiscalYear', get_fiscal_year(current_dt, fiscal_start_month)


def _prepare_k222_datasets(
    resources_file: str,
    jira_issues_file: str,
    github_commits_file: str,
    fiscal_start_month: int
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Prepare merged completed issues and LOC totals by JIRA key."""
    resources_df = pd.read_csv(resources_file)
    resources = resources_df[['SAPID', 'Name', 'JIRA Name']].copy()
    resources['SAPID'] = resources['SAPID'].fillna(0).astype(int).astype(str)
    resources = resources[resources['JIRA Name'].notna()]
    resources = resources[resources['JIRA Name'] != '-NA-']
    resources = resources[resources['JIRA Name'] != '']

    issues_df = pd.read_csv(jira_issues_file)
    done_issues = issues_df[issues_df['Status'] == 'Done'].copy()
    done_issues['Updated'] = pd.to_datetime(done_issues['Updated'], errors='coerce')
    done_issues['Story Points'] = pd.to_numeric(done_issues['Story Points'], errors='coerce')
    done_issues['Key'] = done_issues['Key'].astype(str).str.upper()

    done_issues = done_issues[
        (done_issues['Assignee'].notna()) &
        (done_issues['Updated'].notna()) &
        (done_issues['Key'].notna()) &
        (done_issues['Story Points'].notna()) &
        (done_issues['Story Points'] > 0)
    ]

    merged_issues = done_issues.merge(resources, left_on='Assignee', right_on='JIRA Name', how='inner')
    if merged_issues.empty:
        return merged_issues, {}

    merged_issues['Week'] = merged_issues['Updated'].apply(get_week_number)
    merged_issues['Month'] = merged_issues['Updated'].apply(get_month_string)
    merged_issues['Quarter'] = merged_issues['Updated'].apply(get_quarter_string)
    merged_issues['FiscalYear'] = merged_issues['Updated'].apply(lambda dt: get_fiscal_year(dt, fiscal_start_month))

    commits_df = pd.read_csv(github_commits_file)

    if 'lines_changed' in commits_df.columns:
        loc_values = pd.to_numeric(commits_df['lines_changed'], errors='coerce')
    else:
        loc_values = pd.Series([pd.NA] * len(commits_df), index=commits_df.index)

    if 'lines_added' in commits_df.columns and 'lines_deleted' in commits_df.columns:
        fallback_loc = (
            pd.to_numeric(commits_df['lines_added'], errors='coerce').fillna(0) +
            pd.to_numeric(commits_df['lines_deleted'], errors='coerce').fillna(0)
        )
        loc_values = loc_values.fillna(fallback_loc)

    commits_df['loc_value'] = loc_values.fillna(0).astype(float)

    jira_loc_totals: Dict[str, float] = {}
    for _, row in commits_df.iterrows():
        loc_value = float(row.get('loc_value', 0) or 0)
        if loc_value <= 0:
            continue

        jira_keys = set(_extract_jira_keys(row.get('jira_id', '')))
        if not jira_keys:
            continue

        for jira_key in jira_keys:
            jira_loc_totals[jira_key] = jira_loc_totals.get(jira_key, 0.0) + loc_value

    return merged_issues, jira_loc_totals


def compute_k222_ratio_for_members(
    resources_file: str,
    jira_issues_file: str,
    github_commits_file: str,
    member_names: Iterable[str],
    period: str,
    fiscal_start_month: int = 4,
    current_date: date | None = None
) -> Tuple[float, float, float, int]:
    """
    Compute K222 ratio for a group of members as ratio-of-sums.

    Returns:
        tuple: (ratio, total_loc, total_story_points, contributing_member_count)
    """
    if current_date is None:
        current_date = date.today()

    member_set = {name for name in member_names if name}
    if not member_set:
        return 0.0, 0.0, 0.0, 0

    merged_issues, jira_loc_totals = _prepare_k222_datasets(
        resources_file=resources_file,
        jira_issues_file=jira_issues_file,
        github_commits_file=github_commits_file,
        fiscal_start_month=fiscal_start_month
    )

    if merged_issues.empty:
        return 0.0, 0.0, 0.0, 0

    period_column, period_value = _resolve_period_context(period, fiscal_start_month, current_date)
    period_issues = merged_issues[
        (merged_issues['Name'].isin(member_set)) &
        (merged_issues[period_column] == period_value)
    ]

    if period_issues.empty:
        return 0.0, 0.0, 0.0, 0

    total_story_points = float(period_issues['Story Points'].sum())
    issue_keys = period_issues['Key'].dropna().astype(str).str.upper().unique()
    total_loc = float(sum(jira_loc_totals.get(key, 0.0) for key in issue_keys))
    ratio = (total_loc / total_story_points) if total_story_points > 0 else 0.0

    return ratio, total_loc, total_story_points, int(period_issues['Name'].nunique())


def k222(resources_file, jira_issues_file, github_commits_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K222: Calculate LOC per Story Point and generate k222-data.csv output.

    Args:
        resources_file (str): Path to Resources.csv file
        jira_issues_file (str): Path to JIRAIssues.csv file
        github_commits_file (str): Path to github_commits.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)

    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k222-data.csv')

    if current_date is None:
        current_date = date.today()

    current_date_str = current_date.strftime('%Y%m%d')

    print(f"\n{'='*60}")
    print("KPP K222 - LOC per Story Point")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")

    print("Loading and preparing JIRA/GitHub data...")
    try:
        merged_issues, jira_loc_totals = _prepare_k222_datasets(
            resources_file=resources_file,
            jira_issues_file=jira_issues_file,
            github_commits_file=github_commits_file,
            fiscal_start_month=fiscal_start_month
        )
    except Exception as e:
        print(f"  ✗ Error preparing data: {e}")
        return False

    if merged_issues.empty:
        print("  ⚠ Warning: No completed issues with story points found")
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year',
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        print(f"{'='*60}\n")
        return True

    current_week = get_week_number(pd.Timestamp(current_date))
    current_month = get_month_string(pd.Timestamp(current_date))
    current_quarter = get_quarter_string(pd.Timestamp(current_date))
    current_fiscal_year = get_fiscal_year(pd.Timestamp(current_date), fiscal_start_month)

    def calculate_ratio_map(period_column: str, period_value: str) -> Dict[tuple[str, str], float]:
        period_df = merged_issues[merged_issues[period_column] == period_value]
        ratio_map: Dict[tuple[str, str], float] = {}

        if period_df.empty:
            return ratio_map

        for (sapid, name), group in period_df.groupby(['SAPID', 'Name']):
            total_sp = float(group['Story Points'].sum())
            if total_sp <= 0:
                continue

            issue_keys = group['Key'].dropna().astype(str).str.upper().unique()
            total_loc = float(sum(jira_loc_totals.get(key, 0.0) for key in issue_keys))
            ratio_map[(str(sapid), str(name))] = total_loc / total_sp

        return ratio_map

    weekly_ratio = calculate_ratio_map('Week', current_week)
    monthly_ratio = calculate_ratio_map('Month', current_month)
    quarterly_ratio = calculate_ratio_map('Quarter', current_quarter)
    annual_ratio = calculate_ratio_map('FiscalYear', current_fiscal_year)

    all_employee_keys = set(weekly_ratio) | set(monthly_ratio) | set(quarterly_ratio) | set(annual_ratio)

    if not all_employee_keys:
        print("  ⚠ Warning: No LOC/SP ratios available for current periods")
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year',
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        print(f"{'='*60}\n")
        return True

    result = []
    for sapid, name in sorted(all_employee_keys, key=lambda item: item[0]):
        result.append({
            'SAPID': sapid,
            'Name': name,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'Weekly': round(weekly_ratio.get((sapid, name), 0.0), 2),
            'Monthly': round(monthly_ratio.get((sapid, name), 0.0), 2),
            'Quarterly': round(quarterly_ratio.get((sapid, name), 0.0), 2),
            'Annual': round(annual_ratio.get((sapid, name), 0.0), 2)
        })

    aggregated = pd.DataFrame(result)
    aggregated.insert(0, 'CurrentDate', current_date_str)
    column_order = [
        'CurrentDate', 'Week', 'Month', 'Quarter', 'Year',
        'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
    ]
    new_df = aggregated[column_order]

    if os.path.exists(output_file):
        try:
            existing_df = pd.read_csv(output_file)
            existing_df['SAPID'] = existing_df['SAPID'].astype(str)
            new_df['SAPID'] = new_df['SAPID'].astype(str)
            existing_df['CurrentDate'] = existing_df['CurrentDate'].astype(str)

            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=['CurrentDate', 'SAPID'], keep='last')
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
