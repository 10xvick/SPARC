#!/usr/bin/env python3
"""
KPP K38 - Security Bugs Count
Counts bugs tagged with security-related labels at Team level.
"""

import pandas as pd
import os
from datetime import datetime, date, timedelta
from kpi_helpers import get_date_strings


def get_description():
    """Return KPI description."""
    return "Security Bugs Count - Counts bugs tagged with security-related labels at Team level"


def normalize_label(label):
    """
    Normalize label to handle typos and variations.
    Converts underscores to hyphens, removes trailing dots, and makes lowercase for comparison.
    """
    if pd.isna(label) or not label:
        return ""
    return str(label).lower().replace('_', '-').rstrip('.').strip()


def contains_security_label(labels_str, security_labels_normalized):
    """
    Check if any security-related label exists in the Labels column.
    
    Args:
        labels_str: String containing comma-separated labels
        security_labels_normalized: Set of normalized security labels to check
    
    Returns:
        bool: True if any security label is found
    """
    if pd.isna(labels_str) or not labels_str:
        return False
    
    # Split by comma and normalize each label
    labels = [normalize_label(l) for l in str(labels_str).split(',')]
    
    # Check if any normalized label matches our security labels
    for label in labels:
        if label in security_labels_normalized:
            return True
    
    return False


def count_security_bugs_by_team(jira_issues_df, resources_df, team_name, 
                                 current_date, fiscal_start_month=4):
    """
    Count bugs with security-related labels for a specific team.
    
    Args:
        jira_issues_df (DataFrame): JIRA issues data
        resources_df (DataFrame): Resources data with SAPID, Name, JIRA Name, Team, Scrum
        team_name (str): The team name to filter by
        current_date (date or str): Current date for period calculations
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
    
    Returns:
        dict: Dictionary with 'Weekly', 'Monthly', 'Quarterly', 'Annual' counts
    """
    # Security-related labels (including variations and typos)
    security_labels = [
        'Security',
        'SecurityIncident',
        'Security_Vulnerabilities',
        'application-security-vulnerability-scan',
        'application-security-vulnerability-scan.',  # with trailing dot
        'application_security',
        'authentication',
        'bug-ui-vulnerability',
        'research-security-dev',
        'research-security-test',
        'security',  # lowercase variant
        'vulnerability'
    ]
    
    # Normalize all security labels for comparison
    security_labels_normalized = set(normalize_label(l) for l in security_labels)
    
    # Convert current_date to datetime if it's a string
    if isinstance(current_date, str):
        current_dt_obj = datetime.strptime(current_date, '%Y%m%d').date()
    else:
        current_dt_obj = current_date
    
    # Filter for Bug issues only
    bugs_df = jira_issues_df[jira_issues_df['Issue Type'] == 'Bug'].copy()
    
    # Parse Created date before merging to preserve the column
    bugs_df['Created'] = pd.to_datetime(bugs_df['Created'], errors='coerce')
    bugs_df = bugs_df[bugs_df['Created'].notna()]
    bugs_df['Created Date'] = bugs_df['Created'].dt.date
    
    # Merge with resources to get Team information
    bugs_df = bugs_df.merge(
        resources_df[['JIRA Name', 'SAPID', 'Team', 'Scrum']],
        left_on='Assignee',
        right_on='JIRA Name',
        how='inner'
    )
    
    # Filter by team
    bugs_df = bugs_df[bugs_df['Team'] == team_name]
    
    # Filter by security labels
    bugs_df = bugs_df[bugs_df['Labels'].notna()].copy()
    bugs_df['has_security_label'] = bugs_df['Labels'].apply(
        lambda x: contains_security_label(x, security_labels_normalized)
    )
    bugs_df = bugs_df[bugs_df['has_security_label']].copy()
    
    # If no security bugs found for this team, return zeros
    if len(bugs_df) == 0:
        return {
            'Weekly': 0,
            'Monthly': 0,
            'Quarterly': 0,
            'Annual': 0
        }
    
    # Calculate period boundaries
    current_year = current_dt_obj.year
    current_month = current_dt_obj.month
    
    # Week calculation (ISO week)
    week_start = current_dt_obj - timedelta(days=current_dt_obj.weekday())
    week_end = week_start + timedelta(days=6)
    
    # Month boundaries
    month_start = datetime(current_year, current_month, 1).date()
    if current_month == 12:
        month_end = datetime(current_year + 1, 1, 1).date() - timedelta(days=1)
    else:
        month_end = datetime(current_year, current_month + 1, 1).date() - timedelta(days=1)
    
    # Quarter calculation (fiscal quarter)
    def get_fiscal_quarter_bounds(dt, fiscal_start_month):
        year = dt.year
        month = dt.month
        
        # Adjust year if we're before fiscal year start
        if month < fiscal_start_month:
            fiscal_year = year - 1
        else:
            fiscal_year = year
        
        # Calculate which quarter we're in (0-3)
        months_since_fy_start = (month - fiscal_start_month) % 12
        quarter_num = months_since_fy_start // 3
        
        # Quarter start month
        quarter_start_month = fiscal_start_month + (quarter_num * 3)
        if quarter_start_month > 12:
            quarter_start_month -= 12
            quarter_start_year = fiscal_year + 1
        else:
            quarter_start_year = fiscal_year
        
        quarter_start = datetime(quarter_start_year, quarter_start_month, 1).date()
        
        # Quarter end (3 months later, last day)
        quarter_end_month = quarter_start_month + 3
        if quarter_end_month > 12:
            quarter_end_month -= 12
            quarter_end_year = quarter_start_year + 1
        else:
            quarter_end_year = quarter_start_year
        
        quarter_end = datetime(quarter_end_year, quarter_end_month, 1).date() - timedelta(days=1)
        
        return quarter_start, quarter_end
    
    quarter_start, quarter_end = get_fiscal_quarter_bounds(current_dt_obj, fiscal_start_month)
    
    # Fiscal year calculation
    if current_month >= fiscal_start_month:
        fy_start_year = current_year
    else:
        fy_start_year = current_year - 1
    
    fy_start = datetime(fy_start_year, fiscal_start_month, 1).date()
    fy_end = datetime(fy_start_year + 1, fiscal_start_month, 1).date() - timedelta(days=1)
    
    # Count bugs for each period
    weekly_count = len(bugs_df[
        (bugs_df['Created Date'] >= week_start) &
        (bugs_df['Created Date'] <= week_end)
    ])
    
    monthly_count = len(bugs_df[
        (bugs_df['Created Date'] >= month_start) &
        (bugs_df['Created Date'] <= month_end)
    ])
    
    quarterly_count = len(bugs_df[
        (bugs_df['Created Date'] >= quarter_start) &
        (bugs_df['Created Date'] <= quarter_end)
    ])
    
    annual_count = len(bugs_df[
        (bugs_df['Created Date'] >= fy_start) &
        (bugs_df['Created Date'] <= fy_end)
    ])
    
    return {
        'Weekly': weekly_count,
        'Monthly': monthly_count,
        'Quarterly': quarterly_count,
        'Annual': annual_count
    }


def k38(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K38: Count security bugs at team level and generate k38-data.csv output.
    
    Args:
        resources_file (str): Path to Resources.csv file
        jira_issues_file (str): Path to JIRAIssues.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k38-data.csv')
    
    if current_date is None:
        current_date = date.today()
    
    try:
        # Load Resources
        resources_df = pd.read_csv(resources_file)
        print(f"  ✓ Loaded {len(resources_df)} resources")
        
        # Load JIRA Issues
        jira_df = pd.read_csv(jira_issues_file)
        print(f"  ✓ Loaded {len(jira_df)} JIRA issues")
        
        # Get date strings for output
        current_date_str, week_str, month_str, quarter_str, year_str = get_date_strings(
            current_date, fiscal_start_month
        )
        
        # Get unique teams
        teams = resources_df['Team'].dropna().unique()
        print(f"  ✓ Processing {len(teams)} teams")
        
        # Calculate team-level counts
        team_counts = {}
        for team in teams:
            counts = count_security_bugs_by_team(
                jira_df, resources_df, team, current_date, fiscal_start_month
            )
            team_counts[team] = counts
        
        # Create output rows - each team member gets their team's values
        output_rows = []
        for _, resource in resources_df.iterrows():
            team = resource.get('Team')
            if pd.isna(team) or team not in team_counts:
                continue
            
            counts = team_counts[team]
            
            output_rows.append({
                'CurrentDate': current_date_str,
                'Week': week_str,
                'Month': month_str,
                'Quarter': quarter_str,
                'Year': year_str,
                'SAPID': resource['SAPID'],
                'Name': resource['Name'],
                'Weekly': counts['Weekly'],
                'Monthly': counts['Monthly'],
                'Quarterly': counts['Quarterly'],
                'Annual': counts['Annual']
            })
        
        # Create output DataFrame
        output_df = pd.DataFrame(output_rows)
        
        # Write to CSV
        output_df.to_csv(output_file, index=False)
        print(f"  ✓ Created {output_file} with {len(output_df)} records")
        
        # Print summary
        total_teams_with_bugs = sum(1 for counts in team_counts.values() if counts['Annual'] > 0)
        print(f"  ✓ {total_teams_with_bugs} teams with security bugs")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Error in K38: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    # Test the function
    import sys
    from pathlib import Path
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    resources_file = project_root / 'config' / 'Resources.csv'
    jira_issues_file = project_root / 'output' / 'JIRAIssues.csv'
    output_dir = project_root / 'output'
    
    success = k38(
        resources_file=str(resources_file),
        jira_issues_file=str(jira_issues_file),
        output_dir=str(output_dir)
    )
    
    sys.exit(0 if success else 1)
