#!/usr/bin/env python3
"""
Bug Cycle Time Analysis
Calculates cycle times for bugs based on status transitions from history data.

Metrics calculated:
- Time in each status (New, In Progress, Code Review, Testing, Done, etc.)
- Total cycle time (Created to Resolved)
- Lead time (Created to Done)
- Wait times between transitions
- Number of rework cycles (returns to previous states)
- Average cycle times by priority, team, and scrum
"""

import csv
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any
import os
import sys

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
HISTORY_FILE = os.path.join(PROJECT_ROOT, 'output', 'JIRAIssues_History.csv')
ISSUES_FILE = os.path.join(PROJECT_ROOT, 'output', 'JIRAIssues.csv')
RESOURCES_FILE = os.path.join(PROJECT_ROOT, 'config', 'Resources.csv')
OUTPUT_FILE = os.path.join(PROJECT_ROOT, 'output', 'bug_cycle_time.csv')


def load_resources_mapping() -> Dict[str, Dict[str, str]]:
    """Load resources mapping from Resources.csv.
    
    Returns:
        Dict mapping assignee name to team and scrum info
    """
    if not os.path.exists(RESOURCES_FILE):
        print(f"⚠️  Warning: Resources file not found: {RESOURCES_FILE}")
        print("   Team and Scrum columns will show 'Unknown'")
        return {}
    
    try:
        df = pd.read_csv(RESOURCES_FILE)
        mapping = {}
        
        for idx, row in df.iterrows():
            name = row.get('Name', '')
            jira_name = row.get('JIRA Name', '')
            team = row.get('Team', 'Unknown')
            scrum = row.get('Scrum', 'Unknown')
            
            # Map both Name and JIRA Name to same team/scrum
            if pd.notna(name) and name:
                mapping[str(name).strip()] = {'team': str(team), 'scrum': str(scrum)}
            if pd.notna(jira_name) and jira_name and jira_name != '-NA-':
                mapping[str(jira_name).strip()] = {'team': str(team), 'scrum': str(scrum)}
        
        print(f"   Loaded {len(mapping)} resource mappings from Resources.csv")
        return mapping
    except Exception as e:
        print(f"⚠️  Error loading resources: {e}")
        return {}


def extract_project(key: str) -> str:
    """Extract project from issue key (e.g., 'AS-123' -> 'AS')."""
    if pd.isna(key) or not isinstance(key, str):
        return 'Unknown'
    return key.split('-')[0] if '-' in key else 'Unknown'


def load_history_data() -> pd.DataFrame:
    """Load history data from CSV."""
    if not os.path.exists(HISTORY_FILE):
        print(f"❌ Error: History file not found: {HISTORY_FILE}")
        print("   Please run jira_fetch.py first to generate history data.")
        sys.exit(1)
    
    df = pd.read_csv(HISTORY_FILE)
    df['ChangeDate'] = pd.to_datetime(df['ChangeDate'])
    return df


def load_issues_data() -> pd.DataFrame:
    """Load issues data from CSV."""
    if not os.path.exists(ISSUES_FILE):
        print(f"❌ Error: Issues file not found: {ISSUES_FILE}")
        sys.exit(1)
    
    df = pd.read_csv(ISSUES_FILE)
    df['Created'] = pd.to_datetime(df['Created'])
    df['Updated'] = pd.to_datetime(df['Updated'])
    return df


def calculate_status_durations(key: str, history_df: pd.DataFrame, created_date: datetime) -> Dict[str, Any]:
    """Calculate time spent in each status for a given issue.
    
    Returns:
        Dict with status durations, total cycle time, and transition count
    """
    # Filter history for this issue and status changes only
    issue_history = history_df[
        (history_df['Key'] == key) & 
        (history_df['Field'] == 'status')
    ].sort_values('ChangeDate')
    
    if len(issue_history) == 0:
        return {
            'status_durations': {},
            'total_cycle_time_hours': 0,
            'total_cycle_time_days': 0,
            'transition_count': 0,
            'rework_count': 0,
            'first_status': 'Unknown',
            'final_status': 'Unknown'
        }
    
    # Calculate durations
    status_durations = {}
    rework_count = 0
    visited_statuses = set()
    
    # Start from creation date
    current_status = issue_history.iloc[0]['FromValue'] or 'New'
    current_time = created_date
    
    for idx, row in issue_history.iterrows():
        next_status = row['ToValue']
        next_time = row['ChangeDate']
        
        # Calculate duration in current status
        duration = (next_time - current_time).total_seconds() / 3600  # hours
        
        if current_status in status_durations:
            status_durations[current_status] += duration
        else:
            status_durations[current_status] = duration
        
        # Check for rework (returning to a previously visited status)
        if next_status in visited_statuses:
            rework_count += 1
        
        visited_statuses.add(current_status)
        
        # Move to next status
        current_status = next_status
        current_time = next_time
    
    # Calculate total cycle time
    first_change = issue_history.iloc[0]['ChangeDate']
    last_change = issue_history.iloc[-1]['ChangeDate']
    total_cycle_time_hours = (last_change - created_date).total_seconds() / 3600
    total_cycle_time_days = total_cycle_time_hours / 24
    
    return {
        'status_durations': status_durations,
        'total_cycle_time_hours': total_cycle_time_hours,
        'total_cycle_time_days': total_cycle_time_days,
        'transition_count': len(issue_history),
        'rework_count': rework_count,
        'first_status': issue_history.iloc[0]['FromValue'] or 'New',
        'final_status': issue_history.iloc[-1]['ToValue']
    }


def analyze_bug_cycle_times(history_df: pd.DataFrame, issues_df: pd.DataFrame, resources_mapping: Dict[str, Dict[str, str]]) -> pd.DataFrame:
    """Analyze cycle times for all bugs.
    
    Returns:
        DataFrame with cycle time metrics per bug
    """
    # Filter for bugs only
    bugs = issues_df[issues_df['Issue Type'] == 'Bug'].copy()
    
    if len(bugs) == 0:
        print("⚠️  No bugs found in the issues data.")
        return pd.DataFrame()
    
    print(f"Analyzing {len(bugs)} bugs...")
    
    results = []
    
    for idx, bug in bugs.iterrows():
        key = bug['Key']
        created = bug['Created']
        priority = bug['Priority']
        status = bug['Status']
        assignee = bug.get('Assignee', '')
        
        # Extract project from key
        project = extract_project(key)
        
        # Get team and scrum from resources mapping
        resource_info = resources_mapping.get(str(assignee).strip(), {})
        team = resource_info.get('team', 'Unknown')
        scrum = resource_info.get('scrum', 'Unknown')
        
        # Calculate cycle times
        cycle_data = calculate_status_durations(key, history_df, created)
        
        # Build result row
        result = {
            'Key': key,
            'Project': project,
            'Team': team,
            'Scrum': scrum,
            'Assignee': assignee,
            'Priority': priority,
            'Current_Status': status,
            'Created': created,
            'Total_Cycle_Time_Days': round(cycle_data['total_cycle_time_days'], 2),
            'Total_Cycle_Time_Hours': round(cycle_data['total_cycle_time_hours'], 2),
            'Transition_Count': cycle_data['transition_count'],
            'Rework_Count': cycle_data['rework_count'],
            'First_Status': cycle_data['first_status'],
            'Final_Status': cycle_data['final_status']
        }
        
        # Add individual status durations
        for status_name, duration in cycle_data['status_durations'].items():
            col_name = f'Time_in_{status_name.replace(" ", "_")}_Hours'
            result[col_name] = round(duration, 2)
        
        results.append(result)
    
    return pd.DataFrame(results)


def calculate_summary_stats(cycle_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate summary statistics by priority.
    
    Returns:
        DataFrame with aggregated metrics by priority
    """
    if len(cycle_df) == 0:
        return pd.DataFrame()
    
    summary = cycle_df.groupby('Priority').agg({
        'Key': 'count',
        'Total_Cycle_Time_Days': ['mean', 'median', 'min', 'max'],
        'Transition_Count': 'mean',
        'Rework_Count': 'mean'
    }).round(2)
    
    summary.columns = ['_'.join(col).strip() for col in summary.columns.values]
    summary = summary.rename(columns={
        'Key_count': 'Bug_Count',
        'Total_Cycle_Time_Days_mean': 'Avg_Cycle_Time_Days',
        'Total_Cycle_Time_Days_median': 'Median_Cycle_Time_Days',
        'Total_Cycle_Time_Days_min': 'Min_Cycle_Time_Days',
        'Total_Cycle_Time_Days_max': 'Max_Cycle_Time_Days',
        'Transition_Count_mean': 'Avg_Transitions',
        'Rework_Count_mean': 'Avg_Rework_Count'
    })
    
    return summary.reset_index()


def calculate_team_summary(cycle_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate summary statistics by team.
    
    Returns:
        DataFrame with aggregated metrics by team
    """
    if len(cycle_df) == 0:
        return pd.DataFrame()
    
    # Filter out Unknown team
    team_df = cycle_df[cycle_df['Team'] != 'Unknown'].copy()
    
    if len(team_df) == 0:
        return pd.DataFrame()
    
    team_summary = team_df.groupby('Team').agg({
        'Key': 'count',
        'Total_Cycle_Time_Days': ['mean', 'median', 'min', 'max'],
        'Transition_Count': 'mean',
        'Rework_Count': 'mean'
    }).round(2)
    
    team_summary.columns = ['_'.join(col).strip() for col in team_summary.columns.values]
    team_summary = team_summary.rename(columns={
        'Key_count': 'Bug_Count',
        'Total_Cycle_Time_Days_mean': 'Avg_Cycle_Time_Days',
        'Total_Cycle_Time_Days_median': 'Median_Cycle_Time_Days',
        'Total_Cycle_Time_Days_min': 'Min_Cycle_Time_Days',
        'Total_Cycle_Time_Days_max': 'Max_Cycle_Time_Days',
        'Transition_Count_mean': 'Avg_Transitions',
        'Rework_Count_mean': 'Avg_Rework_Count'
    })
    
    return team_summary.reset_index().sort_values('Avg_Cycle_Time_Days', ascending=False)


def calculate_scrum_summary(cycle_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate summary statistics by scrum.
    
    Returns:
        DataFrame with aggregated metrics by scrum
    """
    if len(cycle_df) == 0:
        return pd.DataFrame()
    
    # Filter out Unknown scrum
    scrum_df = cycle_df[cycle_df['Scrum'] != 'Unknown'].copy()
    
    if len(scrum_df) == 0:
        return pd.DataFrame()
    
    scrum_summary = scrum_df.groupby('Scrum').agg({
        'Key': 'count',
        'Total_Cycle_Time_Days': ['mean', 'median', 'min', 'max'],
        'Transition_Count': 'mean',
        'Rework_Count': 'mean'
    }).round(2)
    
    scrum_summary.columns = ['_'.join(col).strip() for col in scrum_summary.columns.values]
    scrum_summary = scrum_summary.rename(columns={
        'Key_count': 'Bug_Count',
        'Total_Cycle_Time_Days_mean': 'Avg_Cycle_Time_Days',
        'Total_Cycle_Time_Days_median': 'Median_Cycle_Time_Days',
        'Total_Cycle_Time_Days_min': 'Min_Cycle_Time_Days',
        'Total_Cycle_Time_Days_max': 'Max_Cycle_Time_Days',
        'Transition_Count_mean': 'Avg_Transitions',
        'Rework_Count_mean': 'Avg_Rework_Count'
    })
    
    return scrum_summary.reset_index().sort_values('Avg_Cycle_Time_Days', ascending=False)


def main():
    """Main execution."""
    print("=" * 60)
    print("Bug Cycle Time Analysis")
    print("=" * 60)
    
    # Load data
    print("\n📊 Loading data...")
    history_df = load_history_data()
    issues_df = load_issues_data()
    resources_mapping = load_resources_mapping()
    
    print(f"   Loaded {len(history_df)} history entries")
    print(f"   Loaded {len(issues_df)} issues")
    
    # Analyze cycle times
    print("\n🔍 Analyzing bug cycle times...")
    cycle_df = analyze_bug_cycle_times(history_df, issues_df, resources_mapping)
    
    if len(cycle_df) == 0:
        print("❌ No cycle time data generated.")
        return
    
    # Calculate summary stats
    print("\n📈 Calculating summary statistics...")
    summary_df = calculate_summary_stats(cycle_df)
    team_summary_df = calculate_team_summary(cycle_df)
    scrum_summary_df = calculate_scrum_summary(cycle_df)
    
    # Save results
    print(f"\n💾 Saving results to {OUTPUT_FILE}...")
    cycle_df.to_csv(OUTPUT_FILE, index=False)
    
    # Save summary
    summary_file = OUTPUT_FILE.replace('.csv', '_summary.csv')
    summary_df.to_csv(summary_file, index=False)
    
    # Save team summary
    team_summary_file = OUTPUT_FILE.replace('.csv', '_summary_by_team.csv')
    if len(team_summary_df) > 0:
        team_summary_df.to_csv(team_summary_file, index=False)
    
    # Save scrum summary
    scrum_summary_file = OUTPUT_FILE.replace('.csv', '_summary_by_scrum.csv')
    if len(scrum_summary_df) > 0:
        scrum_summary_df.to_csv(scrum_summary_file, index=False)
    
    # Display summary
    print("\n" + "=" * 60)
    print("SUMMARY BY PRIORITY")
    print("=" * 60)
    print(summary_df.to_string(index=False))
    
    if len(team_summary_df) > 0:
        print("\n" + "=" * 60)
        print("SUMMARY BY TEAM")
        print("=" * 60)
        print(team_summary_df.to_string(index=False))
    
    if len(scrum_summary_df) > 0:
        print("\n" + "=" * 60)
        print("SUMMARY BY SCRUM")
        print("=" * 60)
        print(scrum_summary_df.to_string(index=False))
    
    print("\n" + "=" * 60)
    print("TOP 10 LONGEST CYCLE TIMES")
    print("=" * 60)
    top_10 = cycle_df.nlargest(10, 'Total_Cycle_Time_Days')[
        ['Key', 'Project', 'Team', 'Scrum', 'Priority', 'Total_Cycle_Time_Days', 'Current_Status', 'Rework_Count']
    ]
    print(top_10.to_string(index=False))
    
    print(f"\n✅ Analysis complete!")
    print(f"   Detailed results: {OUTPUT_FILE}")
    print(f"   Summary by Priority: {summary_file}")
    if len(team_summary_df) > 0:
        print(f"   Summary by Team: {team_summary_file}")
    if len(scrum_summary_df) > 0:
        print(f"   Summary by Scrum: {scrum_summary_file}")


if __name__ == '__main__':
    main()
