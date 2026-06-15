#!/usr/bin/env python3
"""
KPP K57 - UI Bugs Count
Counts bugs attributable to UI at Scrum Team level.
Uses JIRA bugs linked to commits with UI file changes.
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year


def get_description():
    """Return KPI description."""
    return "UI Bugs Count - Bugs attributable to UI at Scrum Team level"


def k57(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K57: UI Bugs Count at Scrum Team Level.
    
    Counts bugs that are attributable to UI changes by:
    1. Identifying bugs from JIRA (excluding Invalid/Duplicate)
    2. Linking bugs to GitHub commits via JIRA ID
    3. Checking if commits contain UI file changes (ui_screen, ui_component, ui_style)
    4. Counting at Scrum Team level (same count for all team members)
    5. Using created date for bug count
    
    Args:
        resources_file (str): Path to Resources.csv file
        jira_issues_file (str): Path to JIRAIssues.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k57-data.csv')
    github_commits_file = os.path.join(output_dir, 'github_commits.csv')
    commit_files_file = os.path.join(output_dir, 'github_commit_files.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K57 - UI Bugs Count (Scrum Team Level)")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")
    
    # Load resources
    print("Loading resources data...")
    try:
        resources_df = pd.read_csv(resources_file)
        resources = resources_df[['SAPID', 'Name', 'Scrum']].copy()
        resources['SAPID'] = resources['SAPID'].fillna(0).astype(int).astype(str)
        resources = resources[resources['Scrum'].notna()]
        resources = resources[resources['Scrum'] != '-NA-']
        print(f"  ✓ Loaded {len(resources)} resources with Scrum Team assignment")
    except Exception as e:
        print(f"  ✗ Error loading resources file: {e}")
        return False
    
    if resources.empty:
        print("  ✗ No resources data loaded")
        return False
    
    # Load JIRA issues
    print("Loading JIRA issues...")
    if not os.path.exists(jira_issues_file):
        print(f"  ✗ Error: {jira_issues_file} not found")
        return False
    
    try:
        jira_df = pd.read_csv(jira_issues_file)
        jira_df['Created'] = pd.to_datetime(jira_df['Created'], errors='coerce')
        jira_df = jira_df[jira_df['Created'].notna()]
        print(f"  ✓ Loaded {len(jira_df)} JIRA issues")
    except Exception as e:
        print(f"  ✗ Error loading JIRA issues: {e}")
        return False
    
    # Filter for bugs (excluding Invalid/Duplicate)
    print("Filtering for valid bugs...")
    bugs = jira_df[
        (jira_df['Issue Type'] == 'Bug') & 
        (~jira_df['Status'].isin(['Invalid', 'Duplicate']))
    ].copy()
    print(f"  ✓ Found {len(bugs)} valid bugs")
    
    if bugs.empty:
        print("  ⚠ Warning: No valid bugs found")
        # Create output with 0 values
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
    
    # Load GitHub commit files
    print("Loading GitHub commit files...")
    if not os.path.exists(commit_files_file):
        print(f"  ✗ Error: {commit_files_file} not found")
        print(f"      Please run 'python github_fetch.py fetch' to generate file details")
        return False
    
    try:
        files_df = pd.read_csv(commit_files_file)
        print(f"  ✓ Loaded {len(files_df)} file changes")
    except Exception as e:
        print(f"  ✗ Error loading commit files: {e}")
        return False
    
    # Identify UI-related file changes
    print("Identifying UI-related file changes...")
    ui_files = files_df[
        files_df['category'].isin(['ui_screen', 'ui_component', 'ui_style'])
    ].copy()
    
    ui_commit_shas = ui_files['commit_sha'].unique()
    print(f"  ✓ Found {len(ui_commit_shas)} commits with UI file changes")
    
    # Link bugs to UI commits via JIRA ID from files data
    print("Linking bugs to UI commits...")
    
    # Get unique commit_sha and jira_id pairs from UI files
    ui_commits_jira = ui_files[['commit_sha', 'jira_id']].drop_duplicates()
    ui_commits_jira = ui_commits_jira[ui_commits_jira['jira_id'].notna()]
    
    # Merge bugs with UI commits
    bugs_with_commits = bugs.merge(
        ui_commits_jira, 
        left_on='Key', 
        right_on='jira_id', 
        how='inner'
    )
    
    # Already filtered to UI commits, so these are all UI bugs
    ui_bugs = bugs_with_commits.copy()
    
    # Deduplicate by Issue key (one bug may have multiple commits)
    ui_bugs = ui_bugs.drop_duplicates(subset=['Key'])
    
    print(f"  ✓ Found {len(ui_bugs)} UI-related bugs")
    
    if ui_bugs.empty:
        print("  ⚠ Warning: No UI bugs found")
        # Create output with 0 values
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
    
    # Get Scrum Team for each bug via Assignee
    print("Mapping bugs to Scrum Teams...")
    ui_bugs_with_team = ui_bugs.merge(
        resources_df[['JIRA Name', 'Scrum']].drop_duplicates(subset=['JIRA Name']),
        left_on='Assignee',
        right_on='JIRA Name',
        how='left'
    )
    
    # For bugs without assignee match, try to get team from any commit author
    bugs_no_team = ui_bugs_with_team[ui_bugs_with_team['Scrum'].isna()].copy()
    if len(bugs_no_team) > 0:
        print(f"  ⚠ {len(bugs_no_team)} bugs have no Scrum Team from assignee, checking commit authors...")
        
        # Join with UI files to get author team
        bugs_no_team_files = bugs_no_team.merge(
            ui_files[['jira_id', 'author']].drop_duplicates(),
            left_on='Key',
            right_on='jira_id',
            how='left',
            suffixes=('', '_file')
        )
        
        bugs_no_team_files = bugs_no_team_files.merge(
            resources_df[['GitHUB Name', 'Scrum']].drop_duplicates(subset=['GitHUB Name']),
            left_on='author',
            right_on='GitHUB Name',
            how='left',
            suffixes=('_old', '_new')
        )
        
        # Update original dataframe with found teams
        for idx, row in bugs_no_team_files.iterrows():
            if pd.notna(row.get('Scrum_new')):
                mask = ui_bugs_with_team['Key'] == row['Key']
                ui_bugs_with_team.loc[mask, 'Scrum'] = row['Scrum_new']
    
    # Remove bugs with no team assignment
    ui_bugs_with_team = ui_bugs_with_team[ui_bugs_with_team['Scrum'].notna()]
    print(f"  ✓ Mapped {len(ui_bugs_with_team)} UI bugs to Scrum Teams")
    
    # Add time period columns based on Created date
    ui_bugs_with_team['Week'] = ui_bugs_with_team['Created'].apply(get_week_number)
    ui_bugs_with_team['Month'] = ui_bugs_with_team['Created'].apply(get_month_string)
    ui_bugs_with_team['Quarter'] = ui_bugs_with_team['Created'].apply(get_quarter_string)
    ui_bugs_with_team['FiscalYear'] = ui_bugs_with_team['Created'].apply(lambda x: get_fiscal_year(x, fiscal_start_month))
    
    # Calculate current period values
    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_fiscal_year = get_fiscal_year(current_dt, fiscal_start_month)
    
    print("Counting UI bugs per Scrum Team...")
    
    # Count bugs per team for each period
    team_counts = {}
    
    for scrum_team in ui_bugs_with_team['Scrum'].unique():
        team_bugs = ui_bugs_with_team[ui_bugs_with_team['Scrum'] == scrum_team]
        
        weekly = len(team_bugs[team_bugs['Week'] == current_week])
        monthly = len(team_bugs[team_bugs['Month'] == current_month])
        quarterly = len(team_bugs[team_bugs['Quarter'] == current_quarter])
        annual = len(team_bugs[team_bugs['FiscalYear'] == current_fiscal_year])
        
        team_counts[scrum_team] = {
            'Weekly': weekly,
            'Monthly': monthly,
            'Quarterly': quarterly,
            'Annual': annual
        }
    
    print(f"  ✓ Calculated counts for {len(team_counts)} Scrum Teams")
    
    # Create output for all individuals with their team's count
    print("Assigning team counts to all individuals...")
    result = []
    
    for _, emp in resources.iterrows():
        scrum_team = emp['Scrum']
        counts = team_counts.get(scrum_team, {'Weekly': 0, 'Monthly': 0, 'Quarterly': 0, 'Annual': 0})
        
        result.append({
            'CurrentDate': current_date_str,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'SAPID': emp['SAPID'],
            'Name': emp['Name'],
            'Weekly': counts['Weekly'],
            'Monthly': counts['Monthly'],
            'Quarterly': counts['Quarterly'],
            'Annual': counts['Annual']
        })
    
    # Create DataFrame and save
    output_df = pd.DataFrame(result)
    output_df = output_df.sort_values(['Name'])
    
    # Save to CSV
    output_df.to_csv(output_file, index=False)
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"{'='*60}")
    print(f"Total UI bugs found: {len(ui_bugs_with_team)}")
    print(f"Scrum Teams with UI bugs: {len(team_counts)}")
    print(f"Individuals in output: {len(output_df)}")
    print(f"\nTop 5 teams by Annual UI bug count:")
    team_summary = output_df.groupby('Name').first().reset_index()
    # Get unique team counts (take first person from each team)
    unique_teams = output_df.drop_duplicates(subset=['Week', 'Month', 'Quarter', 'Year']).copy()
    if len(unique_teams) > 0:
        # Group by the team count values to show unique teams
        team_data = []
        for scrum_team, counts in team_counts.items():
            team_data.append({
                'Scrum Team': scrum_team,
                'Weekly': counts['Weekly'],
                'Monthly': counts['Monthly'],
                'Quarterly': counts['Quarterly'],
                'Annual': counts['Annual']
            })
        team_df = pd.DataFrame(team_data).sort_values('Annual', ascending=False)
        print(team_df.head().to_string(index=False))
    
    print(f"\n  ✓ Saved to {output_file}")
    print(f"{'='*60}\n")
    
    return True


def main():
    """Main function for testing K57 independently."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    resources_file = os.path.join(project_root, 'config', 'Resources.csv')
    jira_issues_file = os.path.join(project_root, 'output', 'JIRAIssues.csv')
    output_dir = os.path.join(project_root, 'output')
    
    success = k57(resources_file, jira_issues_file, output_dir)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
