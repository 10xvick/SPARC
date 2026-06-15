#!/usr/bin/env python3
"""
KPP K138 - Person Utilization
Measures person utilization based on sprint story points and resource allocation.
"""

import pandas as pd
import os
from datetime import date, timedelta
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings


def get_description():
    """Return KPI description."""
    return "Person Utilization - Measures person utilization based on sprint story points and resource allocation"


def k138(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K138: Calculate person utilization and generate k138-data.csv output.
    
    Args:
        resources_file (str): Path to Resources.csv file
        jira_issues_file (str): Path to JIRAIssues.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k138-data.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K138 - Person Utilization")
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
        
        # Filter for issues with Sprint, Sprint.endDate, Story Points, and Assignee
        sprint_issues = df[
            (df['Sprint'].notna()) &
            (df['Sprint.endDate'].notna()) &
            (df['Story Points'].notna()) &
            (df['Assignee'].notna())
        ].copy()
        
        # Parse Sprint.endDate
        sprint_issues['Sprint.endDate'] = pd.to_datetime(sprint_issues['Sprint.endDate'], errors='coerce', utc=True)
        sprint_issues = sprint_issues[sprint_issues['Sprint.endDate'].notna()]
        
        # Convert Story Points to numeric
        sprint_issues['Story Points'] = pd.to_numeric(sprint_issues['Story Points'], errors='coerce').fillna(0)
        
        # Merge with resources to get Scrum team for each assignee
        sprint_issues = sprint_issues.merge(
            resources[['JIRA Name', 'Scrum']],
            left_on='Assignee',
            right_on='JIRA Name',
            how='left'
        )
        
        # Filter out issues without Scrum team mapping
        sprint_issues = sprint_issues[sprint_issues['Scrum'].notna()]
        
        print(f"  ✓ Loaded {len(sprint_issues)} issues with sprint and scrum data")
    except Exception as e:
        print(f"  ✗ Error loading JIRA issues file: {e}")
        return False
    
    if sprint_issues.empty:
        print("  ⚠ No sprint issues found")
        return False
    
    # Calculate current period values
    current_dt_obj = pd.Timestamp(current_date, tz='UTC')
    current_week = get_week_number(current_dt_obj)
    current_month = get_month_string(current_dt_obj)
    current_quarter = get_quarter_string(current_dt_obj)
    current_fiscal_year = get_fiscal_year(current_dt_obj, fiscal_start_month)
    
    # Calculate next week's dates for weekly calculation
    next_week_start = current_dt_obj + timedelta(days=7)
    next_week_end = current_dt_obj + timedelta(days=14)
    
    # Aggregate sprint data by Scrum team
    print("Analyzing sprint utilization by scrum team...")
    
    # Group by Scrum and Sprint to get total story points and unique assignees per sprint per scrum
    sprint_scrum_summary = sprint_issues.groupby(['Scrum', 'Sprint']).agg({
        'Story Points': 'sum',
        'Assignee': 'nunique',
        'Sprint.endDate': 'first'  # Each sprint should have one end date
    }).reset_index()
    
    sprint_scrum_summary.columns = ['Scrum', 'Sprint', 'Total Story Points', 'Unique Resources', 'Sprint End Date']
    
    print(f"  ✓ Analyzed {len(sprint_scrum_summary)} unique scrum-sprint combinations")
    
    # Calculate utilization for each scrum team and period
    print("Calculating utilization per scrum team...")
    
    scrum_utilization = {}
    
    for scrum_team in sprint_scrum_summary['Scrum'].unique():
        scrum_sprints = sprint_scrum_summary[sprint_scrum_summary['Scrum'] == scrum_team]
        
        # Weekly: Sprints ending in current week or next week
        weekly_sprints = scrum_sprints[
            (scrum_sprints['Sprint End Date'] >= current_dt_obj) &
            (scrum_sprints['Sprint End Date'] < next_week_end)
        ]
        
        if len(weekly_sprints) > 0:
            weekly_story_points = weekly_sprints['Total Story Points'].sum()
            weekly_avg_resources = weekly_sprints['Unique Resources'].mean()
            num_weekly_sprints = len(weekly_sprints)
            # Divide by number of sprints to get per-sprint utilization
            weekly_utilization = (weekly_story_points / num_weekly_sprints) / weekly_avg_resources if weekly_avg_resources > 0 else 0
        else:
            weekly_utilization = 0
        
        # Monthly: Sprints ending in current month
        monthly_sprints = scrum_sprints[
            scrum_sprints['Sprint End Date'].apply(lambda x: get_month_string(x)) == current_month
        ]
        
        if len(monthly_sprints) > 0:
            monthly_story_points = monthly_sprints['Total Story Points'].sum()
            monthly_avg_resources = monthly_sprints['Unique Resources'].mean()
            num_monthly_sprints = len(monthly_sprints)
            # Divide by number of sprints to get per-sprint utilization
            monthly_utilization = (monthly_story_points / num_monthly_sprints) / monthly_avg_resources if monthly_avg_resources > 0 else 0
        else:
            monthly_utilization = 0
        
        # Quarterly: Sprints ending in current quarter
        quarterly_sprints = scrum_sprints[
            scrum_sprints['Sprint End Date'].apply(lambda x: get_quarter_string(x)) == current_quarter
        ]
        
        if len(quarterly_sprints) > 0:
            quarterly_story_points = quarterly_sprints['Total Story Points'].sum()
            quarterly_avg_resources = quarterly_sprints['Unique Resources'].mean()
            num_quarterly_sprints = len(quarterly_sprints)
            # Divide by number of sprints to get per-sprint utilization
            quarterly_utilization = (quarterly_story_points / num_quarterly_sprints) / quarterly_avg_resources if quarterly_avg_resources > 0 else 0
        else:
            quarterly_utilization = 0
        
        # Annual: Sprints ending in current fiscal year
        annual_sprints = scrum_sprints[
            scrum_sprints['Sprint End Date'].apply(lambda x: get_fiscal_year(x, fiscal_start_month)) == current_fiscal_year
        ]
        
        if len(annual_sprints) > 0:
            annual_story_points = annual_sprints['Total Story Points'].sum()
            annual_avg_resources = annual_sprints['Unique Resources'].mean()
            num_annual_sprints = len(annual_sprints)
            # Divide by number of sprints to get per-sprint utilization
            annual_utilization = (annual_story_points / num_annual_sprints) / annual_avg_resources if annual_avg_resources > 0 else 0
        else:
            annual_utilization = 0
        
        scrum_utilization[scrum_team] = {
            'Weekly': weekly_utilization,
            'Monthly': monthly_utilization,
            'Quarterly': quarterly_utilization,
            'Annual': annual_utilization
        }
    
    print(f"  ✓ Calculated utilization for {len(scrum_utilization)} scrum teams")
    
    # Create result - one row per employee with their scrum team's utilization values
    print("Creating output for all employees...")
    result = []
    
    for _, resource in resources.iterrows():
        scrum_team = resource['Scrum'] if pd.notna(resource['Scrum']) else 'Unknown'
        
        # Get utilization for this employee's scrum team
        utilization = scrum_utilization.get(scrum_team, {
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
            'SAPID': resource['SAPID'],
            'Name': resource['Name'],
            'Weekly': round(utilization['Weekly'], 2),
            'Monthly': round(utilization['Monthly'], 2),
            'Quarterly': round(utilization['Quarterly'], 2),
            'Annual': round(utilization['Annual'], 2)
        })
    
    result_df = pd.DataFrame(result)
    
    print(f"  ✓ Created utilization data for {len(result_df)} employees")
    
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
    
    parser = argparse.ArgumentParser(description='Compute KPP K138 - Person Utilization')
    parser.add_argument('--resources', default='../config/Resources.csv', help='Path to Resources.csv')
    parser.add_argument('--jira-issues', default='../output/JIRAIssues.csv', help='Path to JIRA issues CSV')
    parser.add_argument('--output', default='../output', help='Output directory')
    parser.add_argument('--date', default=date.today().strftime('%Y%m%d'), help='Current date (YYYYMMDD)')
    parser.add_argument('--fiscal-month', type=int, default=4, help='Fiscal year start month (1-12)')
    
    args = parser.parse_args()
    
    success = k138(
        resources_file=args.resources,
        jira_issues_file=args.jira_issues,
        output_dir=args.output,
        fiscal_start_month=args.fiscal_month,
        current_date=date.today()
    )
    
    exit(0 if success else 1)
