#!/usr/bin/env python3
"""
KPP K300 - Test Code to Total Code Ratio
Calculates the ratio of test code lines to total code lines committed per individual.
Target: 20% or higher (to maximize test coverage in commits)
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year


def get_description():
    """Return KPI description."""
    return "Test Code to Total Code Ratio - Percentage of test code lines relative to total code lines committed (Target: 20%+)"


def k300(resources_file, github_commits_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K300: Test Code to Total Code Ratio at Individual Level.
    
    Calculates the percentage of test code lines (added) relative to total code lines (added).
    Formula: (Test Code Lines / Total Code Lines) * 100
    
    Args:
        resources_file (str): Path to Resources.csv file
        github_commits_file (str): Path to github_commits.csv file (not used directly)
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k300-data.csv')
    commit_files_file = os.path.join(output_dir, 'github_commit_files.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K300 - Test Code to Total Code Ratio")
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
        
        # Ensure lines_added is numeric
        files_df['lines_added'] = pd.to_numeric(files_df['lines_added'], errors='coerce').fillna(0)
        
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
                'Weekly': 0.0,
                'Monthly': 0.0,
                'Quarterly': 0.0,
                'Annual': 0.0
            })
        
        output_df = pd.DataFrame(result)
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created {output_file} with {len(output_df)} records (all zeros)")
        return True
    
    # Merge with resources to get SAPID and Name
    print("Matching files with resources...")
    files_merged = files_df.merge(
        resources, 
        left_on='author', 
        right_on='GitHUB Name', 
        how='inner'
    )
    
    if files_merged.empty:
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
                'Weekly': 0.0,
                'Monthly': 0.0,
                'Quarterly': 0.0,
                'Annual': 0.0
            })
        
        output_df = pd.DataFrame(result)
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created {output_file} with {len(output_df)} records (all zeros)")
        return True
    
    print(f"  ✓ Matched {len(files_merged)} file changes to resources")
    
    # Add time period columns
    files_merged['Week'] = files_merged['date'].apply(get_week_number)
    files_merged['Month'] = files_merged['date'].apply(get_month_string)
    files_merged['Quarter'] = files_merged['date'].apply(get_quarter_string)
    files_merged['FiscalYear'] = files_merged['date'].apply(lambda x: get_fiscal_year(x, fiscal_start_month))
    
    # Separate test and total code
    test_files = files_merged[files_merged['category'] == 'test'].copy()
    total_files = files_merged.copy()
    
    print(f"  ✓ Test files: {len(test_files)}, Total files: {len(total_files)}")
    
    # Calculate current period values
    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_fiscal_year = get_fiscal_year(current_dt, fiscal_start_month)
    
    print("Calculating test code ratio per individual...")
    
    # Calculate ratio per individual for each period
    result = []
    
    for _, emp in resources.iterrows():
        sapid = emp['SAPID']
        name = emp['Name']
        github_name = emp['GitHUB Name']
        
        # Filter files for this individual
        emp_test = test_files[test_files['SAPID'] == sapid]
        emp_total = total_files[total_files['SAPID'] == sapid]
        
        # Calculate test and total lines for each period
        def calculate_ratio(test_df, total_df, period_col, period_val):
            test_lines = test_df[test_df[period_col] == period_val]['lines_added'].sum()
            total_lines = total_df[total_df[period_col] == period_val]['lines_added'].sum()
            if total_lines > 0:
                return round((test_lines / total_lines) * 100, 2)
            return 0.0
        
        weekly_ratio = calculate_ratio(emp_test, emp_total, 'Week', current_week)
        monthly_ratio = calculate_ratio(emp_test, emp_total, 'Month', current_month)
        quarterly_ratio = calculate_ratio(emp_test, emp_total, 'Quarter', current_quarter)
        annual_ratio = calculate_ratio(emp_test, emp_total, 'FiscalYear', current_fiscal_year)
        
        result.append({
            'CurrentDate': current_date_str,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'SAPID': sapid,
            'Name': name,
            'Weekly': weekly_ratio,
            'Monthly': monthly_ratio,
            'Quarterly': quarterly_ratio,
            'Annual': annual_ratio
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
    print(f"  ✓ {len(non_zero)} individuals with code contributions")
    if len(non_zero) > 0:
        avg_ratio = new_df[new_df['Annual'] > 0]['Annual'].mean()
        max_ratio = new_df['Annual'].max()
        min_ratio = new_df[new_df['Annual'] > 0]['Annual'].min() if len(non_zero) > 0 else 0
        above_target = len(new_df[new_df['Annual'] >= 20.0])
        
        print(f"  ✓ Average test code ratio: {avg_ratio:.2f}%")
        print(f"  ✓ Range: {min_ratio:.2f}% - {max_ratio:.2f}%")
        print(f"  ✓ Contributors meeting 20% target: {above_target}/{len(non_zero)}")
    
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
    
    success = k300(
        resources_file=str(resources_file),
        github_commits_file=str(github_commits_file),
        output_dir=str(output_dir)
    )
    
    sys.exit(0 if success else 1)
