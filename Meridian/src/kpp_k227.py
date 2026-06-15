#!/usr/bin/env python3
"""
KPP K227 - Lines of Code Added
Aggregates lines of code added from GitHub commits.
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings


def get_description():
    """Return KPI description."""
    return "Lines of Code Added - Aggregates lines of code added from GitHub commits"


def k227(resources_file, github_commits_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K227: Aggregate lines of code added and generate k227-data.csv output.
    
    Args:
        resources_file (str): Path to Resources.csv file
        github_commits_file (str): Path to github_commits.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k227-data.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K227 - Lines of Code Added")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")
    
    # Load resources
    print("Loading resources data...")
    try:
        df = pd.read_csv(resources_file)
        resources = df[['SAPID', 'Name', 'GIT Email']].copy()
        resources['SAPID'] = resources['SAPID'].fillna(0).astype(int).astype(str)
        resources = resources[resources['GIT Email'].notna()]
        resources = resources[resources['GIT Email'] != '']
        print(f"  ✓ Loaded {len(resources)} resources with Git emails")
    except Exception as e:
        print(f"  ✗ Error loading resources file: {e}")
        return False
    
    if resources.empty:
        print("  ✗ No resources data loaded")
        return False
    
    # Load GitHub commits
    print("Loading GitHub commits data...")
    try:
        df = pd.read_csv(github_commits_file)
        commits = df.copy()
        commits['date'] = pd.to_datetime(commits['date'], errors='coerce')
        commits['lines_added'] = pd.to_numeric(commits['lines_added'], errors='coerce')
        commits = commits[
            (commits['author_email'].notna()) &
            (commits['date'].notna()) &
            (commits['lines_added'].notna()) &
            (commits['lines_added'] >= 0)
        ]
        print(f"  ✓ Loaded {len(commits)} raw commit rows")

        # Exclude merge commits — they re-count code already captured in the
        # individual feature commits and inflate lines-added significantly.
        merge_pattern = r'^Merge (pull request|branch)\b'
        before_merge = len(commits)
        commits = commits[~commits['message'].str.match(merge_pattern, case=False, na=False)]
        merges_removed = before_merge - len(commits)
        if merges_removed:
            print(f"  ⚠ Excluded {merges_removed} merge commits (Merge pull request / Merge branch)")

        # Prefer SHA-based deduplication when available; fall back to
        # (date, author_email, message) for older rows that lack a SHA.
        has_sha = commits['commit_sha'].notna() & (commits['commit_sha'].astype(str).str.strip() != '')
        sha_rows = commits[has_sha].drop_duplicates(subset=['commit_sha'])
        non_sha_rows = commits[~has_sha].drop_duplicates(subset=['date', 'author_email', 'message'])
        commits = pd.concat([sha_rows, non_sha_rows], ignore_index=True)
        print(f"  ✓ {len(commits)} unique regular commits after deduplication")
    except Exception as e:
        print(f"  ✗ Error loading GitHub commits file: {e}")
        return False
    
    if commits.empty:
        print("  ⚠ Warning: No commits found")
        # Create empty output file with headers
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year', 
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        return True
    
    # Aggregate LOC added
    print("Aggregating lines of code added...")
    
    # Merge with resources
    merged = commits.merge(resources, left_on='author_email', right_on='GIT Email', how='inner')
    
    if merged.empty:
        print("  ⚠ Warning: No matching records found between GitHub commits and Resources")
        return False
    
    # Add time period columns
    merged['Week'] = merged['date'].apply(get_week_number)
    merged['Month'] = merged['date'].apply(get_month_string)
    merged['Quarter'] = merged['date'].apply(get_quarter_string)
    merged['FiscalYear'] = merged['date'].apply(lambda x: get_fiscal_year(x, fiscal_start_month))
    
    # Calculate current period values
    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_fiscal_year = get_fiscal_year(current_dt, fiscal_start_month)
    
    # Aggregate by different time periods
    weekly_agg = merged.groupby(['SAPID', 'Name', 'Week'])['lines_added'].sum().reset_index()
    monthly_agg = merged.groupby(['SAPID', 'Name', 'Month'])['lines_added'].sum().reset_index()
    quarterly_agg = merged.groupby(['SAPID', 'Name', 'Quarter'])['lines_added'].sum().reset_index()
    annual_agg = merged.groupby(['SAPID', 'Name', 'FiscalYear'])['lines_added'].sum().reset_index()
    
    # Get all employees who have commits
    all_employees = merged[['SAPID', 'Name']].drop_duplicates()
    
    # Combine aggregations per employee
    result = []
    for _, emp_row in all_employees.iterrows():
        sapid = emp_row['SAPID']
        emp_name = emp_row['Name']
        
        # Get LOC added for current periods
        weekly_data = weekly_agg[(weekly_agg['SAPID'] == sapid) & (weekly_agg['Week'] == current_week)]
        weekly_loc = weekly_data['lines_added'].sum() if not weekly_data.empty else 0
        
        monthly_data = monthly_agg[(monthly_agg['SAPID'] == sapid) & (monthly_agg['Month'] == current_month)]
        monthly_loc = monthly_data['lines_added'].sum() if not monthly_data.empty else 0
        
        quarterly_data = quarterly_agg[(quarterly_agg['SAPID'] == sapid) & (quarterly_agg['Quarter'] == current_quarter)]
        quarterly_loc = quarterly_data['lines_added'].sum() if not quarterly_data.empty else 0
        
        annual_data = annual_agg[(annual_agg['SAPID'] == sapid) & (annual_agg['FiscalYear'] == current_fiscal_year)]
        annual_loc = annual_data['lines_added'].sum() if not annual_data.empty else 0
        
        result.append({
            'SAPID': sapid,
            'Name': emp_name,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'Weekly': int(weekly_loc),
            'Monthly': int(monthly_loc),
            'Quarterly': int(quarterly_loc),
            'Annual': int(annual_loc)
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
    # For testing
    import sys
    from pathlib import Path
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    resources_file = project_root / 'config' / 'Resources.csv'
    github_commits_file = project_root / 'output' / 'github_commits.csv'
    output_dir = project_root / 'output'
    
    success = k227(
        resources_file=str(resources_file),
        github_commits_file=str(github_commits_file),
        output_dir=str(output_dir)
    )
    
    sys.exit(0 if success else 1)
