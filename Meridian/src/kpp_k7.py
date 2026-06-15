#!/usr/bin/env python3
"""
KPP K7 - Task Completion by Employee
Aggregates count of completed tasks (Task and Sub-Task) per employee.
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings


def get_description():
    """Return KPI description."""
    return "Task Completion - Aggregates count of completed tasks (Task and Sub-Task) per employee"


def k7(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K7: Aggregate completed tasks and generate k7-data.csv output.
    
    Args:
        resources_file (str): Path to Resources.csv file
        jira_issues_file (str): Path to JIRAIssues.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k7-data.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K7 - Task Completion")
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
        # Filter for completed tasks and sub-tasks
        issues = df[
            (df['Status'] == 'Done') & 
            (df['Issue Type'].isin(['Task', 'Sub-Task']))
        ].copy()
        
        # Parse Updated date (completion date)
        issues['Updated'] = pd.to_datetime(issues['Updated'], errors='coerce')
        
        # Keep only rows with valid data
        issues = issues[
            (issues['Assignee'].notna()) &
            (issues['Updated'].notna())
        ]
        
        print(f"  ✓ Loaded {len(issues)} completed tasks")
    except Exception as e:
        print(f"  ✗ Error loading JIRA issues file: {e}")
        return False
    
    if issues.empty:
        print("  ⚠ Warning: No completed tasks found")
        # Create empty output file with headers
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year', 
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        print(f"{'='*60}\n")
        return True
    
    # Merge issues with resources
    print("Aggregating task completions...")
    merged = issues.merge(
        resources,
        left_on='Assignee',
        right_on='JIRA Name',
        how='inner'
    )
    
    if merged.empty:
        print("  ⚠ Warning: No matching records found between JIRA issues and Resources")
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year', 
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        print(f"{'='*60}\n")
        return True
    
    print(f"  ✓ Matched {len(merged)} tasks to employees")
    
    # Add time period columns based on completion date (Updated)
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
    
    # Aggregate by different time periods (count tasks completed)
    weekly_agg = merged.groupby(['SAPID', 'Name', 'Week']).size().reset_index(name='count')
    monthly_agg = merged.groupby(['SAPID', 'Name', 'Month']).size().reset_index(name='count')
    quarterly_agg = merged.groupby(['SAPID', 'Name', 'Quarter']).size().reset_index(name='count')
    annual_agg = merged.groupby(['SAPID', 'Name', 'FiscalYear']).size().reset_index(name='count')
    
    # Get all employees who completed tasks
    all_employees = merged[['SAPID', 'Name']].drop_duplicates()
    
    # Combine aggregations per employee
    result = []
    for _, emp_row in all_employees.iterrows():
        sapid = emp_row['SAPID']
        emp_name = emp_row['Name']
        
        # Get counts for current periods
        weekly_data = weekly_agg[(weekly_agg['SAPID'] == sapid) & (weekly_agg['Week'] == current_week)]
        weekly_count = int(weekly_data['count'].sum()) if not weekly_data.empty else 0
        
        monthly_data = monthly_agg[(monthly_agg['SAPID'] == sapid) & (monthly_agg['Month'] == current_month)]
        monthly_count = int(monthly_data['count'].sum()) if not monthly_data.empty else 0
        
        quarterly_data = quarterly_agg[(quarterly_agg['SAPID'] == sapid) & (quarterly_agg['Quarter'] == current_quarter)]
        quarterly_count = int(quarterly_data['count'].sum()) if not quarterly_data.empty else 0
        
        annual_data = annual_agg[(annual_agg['SAPID'] == sapid) & (annual_agg['FiscalYear'] == current_fiscal_year)]
        annual_count = int(annual_data['count'].sum()) if not annual_data.empty else 0
        
        result.append({
            'SAPID': sapid,
            'Name': emp_name,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'Weekly': weekly_count,
            'Monthly': monthly_count,
            'Quarterly': quarterly_count,
            'Annual': annual_count
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
