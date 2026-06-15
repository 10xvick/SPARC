#!/usr/bin/env python3
"""
KPP K205 - Unique JIRA Committed by Employee
Counts unique JIRA issues (Task and Sub-task) completed per employee on weekly, monthly, quarterly, and annual basis.
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings


def get_description():
    """Return KPI description."""
    return "Unique JIRA Committed - Counts unique JIRA issues (Task/Sub-task) completed per employee"


def k205(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K205: Count unique JIRA issues completed and generate k205-data.csv output.
    
    Args:
        resources_file (str): Path to Resources.csv file
        jira_issues_file (str): Path to JIRAIssues.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k205-data.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K205 - Unique JIRA Committed")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")
    
    # Load resources
    print("Loading resources data...")
    try:
        df = pd.read_csv(resources_file)
        resources = df[['SAPID', 'Name', 'JIRA Name']].copy()
        resources['SAPID'] = resources['SAPID'].fillna(0).astype(int).astype(str)
        resources = resources[resources['JIRA Name'].notna()]
        resources = resources[resources['JIRA Name'] != '-NA-']
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
        # Filter for Task and Sub-task issue types with Status = Done
        completed = df[
            (df['Status'] == 'Done') & 
            (df['Issue Type'].isin(['Task', 'Sub-task']))
        ].copy()
        
        completed['Updated'] = pd.to_datetime(completed['Updated'], errors='coerce')
        completed = completed[
            (completed['Assignee'].notna()) & 
            (completed['Updated'].notna()) &
            (completed['Key'].notna())
        ]
        print(f"  ✓ Loaded {len(completed)} completed Task/Sub-task issues")
    except Exception as e:
        print(f"  ✗ Error loading JIRA issues file: {e}")
        return False
    
    if completed.empty:
        print("  ⚠ Warning: No completed Task/Sub-task JIRA issues found")
        # Create empty output file with headers
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year', 
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        return True
    
    # Count unique JIRA issues
    print("Counting unique JIRA issues...")
    
    # Merge issues with resources
    merged = completed.merge(resources, left_on='Assignee', right_on='JIRA Name', how='inner')
    
    if merged.empty:
        print("  ⚠ Warning: No matching records found between JIRA issues and Resources")
        return False
    
    # Add time period columns
    merged['Week'] = merged['Updated'].apply(get_week_number)
    merged['Month'] = merged['Updated'].apply(get_month_string)
    merged['Quarter'] = merged['Updated'].apply(get_quarter_string)
    merged['FiscalYear'] = merged['Updated'].apply(lambda dt: get_fiscal_year(dt, fiscal_start_month))
    
    # Calculate current period values
    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_fiscal_year = get_fiscal_year(current_dt, fiscal_start_month)
    
    # Count unique JIRA keys by different time periods
    weekly_agg = merged.groupby(['SAPID', 'Name', 'Week'])['Key'].nunique().reset_index()
    weekly_agg.rename(columns={'Key': 'Count'}, inplace=True)
    
    monthly_agg = merged.groupby(['SAPID', 'Name', 'Month'])['Key'].nunique().reset_index()
    monthly_agg.rename(columns={'Key': 'Count'}, inplace=True)
    
    quarterly_agg = merged.groupby(['SAPID', 'Name', 'Quarter'])['Key'].nunique().reset_index()
    quarterly_agg.rename(columns={'Key': 'Count'}, inplace=True)
    
    annual_agg = merged.groupby(['SAPID', 'Name', 'FiscalYear'])['Key'].nunique().reset_index()
    annual_agg.rename(columns={'Key': 'Count'}, inplace=True)
    
    # Get all employees who have completed work
    all_employees = merged[['SAPID', 'Name']].drop_duplicates()
    
    # Combine aggregations per employee
    result = []
    for _, emp_row in all_employees.iterrows():
        sapid = emp_row['SAPID']
        emp_name = emp_row['Name']
        
        # Get unique JIRA count for current periods
        weekly_data = weekly_agg[(weekly_agg['SAPID'] == sapid) & (weekly_agg['Week'] == current_week)]
        weekly_count = weekly_data['Count'].sum() if not weekly_data.empty else 0
        
        monthly_data = monthly_agg[(monthly_agg['SAPID'] == sapid) & (monthly_agg['Month'] == current_month)]
        monthly_count = monthly_data['Count'].sum() if not monthly_data.empty else 0
        
        quarterly_data = quarterly_agg[(quarterly_agg['SAPID'] == sapid) & (quarterly_agg['Quarter'] == current_quarter)]
        quarterly_count = quarterly_data['Count'].sum() if not quarterly_data.empty else 0
        
        annual_data = annual_agg[(annual_agg['SAPID'] == sapid) & (annual_agg['FiscalYear'] == current_fiscal_year)]
        annual_count = annual_data['Count'].sum() if not annual_data.empty else 0
        
        result.append({
            'SAPID': sapid,
            'Name': emp_name,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'Weekly': int(weekly_count),
            'Monthly': int(monthly_count),
            'Quarterly': int(quarterly_count),
            'Annual': int(annual_count)
        })
    
    aggregated = pd.DataFrame(result)
    
    if aggregated.empty:
        print("  ⚠ No aggregated data to write")
        return False
    
    # Prepare output data
    aggregated.insert(0, 'CurrentDate', current_date_str)
    column_order = [
        'CurrentDate', 'Week', 'Month', 'Quarter', 'Year',
        'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
    ]
    new_df = aggregated[column_order]
    
    # Load existing data if file exists and merge
    if os.path.exists(output_file):
        try:
            existing_df = pd.read_csv(output_file)
            existing_df['SAPID'] = existing_df['SAPID'].astype(str)
            new_df['SAPID'] = new_df['SAPID'].astype(str)
            existing_df['CurrentDate'] = existing_df['CurrentDate'].astype(str)
            
            # Remove entries for same employee and date (override logic)
            # Append new data
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


if __name__ == '__main__':
    """Run K205 KPI evaluation when executed directly."""
    import sys
    from pathlib import Path
    
    # Get the project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # Define file paths
    resources_file = project_root / 'config' / 'Resources.csv'
    jira_issues_file = project_root / 'output' / 'JIRAIssues.csv'
    output_dir = project_root / 'output'
    
    # Run the KPI
    success = k205(str(resources_file), str(jira_issues_file), str(output_dir))
    
    sys.exit(0 if success else 1)
