#!/usr/bin/env python3
"""
KPP K16 - Bugs Detected
Counts bugs created in each time period, excluding Invalid and Duplicate bugs.
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings


def get_description():
    """Return KPI description."""
    return "Bugs Detected - Counts bugs created in each time period, excluding Invalid and Duplicate bugs"


def k16(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K16: Count bugs detected and generate k16-data.csv output.
    
    Args:
        resources_file (str): Path to Resources.csv file
        jira_issues_file (str): Path to JIRAIssues.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k16-data.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K16 - Bugs Detected")
    print(f"Date: {current_date_str}")
    print('='*60)
    
    # Load resources
    print("Loading resources data...")
    try:
        resources = pd.read_csv(resources_file)
        # Convert SAPID to string, handling NaN values and removing .0 suffix
        resources['SAPID'] = pd.to_numeric(resources['SAPID'], errors='coerce')
        resources = resources[resources['SAPID'].notna()]
        resources['SAPID'] = resources['SAPID'].astype(int).astype(str)
        print(f"  ✓ Loaded {len(resources)} resources")
    except Exception as e:
        print(f"  ✗ Error loading resources file: {e}")
        return False
    
    if resources.empty:
        print("  ✗ No resources data loaded")
        return False
    
    # Load JIRA issues
    print("Loading JIRA issues data...")
    try:
        df = pd.read_csv(jira_issues_file)
        
        # Filter for Bug issues, excluding Invalid and Duplicate
        bugs = df[
            (df['Issue Type'] == 'Bug') &
            (~df['Status'].isin(['Invalid', 'Duplicate'])) &
            (df['Reporter'].notna())
        ].copy()
        
        # Parse Created date
        bugs['Created'] = pd.to_datetime(bugs['Created'], errors='coerce')
        bugs = bugs[bugs['Created'].notna()]
        
        print(f"  ✓ Loaded {len(bugs)} valid bugs")
    except Exception as e:
        print(f"  ✗ Error loading JIRA issues file: {e}")
        return False
    
    if bugs.empty:
        print("  ⚠ No bugs found")
        # Still create output with zero counts for all employees
    
    # Calculate current period values
    current_dt_obj = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt_obj)
    current_month = get_month_string(current_dt_obj)
    current_quarter = get_quarter_string(current_dt_obj)
    current_fiscal_year = get_fiscal_year(current_dt_obj, fiscal_start_month)
    
    # Helper functions for filtering
    def is_in_week(created_dt, target_week):
        return get_week_number(created_dt) == target_week
    
    def is_in_month(created_dt, target_month):
        return get_month_string(created_dt) == target_month
    
    def is_in_quarter(created_dt, target_quarter):
        return get_quarter_string(created_dt) == target_quarter
    
    def is_in_fiscal_year(created_dt, target_year):
        return get_fiscal_year(created_dt, fiscal_start_month) == target_year
    
    # Count bugs by reporter for each period
    print("Counting bugs by reporter for each time period...")
    
    # Initialize counts dictionary
    bug_counts = {}
    
    if not bugs.empty:
        for reporter in bugs['Reporter'].unique():
            reporter_bugs = bugs[bugs['Reporter'] == reporter]
            
            # Weekly: bugs created in current week
            weekly_count = reporter_bugs[reporter_bugs['Created'].apply(
                lambda x: is_in_week(x, current_week)
            )].shape[0]
            
            # Monthly: bugs created in current month
            monthly_count = reporter_bugs[reporter_bugs['Created'].apply(
                lambda x: is_in_month(x, current_month)
            )].shape[0]
            
            # Quarterly: bugs created in current quarter
            quarterly_count = reporter_bugs[reporter_bugs['Created'].apply(
                lambda x: is_in_quarter(x, current_quarter)
            )].shape[0]
            
            # Annual: bugs created in current fiscal year
            annual_count = reporter_bugs[reporter_bugs['Created'].apply(
                lambda x: is_in_fiscal_year(x, current_fiscal_year)
            )].shape[0]
            
            bug_counts[reporter] = {
                'Weekly': weekly_count,
                'Monthly': monthly_count,
                'Quarterly': quarterly_count,
                'Annual': annual_count
            }
    
    # Merge with resources to get SAPID and Name
    print("Merging with resources data...")
    result = []
    
    for _, resource in resources.iterrows():
        jira_name = resource['JIRA Name']
        sapid = resource['SAPID']
        name = resource['Name']
        
        # Get counts for this employee
        counts = bug_counts.get(jira_name, {
            'Weekly': 0,
            'Monthly': 0,
            'Quarterly': 0,
            'Annual': 0
        })
        
        result.append({
            'CurrentDate': current_date_str,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'SAPID': sapid,
            'Name': name,
            'Weekly': counts['Weekly'],
            'Monthly': counts['Monthly'],
            'Quarterly': counts['Quarterly'],
            'Annual': counts['Annual']
        })
    
    result_df = pd.DataFrame(result)
    
    # Count employees with bugs
    employees_with_bugs = (result_df[['Weekly', 'Monthly', 'Quarterly', 'Annual']].sum(axis=1) > 0).sum()
    print(f"  ✓ Computed bug counts for {len(result_df)} employees ({employees_with_bugs} with bugs)")
    
    # Append to existing data or create new
    if os.path.exists(output_file):
        existing_df = pd.read_csv(output_file)
        # Remove existing records for current date
        existing_df = existing_df[existing_df['CurrentDate'].astype(str) != current_date_str]
        # Append new records
        final_df = pd.concat([existing_df, result_df], ignore_index=True)
    else:
        final_df = result_df
    
    # Save to CSV
    final_df.to_csv(output_file, index=False)
    
    if os.path.exists(output_file):
        action = "Updated" if len(final_df) > len(result_df) else "Created"
        print(f"  ✓ {action} {output_file} with {len(result_df)} records")
    else:
        print(f"  ✗ Failed to create {output_file}")
        return False
    
    print('='*60)
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Compute KPP K16 - Bugs Detected')
    parser.add_argument('--resources', default='../config/Resources.csv', help='Path to Resources.csv')
    parser.add_argument('--jira-issues', default='../output/JIRAIssues.csv', help='Path to JIRA issues CSV')
    parser.add_argument('--output', default='../output', help='Output directory')
    parser.add_argument('--date', default=date.today().strftime('%Y%m%d'), help='Current date (YYYYMMDD)')
    parser.add_argument('--fiscal-month', type=int, default=4, help='Fiscal year start month (1-12)')
    
    args = parser.parse_args()
    
    success = k16(
        resources_file=args.resources,
        jira_issues_file=args.jira_issues,
        output_dir=args.output,
        fiscal_start_month=args.fiscal_month,
        current_date=date.today()
    )
    
    exit(0 if success else 1)
