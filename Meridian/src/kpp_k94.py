#!/usr/bin/env python3
"""
KPP K94 - Average Dev Cycle Time for Bugs (Individual Level)
Calculates average bug cycle time from first assignment to employee to first end state (Ready For QA/Done/Invalid).
Individual-level aggregation.
"""

import pandas as pd
import os
from datetime import date, datetime
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings


def get_description():
    """Return KPI description."""
    return "Average Dev Cycle Time for Bugs (Individual) - Calculates bug cycle time from first assignment to employee to Ready For QA/Done/Invalid, aggregated per individual"


def load_history_data(history_file):
    """Load history data from CSV."""
    if not os.path.exists(history_file):
        print(f"  ⚠ Warning: History file not found: {history_file}")
        return pd.DataFrame()
    
    df = pd.read_csv(history_file)
    df['ChangeDate'] = pd.to_datetime(df['ChangeDate'])
    return df


def get_first_assignment_date(key, assignee_jira_name, history_df):
    """
    Get the first assignment date for this employee on this bug.
    
    Args:
        key: Issue key
        assignee_jira_name: JIRA name of the assignee
        history_df: History dataframe
    
    Returns:
        First assignment datetime or None if not found
    """
    # Filter history for this issue and assignee changes
    issue_history = history_df[
        (history_df['Key'] == key) & 
        (history_df['Field'] == 'assignee') &
        (history_df['ToValue'] == assignee_jira_name)
    ].sort_values('ChangeDate')
    
    if len(issue_history) == 0:
        return None
    
    # Return the first assignment date
    return issue_history.iloc[0]['ChangeDate']


def get_first_end_state_date(key, history_df, end_states=['Ready For QA', 'Done', 'Invalid', 'Closed']):
    """
    Get the first end state date for this bug.
    
    Args:
        key: Issue key
        history_df: History dataframe
        end_states: List of acceptable end states
    
    Returns:
        First end state datetime or None if not found
    """
    # Filter history for this issue and status changes
    issue_history = history_df[
        (history_df['Key'] == key) & 
        (history_df['Field'] == 'status')
    ].sort_values('ChangeDate')
    
    if len(issue_history) == 0:
        return None
    
    # Find first transition to an end state
    for idx, row in issue_history.iterrows():
        to_status = row['ToValue']
        if to_status in end_states:
            return row['ChangeDate']
    
    return None


def calculate_bug_cycle_time_individual(key, assignee_jira_name, created_date, history_df):
    """
    Calculate cycle time for a bug from first assignment to first end state for a specific employee.
    
    Args:
        key: Issue key
        assignee_jira_name: JIRA name of the assignee
        created_date: Creation datetime (fallback if no assignment found)
        history_df: History dataframe
    
    Returns:
        Tuple of (cycle_time_days, start_date, end_date, is_valid)
    """
    # Get first assignment date for this employee
    assignment_date = get_first_assignment_date(key, assignee_jira_name, history_df)
    
    if assignment_date is None:
        # No assignment history found, skip this bug
        return (0, None, None, False)
    
    # Get first end state date
    end_state_date = get_first_end_state_date(key, history_df)
    
    if end_state_date is None:
        # Bug hasn't reached end state yet, skip
        return (0, assignment_date, None, False)
    
    # Calculate cycle time only if end state came after assignment
    if end_state_date < assignment_date:
        # End state before assignment, skip
        return (0, assignment_date, end_state_date, False)
    
    cycle_time = (end_state_date - assignment_date).total_seconds() / (24 * 3600)  # days
    return (cycle_time, assignment_date, end_state_date, True)


def k94(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K94: Average Dev Cycle Time for Bugs at Individual Level.
    
    Args:
        resources_file (str): Path to Resources.csv file
        jira_issues_file (str): Path to JIRAIssues.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k94-data.csv')
    history_file = os.path.join(output_dir, 'JIRAIssues_History.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K94 - Average Dev Cycle Time for Bugs (Individual)")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")
    
    # Load resources
    print("Loading resources data...")
    try:
        resources_df = pd.read_csv(resources_file)
        resources = resources_df[['SAPID', 'Name', 'JIRA Name', 'Team', 'Scrum']].copy()
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
    
    # Load JIRA issues (bugs only)
    print("Loading JIRA bugs data...")
    try:
        issues_df = pd.read_csv(jira_issues_file)
        bugs = issues_df[issues_df['Issue Type'] == 'Bug'].copy()
        bugs['Created'] = pd.to_datetime(bugs['Created'], errors='coerce')
        bugs['Updated'] = pd.to_datetime(bugs['Updated'], errors='coerce')
        bugs = bugs[
            (bugs['Assignee'].notna()) & 
            (bugs['Created'].notna()) &
            (bugs['Updated'].notna())
        ]
        print(f"  ✓ Loaded {len(bugs)} bugs")
    except Exception as e:
        print(f"  ✗ Error loading JIRA issues file: {e}")
        return False
    
    if bugs.empty:
        print("  ⚠ Warning: No bugs found")
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
    
    # Load history data
    print("Loading history data...")
    history_df = load_history_data(history_file)
    if history_df.empty:
        print("  ⚠ Warning: No history data available, cannot calculate cycle times")
        return False
    else:
        print(f"  ✓ Loaded {len(history_df)} history entries")
    
    # Merge bugs with resources
    print("Calculating individual cycle times...")
    merged = bugs.merge(resources, left_on='Assignee', right_on='JIRA Name', how='inner')
    
    if merged.empty:
        print("  ⚠ Warning: No matching records found between bugs and Resources")
        return False
    
    # Calculate cycle time for each bug per individual
    cycle_times = []
    for idx, bug in merged.iterrows():
        cycle_time, start_date, end_date, is_valid = calculate_bug_cycle_time_individual(
            bug['Key'],
            bug['JIRA Name'],
            bug['Created'],
            history_df
        )
        
        if is_valid:
            cycle_times.append({
                'Key': bug['Key'],
                'SAPID': bug['SAPID'],
                'Name': bug['Name'],
                'JIRA Name': bug['JIRA Name'],
                'Team': bug['Team'],
                'Scrum': bug['Scrum'],
                'StartDate': start_date,
                'EndDate': end_date,
                'CycleTimeDays': cycle_time
            })
    
    if not cycle_times:
        print("  ⚠ Warning: No valid cycle times calculated")
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
    
    cycle_df = pd.DataFrame(cycle_times)
    print(f"  ✓ Calculated {len(cycle_df)} valid bug cycle times")
    
    # Add time period columns based on EndDate (completion date)
    cycle_df['Week'] = cycle_df['EndDate'].apply(get_week_number)
    cycle_df['Month'] = cycle_df['EndDate'].apply(get_month_string)
    cycle_df['Quarter'] = cycle_df['EndDate'].apply(get_quarter_string)
    cycle_df['FiscalYear'] = cycle_df['EndDate'].apply(lambda x: get_fiscal_year(x, fiscal_start_month))
    
    # Calculate current period values
    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_fiscal_year = get_fiscal_year(current_dt, fiscal_start_month)
    
    print("Aggregating by individual...")
    
    # Aggregate by individual (SAPID) for each period
    result = []
    
    for _, emp in resources.iterrows():
        sapid = emp['SAPID']
        name = emp['Name']
        
        # Filter bugs for this individual
        emp_bugs = cycle_df[cycle_df['SAPID'] == sapid]
        
        # Calculate averages for each period
        weekly = emp_bugs[emp_bugs['Week'] == current_week]['CycleTimeDays'].mean() if len(emp_bugs[emp_bugs['Week'] == current_week]) > 0 else 0
        monthly = emp_bugs[emp_bugs['Month'] == current_month]['CycleTimeDays'].mean() if len(emp_bugs[emp_bugs['Month'] == current_month]) > 0 else 0
        quarterly = emp_bugs[emp_bugs['Quarter'] == current_quarter]['CycleTimeDays'].mean() if len(emp_bugs[emp_bugs['Quarter'] == current_quarter]) > 0 else 0
        annual = emp_bugs[emp_bugs['FiscalYear'] == current_fiscal_year]['CycleTimeDays'].mean() if len(emp_bugs[emp_bugs['FiscalYear'] == current_fiscal_year]) > 0 else 0
        
        result.append({
            'CurrentDate': current_date_str,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'SAPID': sapid,
            'Name': name,
            'Weekly': round(weekly, 2) if pd.notna(weekly) else 0,
            'Monthly': round(monthly, 2) if pd.notna(monthly) else 0,
            'Quarterly': round(quarterly, 2) if pd.notna(quarterly) else 0,
            'Annual': round(annual, 2) if pd.notna(annual) else 0
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
    print(f"  ✓ {len(non_zero)} individuals with completed bugs")
    
    print(f"{'='*60}\n")
    return True


if __name__ == '__main__':
    # For testing
    import sys
    from pathlib import Path
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    resources_file = project_root / 'config' / 'Resources.csv'
    jira_issues_file = project_root / 'output' / 'JIRAIssues.csv'
    output_dir = project_root / 'output'
    
    success = k94(
        resources_file=str(resources_file),
        jira_issues_file=str(jira_issues_file),
        output_dir=str(output_dir)
    )
    
    sys.exit(0 if success else 1)
