#!/usr/bin/env python3
"""
KPP K4 - Review Comments Aggregation by Employee
Aggregates total review comments received per employee on weekly, monthly, quarterly, and annual basis.
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings


def get_description():
    """Return KPI description."""
    return "Review Comments - Aggregates total review comments received per employee"


def k4(resources_file, github_commits_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K4: Aggregate review comments and generate k4-data.csv output.
    
    Args:
        resources_file (str): Path to Resources.csv file
        github_commits_file (str): Path to github_commits.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k4-data.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K4 - Review Comments Aggregation")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")
    
    # Load resources
    print("Loading resources data...")
    try:
        df = pd.read_csv(resources_file)
        resources = df[['SAPID', 'Name', 'GIT Email']].copy()
        resources['SAPID'] = resources['SAPID'].fillna(0).astype(int).astype(str)
        # Remove rows with missing GIT Email
        resources = resources[resources['GIT Email'].notna()]
        resources = resources[resources['GIT Email'] != '']
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
        
        # Parse review_comments column (format: reviewer:count;reviewer:count;...)
        def parse_review_comments(value):
            """Parse review comments string and return sum of all counts."""
            if pd.isna(value) or value == '':
                return 0
            
            total = 0
            try:
                # Split by semicolon to get individual reviewer:count pairs
                pairs = str(value).split(';')
                for pair in pairs:
                    if ':' in pair:
                        # Split by colon and get the count (second part)
                        parts = pair.split(':')
                        if len(parts) == 2:
                            count = int(parts[1])
                            total += count
            except (ValueError, IndexError):
                return 0
            
            return total
        
        commits['review_comments'] = commits['review_comments'].apply(parse_review_comments)
        
        # Keep only rows with valid data
        commits = commits[
            (commits['author_email'].notna()) & 
            (commits['date'].notna())
        ]
        
        print(f"  ✓ Loaded {len(commits)} commits with review flag")
    except Exception as e:
        print(f"  ✗ Error loading GitHub commits file: {e}")
        return False
    
    if commits.empty:
        print("  ⚠ Warning: No commits with review flag found")
        # Create empty output file with headers
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year', 
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        return True
    
    # Aggregate review comments
    print("Aggregating review comments...")
    
    # Merge commits with resources using author_email and GIT Email
    merged = commits.merge(
        resources, 
        left_on='author_email', 
        right_on='GIT Email', 
        how='inner'
    )
    
    if merged.empty:
        print("  ⚠ Warning: No matching records found between GitHub commits and Resources")
        # Create empty output file with headers
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year', 
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        print(f"{'='*60}\n")
        return True
    
    print(f"  ✓ Matched {len(merged)} commits to employees")
    
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
    
    # Aggregate by different time periods
    weekly_agg = merged.groupby(['SAPID', 'Name', 'Week'])['review_comments'].sum().reset_index()
    monthly_agg = merged.groupby(['SAPID', 'Name', 'Month'])['review_comments'].sum().reset_index()
    quarterly_agg = merged.groupby(['SAPID', 'Name', 'Quarter'])['review_comments'].sum().reset_index()
    annual_agg = merged.groupby(['SAPID', 'Name', 'FiscalYear'])['review_comments'].sum().reset_index()
    
    # Get all employees who have review comments
    all_employees = merged[['SAPID', 'Name']].drop_duplicates()
    
    # Combine aggregations per employee
    result = []
    for _, emp_row in all_employees.iterrows():
        sapid = emp_row['SAPID']
        emp_name = emp_row['Name']
        
        # Get review comments for current periods
        weekly_data = weekly_agg[(weekly_agg['SAPID'] == sapid) & (weekly_agg['Week'] == current_week)]
        weekly_comments = int(weekly_data['review_comments'].sum()) if not weekly_data.empty else 0
        
        monthly_data = monthly_agg[(monthly_agg['SAPID'] == sapid) & (monthly_agg['Month'] == current_month)]
        monthly_comments = int(monthly_data['review_comments'].sum()) if not monthly_data.empty else 0
        
        quarterly_data = quarterly_agg[(quarterly_agg['SAPID'] == sapid) & (quarterly_agg['Quarter'] == current_quarter)]
        quarterly_comments = int(quarterly_data['review_comments'].sum()) if not quarterly_data.empty else 0
        
        annual_data = annual_agg[(annual_agg['SAPID'] == sapid) & (annual_agg['FiscalYear'] == current_fiscal_year)]
        annual_comments = int(annual_data['review_comments'].sum()) if not annual_data.empty else 0
        
        result.append({
            'SAPID': sapid,
            'Name': emp_name,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'Weekly': weekly_comments,
            'Monthly': monthly_comments,
            'Quarterly': quarterly_comments,
            'Annual': annual_comments
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
