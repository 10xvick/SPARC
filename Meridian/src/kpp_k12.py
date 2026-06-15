#!/usr/bin/env python3
"""
KPP K12 - Reviews Approved by Employee
Aggregates count of reviews where employee is marked as approver.
Includes all employees from Resources.csv; employees without approvals get 0 values.
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings


def get_description():
    """Return KPI description."""
    return "Reviews Approved - Aggregates count of reviews where employee is marked as approver (includes all employees, with 0 for no approvals)"


def k12(resources_file, github_commits_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K12: Aggregate reviews approved and generate k12-data.csv output.
    
    Args:
        resources_file (str): Path to Resources.csv file
        github_commits_file (str): Path to github_commits.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k12-data.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K12 - Reviews Approved")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")
    
    # Load resources
    print("Loading resources data...")
    try:
        df = pd.read_csv(resources_file)
        resources = df[['SAPID', 'Name', 'GitHUB Name']].copy()
        resources['SAPID'] = resources['SAPID'].fillna(0).astype(int).astype(str)
        resources['Name'] = resources['Name'].fillna('').astype(str)
        resources['GitHUB Name'] = resources['GitHUB Name'].fillna('').astype(str).str.strip()

        all_employees = resources[['SAPID', 'Name']].drop_duplicates().copy()

        # Keep only valid GitHub names for approver mapping, but preserve all employees for output
        resources_for_mapping = resources[
            (resources['GitHUB Name'] != '') &
            (resources['GitHUB Name'] != '-NA-')
        ].copy()

        print(f"  ✓ Loaded {len(all_employees)} resources")
        print(f"  ✓ Found {len(resources_for_mapping)} resources with valid GitHUB Name")
    except Exception as e:
        print(f"  ✗ Error loading resources file: {e}")
        return False
    
    if all_employees.empty:
        print("  ✗ No resources data loaded")
        return False
    
    # Load GitHub commits
    print("Loading GitHub commits data...")
    try:
        df = pd.read_csv(github_commits_file)
        # Filter for rows where count_review_flag is true
        commits = df[df['count_review_flag'] == True].copy()
        
        # Parse date
        commits['date'] = pd.to_datetime(commits['date'], errors='coerce')
        
        # Keep only rows with valid data and approver
        commits = commits[
            (commits['approver'].notna()) &
            (commits['approver'] != '') &
            (commits['date'].notna())
        ]
        
        print(f"  ✓ Loaded {len(commits)} commits with approvers")
    except Exception as e:
        print(f"  ✗ Error loading GitHub commits file: {e}")
        return False
    
    if commits.empty:
        print("  ⚠ Warning: No commits with approvers found")
        merged = pd.DataFrame(columns=['SAPID', 'Name', 'date'])
    else:
        # Merge commits with resources using approver and GitHUB Name
        print("Mapping approvers to employees...")
        merged = commits.merge(
            resources_for_mapping,
            left_on='approver',
            right_on='GitHUB Name',
            how='inner'
        )

        if merged.empty:
            print("  ⚠ Warning: No matching approvers found in Resources")
        else:
            print(f"  ✓ Matched {len(merged)} approvals to employees")

    if not merged.empty:
        # Add time period columns
        merged['Week'] = merged['date'].apply(get_week_number)
        merged['Month'] = merged['date'].apply(get_month_string)
        merged['Quarter'] = merged['date'].apply(get_quarter_string)
        merged['FiscalYear'] = merged['date'].apply(lambda dt: get_fiscal_year(dt, fiscal_start_month))
    
    # Calculate current period values
    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_fiscal_year = get_fiscal_year(current_dt, fiscal_start_month)
    
    # Aggregate by different time periods (count reviews approved)
    if not merged.empty:
        weekly_agg = merged.groupby(['SAPID', 'Name', 'Week']).size().reset_index(name='count')
        monthly_agg = merged.groupby(['SAPID', 'Name', 'Month']).size().reset_index(name='count')
        quarterly_agg = merged.groupby(['SAPID', 'Name', 'Quarter']).size().reset_index(name='count')
        annual_agg = merged.groupby(['SAPID', 'Name', 'FiscalYear']).size().reset_index(name='count')
    else:
        weekly_agg = pd.DataFrame(columns=['SAPID', 'Name', 'Week', 'count'])
        monthly_agg = pd.DataFrame(columns=['SAPID', 'Name', 'Month', 'count'])
        quarterly_agg = pd.DataFrame(columns=['SAPID', 'Name', 'Quarter', 'count'])
        annual_agg = pd.DataFrame(columns=['SAPID', 'Name', 'FiscalYear', 'count'])
    
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

    print(f"  ✓ Computed review counts for {len(aggregated)} employees")
    
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
