"""
KPP K14 - Delayed Story Points at Team Level
Aggregates delayed story points from K64 by team.
"""

import pandas as pd
import os
from datetime import datetime
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings


def get_description():
    """Return KPI description."""
    return "Delayed Story Points at Team Level - Aggregates delayed story points from K64 by team"


def k14(resources_file, current_date=None, fiscal_start_month=4, output_folder='../output', jira_issues_file='../output/JIRAIssues.csv'):
    """
    Compute K14: Delayed Story Points at Team Level
    
    Args:
        resources_file: Path to Resources.csv
        current_date: Current date (date object or None for today)
        fiscal_start_month: Fiscal year start month (default: 4 for April)
        output_folder: Output folder path
        jira_issues_file: Path to JIRA issues CSV (needed for k64 dependency)
    """
    # Handle current_date
    if current_date is None:
        from datetime import date
        current_date = date.today()
    
    # Convert to string format if it's a date object
    if hasattr(current_date, 'strftime'):
        current_date_str = current_date.strftime('%Y%m%d')
    else:
        current_date_str = str(current_date)
    
    print("\n" + "="*60)
    print("KPP K14 - Delayed Story Points at Team Level")
    print(f"Date: {current_date_str}")
    print("="*60)
    
    output_file = os.path.join(output_folder, 'k14-data.csv')
    k64_file = os.path.join(output_folder, 'k64-data.csv')
    
    # Check if k64 data exists and is current
    k64_needs_update = True
    if os.path.exists(k64_file):
        try:
            k64_df = pd.read_csv(k64_file)
            if not k64_df.empty and str(current_date_str) in k64_df['CurrentDate'].astype(str).values:
                k64_needs_update = False
                print("  ✓ K64 data is up to date")
            else:
                print("  ⚠ K64 data exists but is not current")
        except Exception as e:
            print(f"  ⚠ Warning: Could not read K64 data: {e}")
    else:
        print("  ⚠ K64 data file not found")
    
    # Run k64 if needed
    if k64_needs_update:
        print("ℹ Running K64 to update data...")
        from kpp_k64 import k64
        success = k64(
            resources_file=resources_file,
            jira_issues_file=jira_issues_file,
            output_dir=output_folder,
            fiscal_start_month=fiscal_start_month,
            current_date=current_date
        )
        if not success:
            print("  ✗ Failed to update K64 data")
            return False
    
    # Load resources to get team mapping
    print("Loading resources data...")
    try:
        resources = pd.read_csv(resources_file)
        # Convert SAPID to string, handling NaN values and removing .0 suffix
        resources['SAPID'] = pd.to_numeric(resources['SAPID'], errors='coerce')
        resources = resources[resources['SAPID'].notna()]  # Remove rows with invalid SAPID
        resources['SAPID'] = resources['SAPID'].astype(int).astype(str)
        print(f"  ✓ Loaded {len(resources)} resources")
    except Exception as e:
        print(f"  ✗ Error loading resources file: {e}")
        return False
    
    if resources.empty:
        print("  ✗ No resources data loaded")
        return False
    
    # Load k64 data
    print("Loading K64 delayed story points data...")
    try:
        k64_df = pd.read_csv(k64_file)
        k64_df['SAPID'] = k64_df['SAPID'].astype(str)
        
        # Filter for current date
        current_k64 = k64_df[k64_df['CurrentDate'].astype(str) == str(current_date_str)].copy()
        
        if current_k64.empty:
            print(f"  ✗ No K64 data found for date {current_date_str}")
            return False
        
        print(f"  ✓ Loaded {len(current_k64)} employee records from K64")
    except Exception as e:
        print(f"  ✗ Error loading K64 data: {e}")
        return False
    
    # Merge k64 data with resources to get team information
    print("Aggregating delayed story points by team...")
    merged = current_k64.merge(
        resources[['SAPID', 'Team']], 
        on='SAPID', 
        how='left'
    )
    
    # Fill missing teams with 'Unknown'
    merged['Team'] = merged['Team'].fillna('Unknown')
    
    # Aggregate by team
    team_agg = merged.groupby('Team').agg({
        'Weekly': 'sum',
        'Monthly': 'sum',
        'Quarterly': 'sum',
        'Annual': 'sum'
    }).reset_index()
    
    if team_agg.empty:
        print("  ✗ No team data to aggregate")
        return False
    
    print(f"  ✓ Computed delayed story points for {len(team_agg)} teams")
    
    # Calculate current period values
    current_dt_obj = pd.Timestamp(current_date_str)
    current_week = get_week_number(current_dt_obj)
    current_month = get_month_string(current_dt_obj)
    current_quarter = get_quarter_string(current_dt_obj)
    current_fiscal_year = get_fiscal_year(current_dt_obj, fiscal_start_month)
    
    # Build result - create a row for each individual with their team's values
    # Merge team aggregations back to individual employees
    result = []
    for _, emp_row in merged.iterrows():
        team = emp_row['Team']
        team_data = team_agg[team_agg['Team'] == team].iloc[0]
        
        # Get employee details from k64 data
        result.append({
            'CurrentDate': current_date_str,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'SAPID': emp_row['SAPID'],
            'Name': emp_row['Name'],
            'Weekly': float(team_data['Weekly']),
            'Monthly': float(team_data['Monthly']),
            'Quarterly': float(team_data['Quarterly']),
            'Annual': float(team_data['Annual'])
        })
    
    result_df = pd.DataFrame(result)
    
    # Append to existing data or create new
    if os.path.exists(output_file):
        existing_df = pd.read_csv(output_file)
        # Remove existing records for current date
        existing_df = existing_df[existing_df['CurrentDate'].astype(str) != str(current_date_str)]
        # Append new records
        final_df = pd.concat([existing_df, result_df], ignore_index=True)
    else:
        final_df = result_df
    
    # Save to CSV
    final_df.to_csv(output_file, index=False)
    
    if os.path.exists(output_file):
        action = "Updated" if os.path.exists(output_file) else "Created"
        print(f"  ✓ {action} {output_file} with {len(result_df)} records")
    else:
        print(f"  ✗ Failed to create {output_file}")
        return False
    
    print("="*60)
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Compute KPP K14 - Delayed Story Points at Team Level')
    parser.add_argument('--resources', default='../config/Resources.csv', help='Path to Resources.csv')
    parser.add_argument('--jira-issues', default='../output/JIRAIssues.csv', help='Path to JIRA issues CSV')
    parser.add_argument('--date', default=datetime.now().strftime('%Y%m%d'), help='Current date (YYYYMMDD)')
    parser.add_argument('--fiscal-month', type=int, default=4, help='Fiscal year start month (1-12)')
    parser.add_argument('--output', default='../output', help='Output folder path')
    
    args = parser.parse_args()
    
    success = k14(
        resources_file=args.resources,
        current_date=args.date,
        fiscal_start_month=args.fiscal_month,
        output_folder=args.output,
        jira_issues_file=args.jira_issues
    )
    
    exit(0 if success else 1)
