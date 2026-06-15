#!/usr/bin/env python3
"""
KPP K56 - Number of UI Screens Developed
Counts unique UI screen files developed/modified per individual using github_commit_files data.
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year


def get_description():
    """Return KPI description."""
    return "Number of UI Screens Developed - Counts unique UI screen files developed/modified per individual"


def k56(resources_file, github_commits_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K56: Number of UI Screens Developed at Individual Level.
    
    Args:
        resources_file (str): Path to Resources.csv file
        github_commits_file (str): Path to github_commits.csv file (not used directly)
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k56-data.csv')
    commit_files_file = os.path.join(output_dir, 'github_commit_files.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K56 - Number of UI Screens Developed")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")
    
    # Load resources
    print("Loading resources data...")
    try:
        resources_df = pd.read_csv(resources_file)
        resources = resources_df[['SAPID', 'Name', 'GitHUB Name']].copy()
        resources['SAPID'] = resources['SAPID'].fillna(0).astype(int).astype(str)
        resources = resources[resources['GitHUB Name'].notna()]
        resources = resources[resources['GitHUB Name'] != '-NA-']
        print(f"  ✓ Loaded {len(resources)} resources")
    except Exception as e:
        print(f"  ✗ Error loading resources file: {e}")
        return False
    
    if resources.empty:
        print("  ✗ No resources data loaded")
        return False
    
    # Load commit files data
    print("Loading GitHub commit files data...")
    if not os.path.exists(commit_files_file):
        print(f"  ✗ Error: {commit_files_file} not found")
        print(f"      Please run 'python github_fetch.py fetch' to generate file details")
        return False
    
    try:
        files_df = pd.read_csv(commit_files_file)
        files_df['date'] = pd.to_datetime(files_df['date'], errors='coerce')
        files_df = files_df[files_df['date'].notna()]
        print(f"  ✓ Loaded {len(files_df)} file changes")
    except Exception as e:
        print(f"  ✗ Error loading commit files: {e}")
        return False
    
    if files_df.empty:
        print("  ⚠ Warning: No commit file data found")
        # Create output with 0 values for all employees
        result = []
        current_week = get_week_number(pd.Timestamp(current_date))
        current_month = get_month_string(pd.Timestamp(current_date))
        current_quarter = get_quarter_string(pd.Timestamp(current_date))
        current_fiscal_year = get_fiscal_year(pd.Timestamp(current_date), fiscal_start_month)
        
        for _, emp in resources.iterrows():
            result.append({
                'CurrentDate': current_date_str,
                'Week': current_week,
                'Month': current_month,
                'Quarter': current_quarter,
                'Year': current_fiscal_year,
                'SAPID': emp['SAPID'],
                'Name': emp['Name'],
                'Weekly': 0,
                'Monthly': 0,
                'Quarterly': 0,
                'Annual': 0
            })
        
        output_df = pd.DataFrame(result)
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created {output_file} with {len(output_df)} records (all zeros)")
        return True
    
    # Filter for screen files only (high and medium confidence)
    print("Filtering for UI screen files...")
    screen_files = files_df[
        (files_df['is_screen'] == True) & 
        (files_df['confidence'].isin(['high', 'medium']))
    ].copy()
    
    if screen_files.empty:
        print("  ⚠ Warning: No screen files found")
        # Create output with 0 values
        result = []
        current_week = get_week_number(pd.Timestamp(current_date))
        current_month = get_month_string(pd.Timestamp(current_date))
        current_quarter = get_quarter_string(pd.Timestamp(current_date))
        current_fiscal_year = get_fiscal_year(pd.Timestamp(current_date), fiscal_start_month)
        
        for _, emp in resources.iterrows():
            result.append({
                'CurrentDate': current_date_str,
                'Week': current_week,
                'Month': current_month,
                'Quarter': current_quarter,
                'Year': current_fiscal_year,
                'SAPID': emp['SAPID'],
                'Name': emp['Name'],
                'Weekly': 0,
                'Monthly': 0,
                'Quarterly': 0,
                'Annual': 0
            })
        
        output_df = pd.DataFrame(result)
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created {output_file} with {len(output_df)} records (all zeros)")
        return True
    
    print(f"  ✓ Found {len(screen_files)} screen file changes")
    
    # Merge with resources to get SAPID and Name
    print("Matching screen files with resources...")
    screen_files_merged = screen_files.merge(
        resources, 
        left_on='author', 
        right_on='GitHUB Name', 
        how='inner'
    )
    
    if screen_files_merged.empty:
        print("  ⚠ Warning: No matching records found between commit files and Resources")
        # Create output with 0 values
        result = []
        current_week = get_week_number(pd.Timestamp(current_date))
        current_month = get_month_string(pd.Timestamp(current_date))
        current_quarter = get_quarter_string(pd.Timestamp(current_date))
        current_fiscal_year = get_fiscal_year(pd.Timestamp(current_date), fiscal_start_month)
        
        for _, emp in resources.iterrows():
            result.append({
                'CurrentDate': current_date_str,
                'Week': current_week,
                'Month': current_month,
                'Quarter': current_quarter,
                'Year': current_fiscal_year,
                'SAPID': emp['SAPID'],
                'Name': emp['Name'],
                'Weekly': 0,
                'Monthly': 0,
                'Quarterly': 0,
                'Annual': 0
            })
        
        output_df = pd.DataFrame(result)
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created {output_file} with {len(output_df)} records (all zeros)")
        return True
    
    print(f"  ✓ Matched {len(screen_files_merged)} screen changes to resources")
    
    # Add time period columns
    screen_files_merged['Week'] = screen_files_merged['date'].apply(get_week_number)
    screen_files_merged['Month'] = screen_files_merged['date'].apply(get_month_string)
    screen_files_merged['Quarter'] = screen_files_merged['date'].apply(get_quarter_string)
    screen_files_merged['FiscalYear'] = screen_files_merged['date'].apply(lambda x: get_fiscal_year(x, fiscal_start_month))
    
    # Calculate current period values
    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_fiscal_year = get_fiscal_year(current_dt, fiscal_start_month)
    
    print("Counting unique screens per individual...")
    
    # Count unique screen files (filepath) per individual for each period
    result = []
    
    for _, emp in resources.iterrows():
        sapid = emp['SAPID']
        name = emp['Name']
        github_name = emp['GitHUB Name']
        
        # Filter screens for this individual
        emp_screens = screen_files_merged[screen_files_merged['SAPID'] == sapid]
        
        # Count unique screen files for each period
        weekly_screens = emp_screens[emp_screens['Week'] == current_week]['filepath'].nunique()
        monthly_screens = emp_screens[emp_screens['Month'] == current_month]['filepath'].nunique()
        quarterly_screens = emp_screens[emp_screens['Quarter'] == current_quarter]['filepath'].nunique()
        annual_screens = emp_screens[emp_screens['FiscalYear'] == current_fiscal_year]['filepath'].nunique()
        
        result.append({
            'CurrentDate': current_date_str,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'SAPID': sapid,
            'Name': name,
            'Weekly': weekly_screens,
            'Monthly': monthly_screens,
            'Quarterly': quarterly_screens,
            'Annual': annual_screens
        })
    
    output_df = pd.DataFrame(result)
    
    # Prepare output data
    column_order = [
        'CurrentDate', 'Week', 'Month', 'Quarter', 'Year',
        'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
    ]
    new_df = output_df[column_order]
    
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
    
    # Print summary
    non_zero = new_df[new_df['Annual'] > 0]
    print(f"  ✓ {len(non_zero)} individuals with screen development work")
    if len(non_zero) > 0:
        total_screens = new_df['Annual'].sum()
        print(f"  ✓ Total unique screens developed: {total_screens}")
    
    print(f"{'='*60}\n")
    return True


if __name__ == '__main__':
    # For testing
    import sys
    from pathlib import Path
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    resources_file = project_root / 'config' / 'Resources.csv'
    github_commits_file = project_root / 'output' / 'github_commits.csv'
    output_dir = project_root / 'output'
    
    success = k56(
        resources_file=str(resources_file),
        github_commits_file=str(github_commits_file),
        output_dir=str(output_dir)
    )
    
    sys.exit(0 if success else 1)
