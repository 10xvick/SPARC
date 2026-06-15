#!/usr/bin/env python3
"""
KPP K9 - Average Dev Cycle Time for Bugs
Calculates average bug cycle time from Created to Ready For QA/Done/Invalid, aggregated by Scrum/Team.
"""

import pandas as pd
import os
from datetime import date, datetime
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year, get_date_strings


def get_description():
    """Return KPI description."""
    return "Average Dev Cycle Time for Bugs - Calculates bug cycle time from Created to Ready For QA/Done/Invalid/Closed, aggregated by Scrum/Team"


def load_history_data(history_file):
    """Load history data from CSV."""
    if not os.path.exists(history_file):
        print(f"  ⚠ Warning: History file not found: {history_file}")
        return pd.DataFrame()
    
    df = pd.read_csv(history_file)
    df['ChangeDate'] = pd.to_datetime(df['ChangeDate'])
    return df


def calculate_bug_cycle_time(key, created_date, updated_date, history_df, end_states=['Ready For QA', 'Done', 'Invalid', 'Closed']):
    """
    Calculate cycle time for a bug from Created to first end state.
    
    Args:
        key: Issue key
        created_date: Creation datetime
        updated_date: Update datetime for period filtering
        history_df: History dataframe
        end_states: List of acceptable end states
    
    Returns:
        Tuple of (cycle_time_days, reached_end_state, updated_date)
    """
    # Filter history for this issue and status changes
    issue_history = history_df[
        (history_df['Key'] == key) & 
        (history_df['Field'] == 'status')
    ].sort_values('ChangeDate')
    
    if len(issue_history) == 0:
        # No status changes, return 0
        return (0, False, updated_date)
    
    # Find first transition to an end state
    for idx, row in issue_history.iterrows():
        to_status = row['ToValue']
        if to_status in end_states:
            # Calculate cycle time from created to this status
            cycle_time = (row['ChangeDate'] - created_date).total_seconds() / (24 * 3600)  # days
            return (cycle_time, True, row['ChangeDate'])
    
    # Never reached end state - use time to last status change
    last_change = issue_history.iloc[-1]['ChangeDate']
    cycle_time = (last_change - created_date).total_seconds() / (24 * 3600)  # days
    return (cycle_time, False, last_change)


def k9(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K9: Average Dev Cycle Time for Bugs aggregated by Scrum/Team.
    
    Args:
        resources_file (str): Path to Resources.csv file
        jira_issues_file (str): Path to JIRAIssues.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k9-data.csv')
    history_file = os.path.join(output_dir, 'JIRAIssues_History.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K9 - Average Dev Cycle Time for Bugs")
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
        return False
    
    # Load history data
    print("Loading history data...")
    history_df = load_history_data(history_file)
    if history_df.empty:
        print("  ⚠ Warning: No history data available, cycle times will be 0")
    else:
        print(f"  ✓ Loaded {len(history_df)} history entries")
    
    # Merge bugs with resources
    print("Calculating cycle times per individual...")
    merged = bugs.merge(resources, left_on='Assignee', right_on='JIRA Name', how='inner')
    
    if merged.empty:
        print("  ⚠ Warning: No matching records found between bugs and Resources")
        return False
    
    # Calculate cycle time for each bug
    cycle_times = []
    for idx, bug in merged.iterrows():
        cycle_time, reached_end, completion_date = calculate_bug_cycle_time(
            bug['Key'],
            bug['Created'],
            bug['Updated'],
            history_df
        )
        
        cycle_times.append({
            'Key': bug['Key'],
            'SAPID': bug['SAPID'],
            'Name': bug['Name'],
            'Team': bug['Team'],
            'Scrum': bug['Scrum'],
            'Created': bug['Created'],
            'Updated': bug['Updated'],
            'CompletionDate': completion_date,
            'CycleTimeDays': cycle_time,
            'ReachedEndState': reached_end
        })
    
    cycle_df = pd.DataFrame(cycle_times)
    
    # Add time period columns based on Updated date
    cycle_df['Week'] = cycle_df['Updated'].apply(get_week_number)
    cycle_df['Month'] = cycle_df['Updated'].apply(get_month_string)
    cycle_df['Quarter'] = cycle_df['Updated'].apply(get_quarter_string)
    cycle_df['FiscalYear'] = cycle_df['Updated'].apply(lambda x: get_fiscal_year(x, fiscal_start_month))
    
    # Calculate current period values
    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_fiscal_year = get_fiscal_year(current_dt, fiscal_start_month)
    
    print("Aggregating by Scrum and Team...")
    
    # Aggregate by Scrum for each period
    scrum_aggregations = {}
    
    for scrum in cycle_df['Scrum'].dropna().unique():
        scrum_bugs = cycle_df[cycle_df['Scrum'] == scrum]
        
        weekly = scrum_bugs[scrum_bugs['Week'] == current_week]['CycleTimeDays'].mean() if len(scrum_bugs[scrum_bugs['Week'] == current_week]) > 0 else 0
        monthly = scrum_bugs[scrum_bugs['Month'] == current_month]['CycleTimeDays'].mean() if len(scrum_bugs[scrum_bugs['Month'] == current_month]) > 0 else 0
        quarterly = scrum_bugs[scrum_bugs['Quarter'] == current_quarter]['CycleTimeDays'].mean() if len(scrum_bugs[scrum_bugs['Quarter'] == current_quarter]) > 0 else 0
        annual = scrum_bugs[scrum_bugs['FiscalYear'] == current_fiscal_year]['CycleTimeDays'].mean() if len(scrum_bugs[scrum_bugs['FiscalYear'] == current_fiscal_year]) > 0 else 0
        
        scrum_aggregations[scrum] = {
            'Weekly': round(weekly, 2) if pd.notna(weekly) else 0,
            'Monthly': round(monthly, 2) if pd.notna(monthly) else 0,
            'Quarterly': round(quarterly, 2) if pd.notna(quarterly) else 0,
            'Annual': round(annual, 2) if pd.notna(annual) else 0
        }
    
    # Aggregate by Team for fallback
    team_aggregations = {}
    
    for team in cycle_df['Team'].dropna().unique():
        team_bugs = cycle_df[cycle_df['Team'] == team]
        
        weekly = team_bugs[team_bugs['Week'] == current_week]['CycleTimeDays'].mean() if len(team_bugs[team_bugs['Week'] == current_week]) > 0 else 0
        monthly = team_bugs[team_bugs['Month'] == current_month]['CycleTimeDays'].mean() if len(team_bugs[team_bugs['Month'] == current_month]) > 0 else 0
        quarterly = team_bugs[team_bugs['Quarter'] == current_quarter]['CycleTimeDays'].mean() if len(team_bugs[team_bugs['Quarter'] == current_quarter]) > 0 else 0
        annual = team_bugs[team_bugs['FiscalYear'] == current_fiscal_year]['CycleTimeDays'].mean() if len(team_bugs[team_bugs['FiscalYear'] == current_fiscal_year]) > 0 else 0
        
        team_aggregations[team] = {
            'Weekly': round(weekly, 2) if pd.notna(weekly) else 0,
            'Monthly': round(monthly, 2) if pd.notna(monthly) else 0,
            'Quarterly': round(quarterly, 2) if pd.notna(quarterly) else 0,
            'Annual': round(annual, 2) if pd.notna(annual) else 0
        }
    
    print(f"  ✓ Aggregated for {len(scrum_aggregations)} scrums and {len(team_aggregations)} teams")
    
    # Create output for all employees
    print("Creating output for all employees...")
    result = []
    
    for _, emp in resources.iterrows():
        sapid = emp['SAPID']
        name = emp['Name']
        scrum = emp.get('Scrum', None)
        team = emp.get('Team', None)
        
        # Try to get scrum aggregation first, then team, else 0
        if pd.notna(scrum) and scrum in scrum_aggregations:
            values = scrum_aggregations[scrum]
        elif pd.notna(team) and team in team_aggregations:
            values = team_aggregations[team]
        else:
            values = {'Weekly': 0, 'Monthly': 0, 'Quarterly': 0, 'Annual': 0}
        
        result.append({
            'SAPID': sapid,
            'Name': name,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'Weekly': values['Weekly'],
            'Monthly': values['Monthly'],
            'Quarterly': values['Quarterly'],
            'Annual': values['Annual']
        })
    
    output_df = pd.DataFrame(result)
    
    # Prepare output data
    output_df.insert(0, 'CurrentDate', current_date_str)
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
    
    success = k9(
        resources_file=str(resources_file),
        jira_issues_file=str(jira_issues_file),
        output_dir=str(output_dir)
    )
    
    sys.exit(0 if success else 1)
