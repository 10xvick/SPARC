#!/usr/bin/env python3
"""
KPP K259 - Technical Debt (Unplanned Pending Defects)
Counts open unplanned bugs in To Do/equivalent states at Team level.
Applies each team's count to all members of that team.
"""

import os
import re
import json
from datetime import date, datetime

import pandas as pd

from kpi_helpers import get_fiscal_year, get_month_string, get_quarter_string, get_week_number


OPEN_TODO_STATUSES = {
    'to do',
    'todo',
    'open',
    'new',
    'backlog',
    'selected for development',
    'selected for dev',
    'triage',
    'reopened',
}

UNPLANNED_SPRINT_TOKENS = {
    '',
    'nan',
    'none',
    '-na-',
}


def get_description():
    """Return KPI description."""
    return "Technical Debt - Counts open unplanned bugs/tickets in To Do/equivalent states at Team level"


def _normalize_text(value):
    """Normalize text values for matching."""
    if pd.isna(value):
        return ''
    return str(value).strip().lower()


def _parse_current_date(current_date):
    """Parse current_date into a date object."""
    if current_date is None:
        return date.today()

    if isinstance(current_date, str):
        return datetime.strptime(current_date, '%Y%m%d').date()

    return current_date


def _build_assignee_team_map(resources_df):
    """Build lookup from assignee name to team using both Name and JIRA Name."""
    assignee_team_map = {}

    for _, row in resources_df.iterrows():
        team = row.get('Team')
        if pd.isna(team) or not str(team).strip():
            continue

        normalized_team = str(team).strip()
        for column in ['Name', 'JIRA Name']:
            key = _normalize_text(row.get(column, ''))
            if not key or key in {'-na-', 'na'}:
                continue
            if key not in assignee_team_map:
                assignee_team_map[key] = normalized_team

    return assignee_team_map


def _extract_key_prefix(key_value):
    """Extract issue key prefix (e.g. FSO from FSO-123)."""
    match = re.match(r'^([A-Za-z]+)-', str(key_value or ''))
    if not match:
        return ''
    return match.group(1).upper()


def _build_prefix_team_map(all_bugs_df):
    """
    Infer a prefix-to-team mapping using majority assignee team among mapped issues.
    """
    mapped = all_bugs_df[all_bugs_df['assignee_team'].notna()].copy()
    if mapped.empty:
        return {}

    prefix_counts = (
        mapped
        .groupby(['prefix', 'assignee_team'])
        .size()
        .reset_index(name='count')
    )

    prefix_team_map = {}
    for prefix, group in prefix_counts.groupby('prefix'):
        if not prefix:
            continue
        best_row = group.sort_values(['count', 'assignee_team'], ascending=[False, True]).iloc[0]
        prefix_team_map[prefix] = best_row['assignee_team']

    return prefix_team_map


def _load_config_prefix_team_mapping(resources_file):
    """Load explicit JIRA prefix->team mapping from jira_config.json."""
    config_dir = os.path.dirname(os.path.abspath(resources_file))
    jira_config_path = os.path.join(config_dir, 'jira_config.json')

    if not os.path.exists(jira_config_path):
        return {}

    try:
        with open(jira_config_path, 'r', encoding='utf-8') as file_handle:
            jira_config = json.load(file_handle)
    except Exception:
        return {}

    raw_mapping = jira_config.get('prefix_team_mapping', {})
    if not isinstance(raw_mapping, dict):
        return {}

    normalized_mapping = {}
    for prefix, team in raw_mapping.items():
        normalized_prefix = str(prefix).strip().upper()
        normalized_team = str(team).strip()
        if normalized_prefix and normalized_team:
            normalized_mapping[normalized_prefix] = normalized_team

    return normalized_mapping


def _assign_team(issue_row, known_teams, prefix_team_map, config_prefix_team_map):
    """
    Assign issue to team using deterministic fallback order:
    1) Explicit mapping from jira_config.json (prefix_team_mapping)
    2) Exact prefix == team
    3) Mapped assignee team
    4) Inferred team from prefix majority mapping
    """
    prefix = issue_row.get('prefix', '')
    assignee_team = issue_row.get('assignee_team')

    config_mapped_team = config_prefix_team_map.get(prefix)
    if config_mapped_team in known_teams:
        return config_mapped_team

    if prefix in known_teams:
        return prefix

    if pd.notna(assignee_team) and assignee_team in known_teams:
        return assignee_team

    inferred_team = prefix_team_map.get(prefix)
    if inferred_team in known_teams:
        return inferred_team

    return None


def k259(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K259: Technical Debt - Open unplanned bugs in To Do/equivalent states.

    Team-level KPI: each member gets the same value as their team.
    """
    output_file = os.path.join(output_dir, 'k259-data.csv')

    current_dt = _parse_current_date(current_date)
    current_date_str = current_dt.strftime('%Y%m%d')

    print(f"\n{'=' * 60}")
    print('KPP K259 - Technical Debt (Unplanned Pending Defects)')
    print(f'Date: {current_date_str}')
    print(f"{'=' * 60}")

    print('Loading resources data...')
    try:
        resources_df = pd.read_csv(resources_file)
        resources_df['SAPID'] = pd.to_numeric(resources_df['SAPID'], errors='coerce')
        resources_df = resources_df[resources_df['SAPID'].notna()].copy()
        resources_df['SAPID'] = resources_df['SAPID'].astype(int).astype(str)
        resources_df['Team'] = resources_df['Team'].fillna('').astype(str).str.strip()
        print(f"  ✓ Loaded {len(resources_df)} resources")
    except Exception as exc:
        print(f'  ✗ Error loading resources: {exc}')
        return False

    if resources_df.empty:
        print('  ✗ No resources data available')
        return False

    known_teams = set(resources_df['Team'][resources_df['Team'] != ''].unique())
    assignee_team_map = _build_assignee_team_map(resources_df)
    config_prefix_team_map = _load_config_prefix_team_mapping(resources_file)
    if config_prefix_team_map:
        print(f"  ✓ Loaded {len(config_prefix_team_map)} prefix-team mappings from jira_config.json")
    else:
        print('  ⚠ No prefix-team mapping found in jira_config.json (using fallback attribution)')

    print('Loading JIRA issues data...')
    try:
        jira_df = pd.read_csv(jira_issues_file)
        print(f"  ✓ Loaded {len(jira_df)} JIRA issues")
    except Exception as exc:
        print(f'  ✗ Error loading JIRA issues: {exc}')
        return False

    if jira_df.empty:
        print('  ⚠ Warning: JIRA issues data is empty')

    # Prepare all bugs (used to learn prefix->team fallback mapping)
    all_bugs_df = jira_df[
        jira_df['Issue Type'].fillna('').astype(str).str.strip().str.lower() == 'bug'
    ].copy()
    all_bugs_df['prefix'] = all_bugs_df['Key'].apply(_extract_key_prefix)
    all_bugs_df['assignee_key'] = all_bugs_df['Assignee'].apply(_normalize_text)
    all_bugs_df['assignee_team'] = all_bugs_df['assignee_key'].map(assignee_team_map)

    prefix_team_map = _build_prefix_team_map(all_bugs_df)

    # Filter to unplanned open bugs in To Do/equivalent statuses
    technical_debt_df = all_bugs_df.copy()
    technical_debt_df['status_normalized'] = technical_debt_df['Status'].apply(_normalize_text)
    technical_debt_df['sprint_normalized'] = technical_debt_df['Sprint'].apply(_normalize_text)

    technical_debt_df = technical_debt_df[
        technical_debt_df['status_normalized'].isin(OPEN_TODO_STATUSES)
    ]
    technical_debt_df = technical_debt_df[
        technical_debt_df['sprint_normalized'].isin(UNPLANNED_SPRINT_TOKENS)
    ]

    if technical_debt_df.empty:
        print('  ⚠ No open unplanned bugs found for K259')
        team_counts = {}
        unattributed_count = 0
    else:
        technical_debt_df['assigned_team'] = technical_debt_df.apply(
            lambda row: _assign_team(row, known_teams, prefix_team_map, config_prefix_team_map),
            axis=1
        )

        unattributed_count = int(technical_debt_df['assigned_team'].isna().sum())
        team_counts = technical_debt_df['assigned_team'].value_counts(dropna=True).to_dict()

        print(f"  ✓ Open unplanned bugs considered: {len(technical_debt_df)}")
        print(f"  ✓ Attributed to teams: {len(technical_debt_df) - unattributed_count}")
        if unattributed_count > 0:
            print(f"  ⚠ Unattributed issues: {unattributed_count}")

    # Calculate current period values
    current_ts = pd.Timestamp(current_dt)
    current_week = get_week_number(current_ts)
    current_month = get_month_string(current_ts)
    current_quarter = get_quarter_string(current_ts)
    current_fiscal_year = get_fiscal_year(current_ts, fiscal_start_month)

    # Build output: each employee gets their team's value
    output_rows = []
    for _, resource in resources_df.iterrows():
        team_name = resource.get('Team', '')
        team_value = int(team_counts.get(team_name, 0))

        output_rows.append({
            'CurrentDate': current_date_str,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'SAPID': resource['SAPID'],
            'Name': resource['Name'],
            'Weekly': team_value,
            'Monthly': team_value,
            'Quarterly': team_value,
            'Annual': team_value,
        })

    result_df = pd.DataFrame(output_rows)

    # Merge with existing output while replacing current date rows
    if os.path.exists(output_file):
        try:
            existing_df = pd.read_csv(output_file)
            existing_df['CurrentDate'] = existing_df['CurrentDate'].astype(str)
            existing_df = existing_df[existing_df['CurrentDate'] != current_date_str]
            final_df = pd.concat([existing_df, result_df], ignore_index=True)
        except Exception as exc:
            print(f"  ⚠ Warning: Could not merge with existing output ({exc}), rewriting file")
            final_df = result_df
    else:
        final_df = result_df

    final_df.to_csv(output_file, index=False)
    print(f"  ✓ Wrote {output_file} with {len(result_df)} records")

    teams_with_debt = sum(1 for value in team_counts.values() if value > 0)
    print(f"  ✓ Teams with technical debt issues: {teams_with_debt}")
    if team_counts:
        top_teams = sorted(team_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        top_display = ', '.join([f"{team}:{count}" for team, count in top_teams])
        print(f"  ✓ Top team counts: {top_display}")

    print(f"{'=' * 60}\n")
    return True


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Compute KPP K259 - Technical Debt (Unplanned Pending Defects)')
    parser.add_argument('--resources', default='../config/Resources.csv', help='Path to Resources.csv')
    parser.add_argument('--jira-issues', default='../output/JIRAIssues.csv', help='Path to JIRAIssues.csv')
    parser.add_argument('--date', default=datetime.now().strftime('%Y%m%d'), help='Current date (YYYYMMDD)')
    parser.add_argument('--fiscal-month', type=int, default=4, help='Fiscal year start month (1-12)')
    parser.add_argument('--output', default='../output', help='Output folder path')

    args = parser.parse_args()

    success = k259(
        resources_file=args.resources,
        jira_issues_file=args.jira_issues,
        output_dir=args.output,
        fiscal_start_month=args.fiscal_month,
        current_date=args.date,
    )

    raise SystemExit(0 if success else 1)