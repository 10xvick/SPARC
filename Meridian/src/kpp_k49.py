#!/usr/bin/env python3
"""
KPP K49 - Reviews Actively Participated In by Employee
Aggregates count of reviews where employee participated (made at least 1 comment).
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings


def get_description():
    """Return KPI description."""
    return "Reviews Actively Participated In - Aggregates count of reviews where employee participated (made at least 1 comment)"


def k49(resources_file, github_commits_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K49: Aggregate reviews participated in and generate k49-data.csv output.
    
    Args:
        resources_file (str): Path to Resources.csv file
        github_commits_file (str): Path to github_commits.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k49-data.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K49 - Reviews Actively Participated In")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")
    
    # Load resources
    print("Loading resources data...")
    try:
        df = pd.read_csv(resources_file)
        resources = df[['SAPID', 'Name', 'GitHUB Name']].copy()
        resources['SAPID'] = resources['SAPID'].fillna(0).astype(int).astype(str)
        # Remove rows with missing GitHUB Name
        resources = resources[resources['GitHUB Name'].notna()]
        resources = resources[resources['GitHUB Name'] != '']
        resources = resources[resources['GitHUB Name'] != '-NA-']
        print(f"  ✓ Loaded {len(resources)} resources")
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
        # Filter for rows where count_review_flag is true
        commits = df[df['count_review_flag'] == True].copy()
        
        # Parse date
        commits['date'] = pd.to_datetime(commits['date'], errors='coerce')
        
        # Keep only rows with valid data and review_comments
        commits = commits[
            (commits['review_comments'].notna()) &
            (commits['review_comments'] != '') &
            (commits['date'].notna())
        ]
        
        print(f"  ✓ Loaded {len(commits)} commits with review comments")
    except Exception as e:
        print(f"  ✗ Error loading GitHub commits file: {e}")
        return False
    
    if commits.empty:
        print("  ⚠ Warning: No commits with review comments found")
        # Create empty output file with headers
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year', 
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        print(f"{'='*60}\n")
        return True
    
    def extract_reviewers(review_comments_str):
        """Extract unique reviewer GitHub names from review_comments string."""
        reviewers = []
        try:
            if pd.isna(review_comments_str) or review_comments_str == '':
                return reviewers
            
            # Split by semicolon to get individual reviewer:count pairs
            pairs = str(review_comments_str).split(';')
            for pair in pairs:
                if ':' in pair:
                    # Get reviewer name (first part before colon)
                    reviewer = pair.split(':')[0].strip()
                    if reviewer:
                        reviewers.append(reviewer)
        except Exception:
            return []
        
        return reviewers
    
    # Extract reviewers from each commit and create rows for each reviewer
    print("Extracting reviewer participation...")
    review_participation = []
    
    for _, commit in commits.iterrows():
        reviewers = extract_reviewers(commit['review_comments'])
        commit_date = commit['date']
        
        for reviewer_github_name in reviewers:
            review_participation.append({
                'date': commit_date,
                'reviewer_github_name': reviewer_github_name
            })
    
    if not review_participation:
        print("  ⚠ Warning: No reviewer participation found")
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year', 
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        print(f"{'='*60}\n")
        return True
    
    participation_df = pd.DataFrame(review_participation)
    print(f"  ✓ Extracted {len(participation_df)} reviewer participation records")
    
    # Merge with resources using GitHub Name
    print("Mapping reviewers to employees...")
    merged = participation_df.merge(
        resources,
        left_on='reviewer_github_name',
        right_on='GitHUB Name',
        how='inner'
    )
    
    if merged.empty:
        print("  ⚠ Warning: No matching reviewers found in Resources")
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year', 
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        print(f"{'='*60}\n")
        return True
    
    print(f"  ✓ Matched {len(merged)} participation records to employees")
    
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
    
    # Aggregate by different time periods (count reviews participated in)
    weekly_agg = merged.groupby(['SAPID', 'Name', 'Week']).size().reset_index(name='count')
    monthly_agg = merged.groupby(['SAPID', 'Name', 'Month']).size().reset_index(name='count')
    quarterly_agg = merged.groupby(['SAPID', 'Name', 'Quarter']).size().reset_index(name='count')
    annual_agg = merged.groupby(['SAPID', 'Name', 'FiscalYear']).size().reset_index(name='count')
    
    # Get all employees who participated in reviews
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
