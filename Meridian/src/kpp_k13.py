#!/usr/bin/env python3
"""
KPP K13 - Story Points Per Team Member (Self + Team Hierarchy)
Aggregates average story points delivered per team member, including self.
Every employee gets team_size = Reporting + 1 (always includes self).
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings

# Import K3 to run it if needed
from kpp_k3 import k3


def get_description():
    """Return KPI description."""
    return "Story Points Per Team Member - Aggregates average story points per team member (self + direct reports) for all employees"


def k13(resources_file, k3_data_file, output_dir, jira_issues_file=None, fiscal_start_month=4, current_date=None):
    """
    K13: Aggregate average story points per team member for managers and generate k13-data.csv output.
    
    Args:
        resources_file (str): Path to Resources.csv file
        k3_data_file (str): Path to k3-data.csv file (output from K3)
        output_dir (str): Directory for output files
        jira_issues_file (str): Path to JIRAIssues.csv file (needed if K3 needs to be run)
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k13-data.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K13 - Story Points Per Team Member")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")
    
    # Load resources
    print("Loading resources data...")
    try:
        df = pd.read_csv(resources_file)
        resources = df[['Ref', 'SAPID', 'Name', 'Manager', 'Manager Name', 'Reporting']].copy()
        resources['SAPID'] = resources['SAPID'].fillna(0).astype(int).astype(str)
        resources['Ref'] = resources['Ref'].fillna(0).astype(int)
        # Convert Manager to numeric, coerce errors to NaN
        resources['Manager'] = pd.to_numeric(resources['Manager'], errors='coerce').fillna(0).astype(int)
        resources['Reporting'] = pd.to_numeric(resources['Reporting'], errors='coerce').fillna(0).astype(int)
        
        # Include all employees - team_size = Reporting + 1 (self), so even Reporting=0 yields team_size=1
        managers = resources.copy()
        print(f"  ✓ Loaded {len(resources)} resources")
        print(f"  ✓ Processing {len(managers)} employees (Reporting + 1 includes self)")
    except Exception as e:
        print(f"  ✗ Error loading resources file: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    if managers.empty:
        print("  ⚠ Warning: No employees found")
        # Create empty output file with headers
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year', 
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        print(f"{'='*60}\n")
        return True
    
    # Load K3 data
    print("Loading K3 story points data...")
    k3_needs_update = False
    
    try:
        k3_df = pd.read_csv(k3_data_file)
        
        # Check if K3 data is up to date (has current date entries)
        if k3_df.empty:
            print(f"  ⚠ Warning: K3 data file is empty")
            k3_needs_update = True
        else:
            # Check for current date entries
            k3_df['CurrentDate'] = k3_df['CurrentDate'].astype(str)
            current_date_entries = k3_df[k3_df['CurrentDate'] == current_date_str]
            
            if current_date_entries.empty:
                print(f"  ⚠ Warning: K3 data is not up to date for {current_date_str}")
                k3_needs_update = True
                
    except FileNotFoundError:
        print(f"  ⚠ Warning: K3 data file not found")
        k3_needs_update = True
    except Exception as e:
        print(f"  ✗ Error loading K3 data file: {e}")
        return False
    
    # Run K3 if needed
    if k3_needs_update:
        print(f"  ℹ Running K3 to update data...")
        
        if jira_issues_file is None:
            print(f"  ✗ Error: Cannot run K3 - JIRA issues file path not provided")
            print(f"  ℹ Please run K3 separately: python KppEvaluator.py -k k3")
            return False
        
        k3_success = k3(
            resources_file=resources_file,
            jira_issues_file=jira_issues_file,
            output_dir=output_dir,
            fiscal_start_month=fiscal_start_month,
            current_date=current_date
        )
        
        if not k3_success:
            print(f"  ✗ Error: Failed to run K3")
            return False
        
        # Reload K3 data after running it
        try:
            k3_df = pd.read_csv(k3_data_file)
            k3_df['CurrentDate'] = k3_df['CurrentDate'].astype(str)
            current_date_entries = k3_df[k3_df['CurrentDate'] == current_date_str]
            
            if current_date_entries.empty:
                print(f"  ✗ Error: K3 data still not available for {current_date_str}")
                return False
        except Exception as e:
            print(f"  ✗ Error reloading K3 data: {e}")
            return False
    
    # Filter for current date only
    k3_df = k3_df[k3_df['CurrentDate'] == current_date_str].copy()
    k3_df['SAPID'] = k3_df['SAPID'].astype(str)
    
    print(f"  ✓ Loaded {len(k3_df)} employee story point records for {current_date_str}")
    
    if k3_df.empty:
        print("  ⚠ Warning: No K3 data found for current date")
        # Create empty output file with headers
        output_df = pd.DataFrame(columns=[
            'CurrentDate', 'Week', 'Month', 'Quarter', 'Year', 
            'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual'
        ])
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created empty output file: {output_file}")
        print(f"{'='*60}\n")
        return True
    
    # Calculate current period values
    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_fiscal_year = get_fiscal_year(current_dt, fiscal_start_month)
    
    # Compute story points per team member for each employee (self + direct reports)
    print("Computing story points per team member for all employees...")
    result = []
    
    for _, manager_row in managers.iterrows():
        manager_ref = manager_row['Ref']
        manager_sapid = manager_row['SAPID']
        manager_name = manager_row['Name']
        num_reportees = manager_row['Reporting']
        
        # Find the manager's own story points from K3
        manager_k3 = k3_df[k3_df['SAPID'] == manager_sapid]
        
        # Get manager's story points (default to 0 if not found)
        if not manager_k3.empty:
            manager_weekly = manager_k3['Weekly'].iloc[0]
            manager_monthly = manager_k3['Monthly'].iloc[0]
            manager_quarterly = manager_k3['Quarterly'].iloc[0]
            manager_annual = manager_k3['Annual'].iloc[0]
        else:
            manager_weekly = 0
            manager_monthly = 0
            manager_quarterly = 0
            manager_annual = 0
        
        # Find all reportees (where Manager == this manager's Ref)
        reportees = resources[resources['Manager'] == manager_ref]
        
        # Sum story points for all reportees
        total_weekly = manager_weekly
        total_monthly = manager_monthly
        total_quarterly = manager_quarterly
        total_annual = manager_annual
        
        for _, reportee_row in reportees.iterrows():
            reportee_sapid = reportee_row['SAPID']
            reportee_k3 = k3_df[k3_df['SAPID'] == reportee_sapid]
            
            if not reportee_k3.empty:
                total_weekly += reportee_k3['Weekly'].iloc[0]
                total_monthly += reportee_k3['Monthly'].iloc[0]
                total_quarterly += reportee_k3['Quarterly'].iloc[0]
                total_annual += reportee_k3['Annual'].iloc[0]
        
        # Calculate average per team member (divide by num_reportees + 1 for manager)
        # Round to 1 decimal place
        total_members = num_reportees + 1  # +1 to include the manager
        avg_weekly = round(total_weekly / total_members, 1) if total_members > 0 else 0.0
        avg_monthly = round(total_monthly / total_members, 1) if total_members > 0 else 0.0
        avg_quarterly = round(total_quarterly / total_members, 1) if total_members > 0 else 0.0
        avg_annual = round(total_annual / total_members, 1) if total_members > 0 else 0.0
        
        result.append({
            'SAPID': manager_sapid,
            'Name': manager_name,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'Weekly': avg_weekly,
            'Monthly': avg_monthly,
            'Quarterly': avg_quarterly,
            'Annual': avg_annual
        })
    
    aggregated = pd.DataFrame(result)
    
    if aggregated.empty:
        print("  ⚠ No aggregated data to write")
        return False
    
    print(f"  ✓ Computed averages for {len(aggregated)} employees")
    
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
