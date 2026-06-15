#!/usr/bin/env python3
"""
KPP K64 - Delayed Story Points
Aggregates story points that are delayed (Sprint.endDate < current date).
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings


def get_description():
    """Return KPI description."""
    return "Delayed Story Points - Aggregates story points that are delayed (Sprint.endDate < current date)"


def k64(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K64: Aggregate delayed story points and generate k64-data.csv output.
    
    Args:
        resources_file (str): Path to Resources.csv file
        jira_issues_file (str): Path to JIRAIssues.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k64-data.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K64 - Delayed Story Points")
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
        
        # Parse Sprint.endDate (keep timezone-aware)
        df['Sprint.endDate'] = pd.to_datetime(df['Sprint.endDate'], errors='coerce', utc=True)
        
        # Filter for delayed items (Sprint.endDate < current_date AND Status != 'Done')
        # Make current_dt timezone-aware to match Sprint.endDate
        current_dt = pd.Timestamp(current_date, tz='UTC')
        delayed_issues = df[
            (df['Sprint.endDate'].notna()) &
            (df['Sprint.endDate'] < current_dt) &
            (df['Status'] != 'Done') &
            (df['Assignee'].notna()) &
            (df['Story Points'].notna())
        ].copy()
        
        # Convert Story Points to numeric
        delayed_issues['Story Points'] = pd.to_numeric(delayed_issues['Story Points'], errors='coerce').fillna(0)
        
        print(f"  ✓ Loaded {len(delayed_issues)} delayed issues")
    except Exception as e:
        print(f"  ✗ Error loading JIRA issues file: {e}")
        return False
    
    if delayed_issues.empty:
        print("  ⚠ Warning: No delayed issues found")
        # Still create records for employees with 0 delayed points
        delayed_issues = pd.DataFrame(columns=['Assignee', 'Story Points'])
    
    # Calculate current period values
    current_dt_obj = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt_obj)
    current_month = get_month_string(current_dt_obj)
    current_quarter = get_quarter_string(current_dt_obj)
    current_fiscal_year = get_fiscal_year(current_dt_obj, fiscal_start_month)
    
    # Aggregate delayed story points by assignee (for weekly data)
    print("Aggregating delayed story points...")
    if not delayed_issues.empty:
        weekly_agg = delayed_issues.groupby('Assignee')['Story Points'].sum().reset_index()
        weekly_agg.columns = ['Assignee', 'Weekly']
    else:
        weekly_agg = pd.DataFrame(columns=['Assignee', 'Weekly'])
    
    # Merge with resources
    merged = resources.merge(
        weekly_agg,
        left_on='JIRA Name',
        right_on='Assignee',
        how='left'
    )
    
    # Fill NaN weekly values with 0
    merged['Weekly'] = merged['Weekly'].fillna(0)
    
    print(f"  ✓ Computed delayed story points for {len(merged)} employees")
    
    # Load existing data to calculate median for monthly, quarterly, annual
    # We need to include the current week's value when calculating medians
    print("Computing median values for monthly, quarterly, and annual...")
    monthly_values = {}
    quarterly_values = {}
    annual_values = {}
    
    existing_df = pd.DataFrame()
    if os.path.exists(output_file):
        try:
            existing_df = pd.read_csv(output_file)
            existing_df['SAPID'] = existing_df['SAPID'].astype(str)
        except Exception as e:
            print(f"  ⚠ Warning: Could not load existing data for median calculation: {e}")
    
    # For each employee, get historical + current weekly values to compute medians
    for _, row in merged.iterrows():
        sapid = row['SAPID']
        weekly_val = float(row['Weekly'])
        
        # Get historical data for this employee
        employee_history = existing_df[existing_df['SAPID'] == sapid] if not existing_df.empty else pd.DataFrame()
        
        # Monthly: median of weekly values from current month (including current week)
        monthly_data = employee_history[employee_history['Month'] == current_month] if not employee_history.empty else pd.DataFrame()
        monthly_weekly_values = monthly_data['Weekly'].tolist() if not monthly_data.empty else []
        monthly_weekly_values.append(weekly_val)  # Include current week
        monthly_values[sapid] = pd.Series(monthly_weekly_values).median()
        
        # Quarterly: median of weekly values from current quarter (including current week)
        quarterly_data = employee_history[employee_history['Quarter'] == current_quarter] if not employee_history.empty else pd.DataFrame()
        quarterly_weekly_values = quarterly_data['Weekly'].tolist() if not quarterly_data.empty else []
        quarterly_weekly_values.append(weekly_val)  # Include current week
        quarterly_values[sapid] = pd.Series(quarterly_weekly_values).median()
        
        # Annual: median of weekly values from current fiscal year (including current week)
        annual_data = employee_history[employee_history['Year'] == current_fiscal_year] if not employee_history.empty else pd.DataFrame()
        annual_weekly_values = annual_data['Weekly'].tolist() if not annual_data.empty else []
        annual_weekly_values.append(weekly_val)  # Include current week
        annual_values[sapid] = pd.Series(annual_weekly_values).median()
    
    # Build result with median values for monthly, quarterly, annual
    result = []
    for _, row in merged.iterrows():
        sapid = row['SAPID']
        weekly_val = float(row['Weekly'])
        
        # Use computed median values
        monthly_val = monthly_values.get(sapid, weekly_val)
        quarterly_val = quarterly_values.get(sapid, weekly_val)
        annual_val = annual_values.get(sapid, weekly_val)
        
        result.append({
            'SAPID': sapid,
            'Name': row['Name'],
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'Weekly': weekly_val,
            'Monthly': monthly_val,
            'Quarterly': quarterly_val,
            'Annual': annual_val
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
