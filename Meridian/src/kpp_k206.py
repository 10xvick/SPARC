#!/usr/bin/env python3
"""
KPP K206 - Reviews Initiated by Employee
Aggregates count of reviews initiated by employee from GitHub commits.
"""

import os
from datetime import date

import pandas as pd

from kpi_helpers import get_fiscal_year, get_month_string, get_quarter_string, get_week_number


def get_description():
    """Return KPI description."""
    return "Reviews Initiated - Aggregates count of reviews initiated by employee"


def k206(resources_file, github_commits_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K206: Count reviews initiated per employee and generate k206-data.csv output.

    Args:
        resources_file (str): Path to Resources.csv file
        github_commits_file (str): Path to github_commits.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)

    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k206-data.csv')

    if current_date is None:
        current_date = date.today()

    current_date_str = current_date.strftime('%Y%m%d')

    print(f"\n{'='*60}")
    print("KPP K206 - Reviews Initiated")
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

        # Count only commits where review was initiated (count_review_flag = true)
        review_flag = df['count_review_flag'].astype(str).str.strip().str.lower().isin(['true', '1', 'yes'])
        commits = df[review_flag].copy()

        commits['date'] = pd.to_datetime(commits['date'], errors='coerce')

        commits = commits[
            (commits['author_email'].notna()) &
            (commits['author_email'] != '') &
            (commits['date'].notna())
        ]

        print(f"  ✓ Loaded {len(commits)} review-initiated commits")
    except Exception as e:
        print(f"  ✗ Error loading GitHub commits file: {e}")
        return False

    if commits.empty:
        print("  ⚠ Warning: No review-initiated commits found")
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year',
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        print(f"{'='*60}\n")
        return True

    # Merge commits with resources using author_email and GIT Email
    print("Mapping review initiations to employees...")
    merged = commits.merge(
        resources,
        left_on='author_email',
        right_on='GIT Email',
        how='inner'
    )

    if merged.empty:
        print("  ⚠ Warning: No matching records found between GitHub commits and Resources")
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year',
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        print(f"{'='*60}\n")
        return True

    print(f"  ✓ Matched {len(merged)} review initiations to employees")

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

    # Aggregate by different time periods (count review initiations)
    weekly_agg = merged.groupby(['SAPID', 'Name', 'Week']).size().reset_index(name='count')
    monthly_agg = merged.groupby(['SAPID', 'Name', 'Month']).size().reset_index(name='count')
    quarterly_agg = merged.groupby(['SAPID', 'Name', 'Quarter']).size().reset_index(name='count')
    annual_agg = merged.groupby(['SAPID', 'Name', 'FiscalYear']).size().reset_index(name='count')

    # Get all employees who initiated reviews
    all_employees = merged[['SAPID', 'Name']].drop_duplicates()

    # Combine aggregations per employee
    result = []
    for _, emp_row in all_employees.iterrows():
        sapid = emp_row['SAPID']
        emp_name = emp_row['Name']

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
