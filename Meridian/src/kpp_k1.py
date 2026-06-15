#!/usr/bin/env python3
"""
KPP K1 - Copilot LOC (Lines of Code Added)
Tracks lines of code added via Copilot per employee on weekly, monthly, quarterly, and annual basis.
"""

import pandas as pd
import os
from datetime import date


def get_description():
    """Return KPI description."""
    return "Copilot LOC - Tracks lines of code added via Copilot by employee"


def k1(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K1: Copilot LOC aggregation from copilot_loc_metrics.csv.

    Args:
        resources_file (str): Path to Resources.csv file
        jira_issues_file (str): Path to JIRAIssues.csv file (unused, kept for interface compatibility)
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)

    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k1-data.csv')

    if current_date is None:
        current_date = date.today()

    current_date_str = current_date.strftime('%Y%m%d')

    print(f"\n{'='*60}")
    print(f"KPP K1 - Copilot LOC (Lines of Code Added)")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")

    # Load resources
    print("Loading resources data...")
    try:
        df_resources = pd.read_csv(resources_file)
        resources = df_resources[['SAPID', 'Name', 'copilot_user']].copy()
        resources['SAPID'] = resources['SAPID'].fillna(0).astype(int).astype(str)
        resources = resources[
            (resources['copilot_user'].notna()) &
            (resources['copilot_user'] != 'not_mapped')
        ]
        print(f"  ✓ Loaded {len(resources)} resources with Copilot mapping")
    except Exception as e:
        print(f"  ✗ Error loading resources file: {e}")
        return False

    if resources.empty:
        print("  ✗ No resources with Copilot mapping found")
        return False

    # Load copilot LOC metrics file
    print("Loading Copilot LOC metrics data...")
    copilot_loc_file = os.path.join(os.path.dirname(output_dir), 'output', 'copilot_loc_metrics.csv')

    try:
        df_metrics = pd.read_csv(copilot_loc_file)
        print(f"  ✓ Loaded {len(df_metrics)} Copilot LOC metrics records")
    except Exception as e:
        print(f"  ✗ Error loading Copilot LOC metrics file: {e}")
        print(f"     Expected at: {copilot_loc_file}")
        return False

    if df_metrics.empty:
        print("  ⚠ Warning: No Copilot LOC metrics data found")
        return False

    # Build login → SAPID/Name lookup
    login_to_employee = {
        row['copilot_user'].strip(): {'SAPID': row['SAPID'], 'Name': row['Name']}
        for _, row in resources.iterrows()
        if row['copilot_user'].strip()
    }

    # Map metrics rows to employees
    result = []
    for _, metric_row in df_metrics.iterrows():
        user_login = metric_row['user_login'].strip()

        if user_login in login_to_employee:
            emp_info = login_to_employee[user_login]

            result.append({
                'CurrentDate': metric_row['CurrentDate'],
                'Week':        metric_row['Week'],
                'Month':       metric_row['Month'],
                'Quarter':     metric_row['Quarter'],
                'Year':        metric_row['Year'],
                'SAPID':       emp_info['SAPID'],
                'Name':        emp_info['Name'],
                'Weekly':      int(metric_row['loc_added_weekly']),
                'Monthly':     int(metric_row['loc_added_monthly']),
                'Quarterly':   int(metric_row['loc_added_quarterly']),
                'Annual':      int(metric_row['loc_added_annual']),
            })

    if not result:
        print("  ⚠ No matching records found")
        return False

    aggregated = pd.DataFrame(result)

    column_order = [
        'CurrentDate', 'Week', 'Month', 'Quarter', 'Year',
        'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
    ]
    new_df = aggregated[column_order]

    # Merge with existing file if present
    if os.path.exists(output_file):
        try:
            existing_df = pd.read_csv(output_file)
            existing_df['SAPID'] = existing_df['SAPID'].astype(str)
            new_df['SAPID'] = new_df['SAPID'].astype(str)
            existing_df['CurrentDate'] = existing_df['CurrentDate'].astype(str)
            new_df['CurrentDate'] = new_df['CurrentDate'].astype(str)

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
