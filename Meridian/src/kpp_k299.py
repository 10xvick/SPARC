#!/usr/bin/env python3
"""
KPP K299 - Total Test Code Lines Committed
Tracks total lines of test code (added) committed per individual using github_commit_files data.
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year


def get_description():
    """Return KPI description."""
    return "Total Test Code Lines Committed - Tracks total lines of test code (added) committed per individual"


def k299(resources_file, github_commits_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K299: Total Test Code Lines Committed at Individual Level.
    
    Counts the total lines of test code (lines_added) committed by each individual.
    Only includes files categorized as 'test' in github_commit_files.csv.
   
       Merge commits are excluded — they re-count code already captured in the
       individual feature commits and would inflate test-line counts.
   
       File rows are deduplicated by (commit_sha, filepath) before aggregation
       to avoid double-counting commits that appear in multiple branches.
       Matching is done by author_email for consistency with K227.
    
    Args:
        resources_file (str): Path to Resources.csv file
        github_commits_file (str): Path to github_commits.csv file (not used directly)
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k299-data.csv')
    commit_files_file = os.path.join(output_dir, 'github_commit_files.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K299 - Total Test Code Lines Committed")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")
    
    # Load resources
    print("Loading resources data...")
    try:
        resources_df = pd.read_csv(resources_file)
        resources = resources_df[['SAPID', 'Name', 'GIT Email']].copy()
        resources['SAPID'] = resources['SAPID'].fillna(0).astype(int).astype(str)
        resources = resources[resources['GIT Email'].notna()]
        resources = resources[resources['GIT Email'].str.strip() != '']
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

    # Deduplicate commit-file rows to prevent double-counting the same file
    # change when data is fetched from multiple branches.
    before_dedup = len(files_df)
    files_df = files_df.drop_duplicates(subset=['commit_sha', 'filepath', 'author_email'])
    dupes_removed = before_dedup - len(files_df)
    if dupes_removed:
        print(f"  ⚠ Removed {dupes_removed} duplicate file rows (same commit+filepath+email)")

    # Exclude merge commits so only authored commits are counted.
    merge_shas: set = set()
    if os.path.exists(github_commits_file):
        try:
            commits_df = pd.read_csv(github_commits_file, usecols=lambda c: c in ['commit_sha', 'message'])
            merge_pattern = r'^Merge (pull request|branch)\b'
            is_merge = commits_df['message'].str.match(merge_pattern, case=False, na=False)
            valid_sha = commits_df['commit_sha'].notna() & (
                commits_df['commit_sha'].astype(str).str.strip() != ''
            )
            merge_shas = set(commits_df[is_merge & valid_sha]['commit_sha'].astype(str))
            if merge_shas:
                before_merge = len(files_df)
                files_df = files_df[~files_df['commit_sha'].astype(str).isin(merge_shas)]
                merges_removed = before_merge - len(files_df)
                print(f"  ⚠ Excluded {merges_removed} file rows from {len(merge_shas)} merge commit SHAs")
        except Exception as exc:
            print(f"  ⚠ Could not load commits for merge exclusion: {exc}")

    # Fallback merge detection by message when available in files CSV.
    if 'message' in files_df.columns:
        merge_pattern = r'^Merge (pull request|branch)\b'
        msg_merge = files_df['message'].str.match(merge_pattern, case=False, na=False)
        before_msg_merge = len(files_df)
        files_df = files_df[~msg_merge]
        msg_removed = before_msg_merge - len(files_df)
        if msg_removed:
            print(f"  ⚠ Excluded {msg_removed} file rows by message-based merge detection")

    
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
    
    # Filter for test files only
    print("Filtering for test files...")
    test_files = files_df[files_df['category'] == 'test'].copy()
    
    if test_files.empty:
        print("  ⚠ Warning: No test files found")
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
    
    print(f"  ✓ Found {len(test_files)} test file changes")
    print(f"  ✓ Total test lines added: {test_files['lines_added'].sum():,.0f}")
    
    # Merge with resources to get SAPID and Name
    print("Matching test files with resources...")
    test_files_merged = test_files.merge(
        resources, 
        left_on='author_email',
        right_on='GIT Email',
        how='inner'
    )
    
    if test_files_merged.empty:
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
    
    print(f"  ✓ Matched {len(test_files_merged)} test file changes to resources")
    
    # Add time period columns
    test_files_merged['Week'] = test_files_merged['date'].apply(get_week_number)
    test_files_merged['Month'] = test_files_merged['date'].apply(get_month_string)
    test_files_merged['Quarter'] = test_files_merged['date'].apply(get_quarter_string)
    test_files_merged['FiscalYear'] = test_files_merged['date'].apply(lambda x: get_fiscal_year(x, fiscal_start_month))
    
    # Calculate current period values
    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_fiscal_year = get_fiscal_year(current_dt, fiscal_start_month)
    
    print("Calculating test code lines per individual...")
    
    # Sum test lines added per individual for each period
    result = []
    
    for _, emp in resources.iterrows():
        sapid = emp['SAPID']
        name = emp['Name']
        
        # Filter test files for this individual
        emp_tests = test_files_merged[test_files_merged['SAPID'] == sapid]
        
        # Sum lines added for each period
        weekly_lines = emp_tests[emp_tests['Week'] == current_week]['lines_added'].sum()
        monthly_lines = emp_tests[emp_tests['Month'] == current_month]['lines_added'].sum()
        quarterly_lines = emp_tests[emp_tests['Quarter'] == current_quarter]['lines_added'].sum()
        annual_lines = emp_tests[emp_tests['FiscalYear'] == current_fiscal_year]['lines_added'].sum()
        
        result.append({
            'CurrentDate': current_date_str,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'SAPID': sapid,
            'Name': name,
            'Weekly': int(weekly_lines),
            'Monthly': int(monthly_lines),
            'Quarterly': int(quarterly_lines),
            'Annual': int(annual_lines)
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
    print(f"  ✓ {len(non_zero)} individuals with test code contributions")
    if len(non_zero) > 0:
        total_test_lines = new_df['Annual'].sum()
        avg_lines = new_df[new_df['Annual'] > 0]['Annual'].mean()
        max_lines = new_df['Annual'].max()
        max_contributor = new_df[new_df['Annual'] == max_lines]['Name'].values[0] if max_lines > 0 else 'N/A'
        
        print(f"  ✓ Total test lines committed: {total_test_lines:,.0f}")
        print(f"  ✓ Average per contributor: {avg_lines:,.0f} lines")
        print(f"  ✓ Top contributor: {max_contributor} ({max_lines:,.0f} lines)")
    
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
    
    success = k299(
        resources_file=str(resources_file),
        github_commits_file=str(github_commits_file),
        output_dir=str(output_dir)
    )
    
    sys.exit(0 if success else 1)
