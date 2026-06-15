#!/usr/bin/env python3
"""
Replan Tracker Analysis
Tracks sprint changes and replanning for Stories and Epics.

Metrics calculated:
- Number of sprint changes per issue
- Timeline of sprint changes
- Replan rate by issue type, priority, team, and scrum
- Stories/Epics moved between sprints
- Sprint stability metrics
"""

import csv
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any
import os
import sys

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
HISTORY_FILE = os.path.join(PROJECT_ROOT, 'output', 'JIRAIssues_History.csv')
ISSUES_FILE = os.path.join(PROJECT_ROOT, 'output', 'JIRAIssues.csv')
RESOURCES_FILE = os.path.join(PROJECT_ROOT, 'config', 'Resources.csv')
OUTPUT_FILE = os.path.join(PROJECT_ROOT, 'output', 'replan_tracker.csv')


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


def analyze_sprint_changes(key: str, history_df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze sprint changes for a given issue.
    
    Groups changes made on the same date as a single replan.
    
    Returns:
        Dict with sprint change metrics
    """
    # Filter history for this issue and Sprint changes only
    sprint_history = history_df[
        (history_df['Key'] == key) & 
        (history_df['Field'] == 'Sprint')
    ].sort_values('ChangeDate')
    
    if len(sprint_history) == 0:
        return {
            'replan_count': 0,
            'sprint_changes': [],
            'first_sprint': 'None',
            'final_sprint': 'None',
            'days_to_first_replan': None,
            'total_sprints': 0
        }
    
    # Group changes by date and keep only the final value for each date
    changes_by_date = {}
    unique_sprints = set()
    
    for idx, row in sprint_history.iterrows():
        to_sprint = row['ToValue']
        change_date = row['ChangeDate'].date()  # Group by date only (ignore time)
        author = row['Author']
        
        # Normalize empty/None values
        current_sprint = str(to_sprint) if pd.notna(to_sprint) and to_sprint else None
        
        # Keep the final sprint value for each date
        changes_by_date[change_date] = {
            'date': change_date,
            'to': current_sprint if current_sprint else 'nan',
            'author': author
        }
        
        # Track unique named sprints (exclude None/empty)
        if current_sprint:
            unique_sprints.add(current_sprint)
    
    # Sort changes by date and filter out consecutive duplicates
    sorted_dates = sorted(changes_by_date.keys())
    sprint_changes = []
    previous_sprint = None
    
    for change_date in sorted_dates:
        change = changes_by_date[change_date]
        current_sprint = change['to']
        
        # Only record changes where the sprint actually changed from the previous value
        if current_sprint != previous_sprint:
            sprint_changes.append(change)
            previous_sprint = current_sprint
    
    # Determine first and final sprint (excluding None/empty values)
    first_sprint = 'None'
    final_sprint = 'None'
    
    if sprint_changes:
        # Find first non-None sprint
        for change in sprint_changes:
            if change['to'] != 'nan':
                first_sprint = change['to']
                break
        
        # Find last non-None sprint
        for change in reversed(sprint_changes):
            if change['to'] != 'nan':
                final_sprint = change['to']
                break
    
    # Replan count: number of meaningful changes minus 1 (first assignment is not a replan)
    # Only count transitions to actual sprint values (not to 'nan')
    meaningful_changes = [ch for ch in sprint_changes if ch['to'] != 'nan']
    replan_count = max(0, len(meaningful_changes) - 1)  # First sprint assignment is not a replan
    
    return {
        'replan_count': replan_count,
        'sprint_changes': sprint_changes,
        'first_sprint': first_sprint,
        'final_sprint': final_sprint,
        'total_sprints': len(unique_sprints)
    }


def track_replans(history_df: pd.DataFrame, issues_df: pd.DataFrame, resources_mapping: Dict[str, Dict[str, str]]) -> pd.DataFrame:
    """Track replans for Stories and Epics.
    
    Returns:
        DataFrame with replan metrics per issue
    """
    # Filter for Stories and Epics
    relevant_issues = issues_df[
        issues_df['Issue Type'].isin(['Story', 'Epic', 'Task'])
    ].copy()
    
    if len(relevant_issues) == 0:
        print("⚠️  No Stories, Epics, or Tasks found in the issues data.")
        return pd.DataFrame()
    
    print(f"Analyzing {len(relevant_issues)} Stories/Epics/Tasks for replanning...")
    
    results = []
    
    for idx, issue in relevant_issues.iterrows():
        key = issue['Key']
        issue_type = issue['Issue Type']
        priority = issue['Priority']
        current_sprint = issue['Sprint']
        status = issue['Status']
        created = issue['Created']
        story_points = issue.get('Story Points', 0)
        assignee = issue.get('Assignee', '')
        
        # Extract project from key
        project = extract_project(key)
        
        # Get team and scrum from resources mapping
        resource_info = resources_mapping.get(str(assignee).strip(), {})
        team = resource_info.get('team', 'Unknown')
        scrum = resource_info.get('scrum', 'Unknown')
        
        # Analyze sprint changes
        replan_data = analyze_sprint_changes(key, history_df)
        
        # Build sprint change timeline
        sprint_timeline = ' → '.join([
            f"{('No Plan' if change['to'] == 'nan' else change['to'])} ({change['date'].strftime('%Y-%m-%d')})"
            for change in replan_data['sprint_changes']
        ])
        
        # Build result row
        result = {
            'Key': key,
            'Project': project,
            'Team': team,
            'Scrum': scrum,
            'Assignee': assignee,
            'Issue_Type': issue_type,
            'Priority': priority,
            'Story_Points': story_points,
            'Current_Sprint': current_sprint,
            'Current_Status': status,
            'Created': created,
            'Replan_Count': replan_data['replan_count'],
            'Total_Sprints': replan_data['total_sprints'],
            'First_Sprint': replan_data['first_sprint'],
            'Final_Sprint': replan_data['final_sprint'],
            'Sprint_Timeline': sprint_timeline if sprint_timeline else 'No changes'
        }
        
        results.append(result)
    
    return pd.DataFrame(results)


def calculate_replan_summary(replan_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate summary statistics for replanning.
    
    Returns:
        DataFrame with aggregated replan metrics
    """
    if len(replan_df) == 0:
        return pd.DataFrame()
    
    # Overall summary
    summary = replan_df.groupby('Issue_Type').agg({
        'Key': 'count',
        'Replan_Count': ['sum', 'mean', 'max'],
        'Total_Sprints': 'mean',
        'Story_Points': 'sum'
    }).round(2)
    
    summary.columns = ['_'.join(col).strip() for col in summary.columns.values]
    summary = summary.rename(columns={
        'Key_count': 'Issue_Count',
        'Replan_Count_sum': 'Total_Replans',
        'Replan_Count_mean': 'Avg_Replans_Per_Issue',
        'Replan_Count_max': 'Max_Replans',
        'Total_Sprints_mean': 'Avg_Sprints_Per_Issue',
        'Story_Points_sum': 'Total_Story_Points'
    })
    
    return summary.reset_index()


def calculate_priority_breakdown(replan_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate replan breakdown by priority.
    
    Returns:
        DataFrame with replan metrics by priority
    """
    if len(replan_df) == 0:
        return pd.DataFrame()
    
    priority_summary = replan_df.groupby(['Issue_Type', 'Priority']).agg({
        'Key': 'count',
        'Replan_Count': ['sum', 'mean']
    }).round(2)
    
    priority_summary.columns = ['_'.join(col).strip() for col in priority_summary.columns.values]
    priority_summary = priority_summary.rename(columns={
        'Key_count': 'Count',
        'Replan_Count_sum': 'Total_Replans',
        'Replan_Count_mean': 'Avg_Replans'
    })
    
    return priority_summary.reset_index()


def calculate_team_summary(replan_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate replan summary by team.
    
    Returns:
        DataFrame with replan metrics by team
    """
    if len(replan_df) == 0:
        return pd.DataFrame()
    
    # Filter out Unknown team
    team_df = replan_df[replan_df['Team'] != 'Unknown'].copy()
    
    if len(team_df) == 0:
        return pd.DataFrame()
    
    team_summary = team_df.groupby('Team').agg({
        'Key': 'count',
        'Replan_Count': ['sum', 'mean', 'max'],
        'Total_Sprints': 'mean',
        'Story_Points': 'sum'
    }).round(2)
    
    team_summary.columns = ['_'.join(col).strip() for col in team_summary.columns.values]
    team_summary = team_summary.rename(columns={
        'Key_count': 'Issue_Count',
        'Replan_Count_sum': 'Total_Replans',
        'Replan_Count_mean': 'Avg_Replans_Per_Issue',
        'Replan_Count_max': 'Max_Replans',
        'Total_Sprints_mean': 'Avg_Sprints_Per_Issue',
        'Story_Points_sum': 'Total_Story_Points'
    })
    
    # Calculate replan rate per team
    issues_with_replans = team_df[team_df['Replan_Count'] > 0].groupby('Team')['Key'].count()
    team_summary['Replan_Rate_%'] = ((issues_with_replans / team_summary['Issue_Count']) * 100).round(1)
    team_summary['Replan_Rate_%'] = team_summary['Replan_Rate_%'].fillna(0)
    
    return team_summary.reset_index().sort_values('Total_Replans', ascending=False)


def calculate_scrum_summary(replan_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate replan summary by scrum.
    
    Returns:
        DataFrame with replan metrics by scrum
    """
    if len(replan_df) == 0:
        return pd.DataFrame()
    
    # Filter out Unknown scrum
    scrum_df = replan_df[replan_df['Scrum'] != 'Unknown'].copy()
    
    if len(scrum_df) == 0:
        return pd.DataFrame()
    
    scrum_summary = scrum_df.groupby('Scrum').agg({
        'Key': 'count',
        'Replan_Count': ['sum', 'mean', 'max'],
        'Total_Sprints': 'mean',
        'Story_Points': 'sum'
    }).round(2)
    
    scrum_summary.columns = ['_'.join(col).strip() for col in scrum_summary.columns.values]
    scrum_summary = scrum_summary.rename(columns={
        'Key_count': 'Issue_Count',
        'Replan_Count_sum': 'Total_Replans',
        'Replan_Count_mean': 'Avg_Replans_Per_Issue',
        'Replan_Count_max': 'Max_Replans',
        'Total_Sprints_mean': 'Avg_Sprints_Per_Issue',
        'Story_Points_sum': 'Total_Story_Points'
    })
    
    # Calculate replan rate per scrum
    issues_with_replans = scrum_df[scrum_df['Replan_Count'] > 0].groupby('Scrum')['Key'].count()
    scrum_summary['Replan_Rate_%'] = ((issues_with_replans / scrum_summary['Issue_Count']) * 100).round(1)
    scrum_summary['Replan_Rate_%'] = scrum_summary['Replan_Rate_%'].fillna(0)
    
    return scrum_summary.reset_index().sort_values('Total_Replans', ascending=False)


def enrich_with_epic_info(replan_df: pd.DataFrame, issues_df: pd.DataFrame) -> pd.DataFrame:
    """Add Epic_Key, Epic_Summary, and Description columns to the replan DataFrame.

    Resolution logic (matches backend _build_epic_info_map):
    - If issue is an Epic -> epic_key = own key
    - Otherwise traverse Parent up to 2 levels to find an Epic
    - Fallback: 'NA'
    """
    if replan_df.empty or issues_df.empty:
        replan_df['Epic_Key'] = 'NA'
        replan_df['Epic_Summary'] = ''
        replan_df['Description'] = ''
        return replan_df

    # Build lookup maps from JIRAIssues
    type_map: Dict[str, str] = {}
    parent_map: Dict[str, str] = {}
    summary_map: Dict[str, str] = {}

    for _, row in issues_df.iterrows():
        k = str(row.get('Key', '')).strip()
        if not k:
            continue
        type_map[k] = str(row.get('Issue Type', '')).strip().lower()
        parent_map[k] = str(row.get('Parent', '')).strip() if pd.notna(row.get('Parent')) else ''
        summary_map[k] = str(row.get('Summary', '')).strip() if pd.notna(row.get('Summary')) else ''

    def resolve_epic(key: str):
        if not key or key not in type_map:
            return 'NA', ''
        if type_map[key] == 'epic':
            return key, summary_map.get(key, '')
        parent = parent_map.get(key, '')
        if parent and parent in type_map:
            if type_map[parent] == 'epic':
                return parent, summary_map.get(parent, '')
            grandparent = parent_map.get(parent, '')
            if grandparent and grandparent in type_map and type_map[grandparent] == 'epic':
                return grandparent, summary_map.get(grandparent, '')
        return 'NA', ''

    epic_keys = []
    epic_summaries = []
    descriptions = []

    for k in replan_df['Key']:
        ek, es = resolve_epic(str(k).strip())
        epic_keys.append(ek)
        epic_summaries.append(es)
        descriptions.append(summary_map.get(str(k).strip(), ''))

    replan_df = replan_df.copy()
    replan_df['Epic_Key'] = epic_keys
    replan_df['Epic_Summary'] = epic_summaries
    replan_df['Description'] = descriptions
    return replan_df


def identify_high_replan_issues(replan_df: pd.DataFrame, threshold: int = 3) -> pd.DataFrame:
    """Identify issues with high replan counts.
    
    Args:
        threshold: Minimum number of replans to be considered high
    
    Returns:
        DataFrame with high replan issues
    """
    if len(replan_df) == 0:
        return pd.DataFrame()
    
    high_replan = replan_df[replan_df['Replan_Count'] >= threshold].copy()
    high_replan = high_replan.sort_values('Replan_Count', ascending=False)
    
    return high_replan[[
        'Key', 'Project', 'Team', 'Scrum', 'Issue_Type', 'Priority', 'Story_Points',
        'Replan_Count', 'Current_Status', 'Sprint_Timeline'
    ]]


def main():
    """Main execution."""
    print("=" * 60)
    print("Replan Tracker Analysis")
    print("=" * 60)
    
    # Load data
    print("\n📊 Loading data...")
    history_df = load_history_data()
    issues_df = load_issues_data()
    resources_mapping = load_resources_mapping()
    
    print(f"   Loaded {len(history_df)} history entries")
    print(f"   Loaded {len(issues_df)} issues")
    
    # Track replans
    print("\n🔍 Tracking replans...")
    replan_df = track_replans(history_df, issues_df, resources_mapping)
    
    if len(replan_df) == 0:
        print("❌ No replan data generated.")
        return
    
    # Calculate summaries
    print("\n📈 Calculating summary statistics...")
    summary_df = calculate_replan_summary(replan_df)
    priority_df = calculate_priority_breakdown(replan_df)
    team_summary_df = calculate_team_summary(replan_df)
    scrum_summary_df = calculate_scrum_summary(replan_df)
    high_replan_df = identify_high_replan_issues(replan_df, threshold=3)

    # Enrich with Epic and Description info from JIRAIssues
    print("\n🔗 Enriching with Epic information...")
    replan_df = enrich_with_epic_info(replan_df, issues_df)
    enriched_with_epic = (replan_df['Epic_Key'] != 'NA').sum()
    print(f"   {enriched_with_epic} issues linked to an Epic")

    # Save results
    print(f"\n💾 Saving results to {OUTPUT_FILE}...")
    replan_df.to_csv(OUTPUT_FILE, index=False)
    
    # Save summaries
    summary_file = OUTPUT_FILE.replace('.csv', '_summary.csv')
    summary_df.to_csv(summary_file, index=False)
    
    priority_file = OUTPUT_FILE.replace('.csv', '_by_priority.csv')
    priority_df.to_csv(priority_file, index=False)
    
    team_summary_file = OUTPUT_FILE.replace('.csv', '_summary_by_team.csv')
    if len(team_summary_df) > 0:
        team_summary_df.to_csv(team_summary_file, index=False)
    
    scrum_summary_file = OUTPUT_FILE.replace('.csv', '_summary_by_scrum.csv')
    if len(scrum_summary_df) > 0:
        scrum_summary_df.to_csv(scrum_summary_file, index=False)
    
    high_replan_file = OUTPUT_FILE.replace('.csv', '_high_replan.csv')
    if len(high_replan_df) > 0:
        high_replan_df.to_csv(high_replan_file, index=False)
    
    # Display results
    print("\n" + "=" * 60)
    print("REPLAN SUMMARY BY ISSUE TYPE")
    print("=" * 60)
    print(summary_df.to_string(index=False))
    
    if len(team_summary_df) > 0:
        print("\n" + "=" * 60)
        print("REPLAN SUMMARY BY TEAM")
        print("=" * 60)
        print(team_summary_df.to_string(index=False))
    
    if len(scrum_summary_df) > 0:
        print("\n" + "=" * 60)
        print("REPLAN SUMMARY BY SCRUM")
        print("=" * 60)
        print(scrum_summary_df.to_string(index=False))
    
    print("\n" + "=" * 60)
    print("REPLAN BREAKDOWN BY PRIORITY")
    print("=" * 60)
    print(priority_df.to_string(index=False))
    
    if len(high_replan_df) > 0:
        print("\n" + "=" * 60)
        print(f"HIGH REPLAN ISSUES (>= 3 replans)")
        print("=" * 60)
        print(high_replan_df.head(10).to_string(index=False))
    
    # Calculate replan rate
    total_issues = len(replan_df)
    issues_with_replans = len(replan_df[replan_df['Replan_Count'] > 0])
    replan_rate = (issues_with_replans / total_issues * 100) if total_issues > 0 else 0
    
    print("\n" + "=" * 60)
    print("KEY METRICS")
    print("=" * 60)
    print(f"Total Issues Analyzed: {total_issues}")
    print(f"Issues with Replans: {issues_with_replans}")
    print(f"Replan Rate: {replan_rate:.1f}%")
    print(f"Total Replans: {replan_df['Replan_Count'].sum()}")
    print(f"Avg Replans per Issue: {replan_df['Replan_Count'].mean():.2f}")
    
    print(f"\n✅ Analysis complete!")
    print(f"   Detailed results: {OUTPUT_FILE}")
    print(f"   Summary by Issue Type: {summary_file}")
    if len(team_summary_df) > 0:
        print(f"   Summary by Team: {team_summary_file}")
    if len(scrum_summary_df) > 0:
        print(f"   Summary by Scrum: {scrum_summary_file}")
    print(f"   By Priority: {priority_file}")
    if len(high_replan_df) > 0:
        print(f"   High Replan Issues: {high_replan_file}")


if __name__ == '__main__':
    main()
