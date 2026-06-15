#!/usr/bin/env python3
"""
KPP K39 - Design Bugs Count
Counts bugs with label 'bug-ui-functional' at Team level.
"""

import pandas as pd
import os
from datetime import datetime, date
from kpi_helpers import count_bugs_by_label, get_date_strings


def get_description():
    """Return KPI description."""
    return "Design Bugs Count - Counts bugs with label 'bug-ui-functional' at Team level"


def get_date_strings(current_date, fiscal_start_month=4):
    """
    Generate formatted date strings for output.
    
    Args:
        current_date (date): The current date
        fiscal_start_month (int): Starting month for fiscal year
    
    Returns:
        tuple: (current_date_str, week_str, month_str, quarter_str, year_str)
    """
    # Current date as YYYYMMDD
    current_date_str = current_date.strftime('%Y%m%d')
    
    # Week as YYYYWW (ISO week)
    year, week, _ = current_date.isocalendar()
    week_str = f"{year}{week:02d}"
    
    # Month as MmmYYYY
    month_str = current_date.strftime('%b%Y')
    
    # Quarter as XXXYYY (e.g., JFM2026 for Jan-Feb-Mar 2026)
    month = current_date.month
    year = current_date.year
    
    # Calculate fiscal quarter
    if month >= fiscal_start_month:
        fiscal_year = year
    else:
        fiscal_year = year - 1
    
    months_since_fy_start = (month - fiscal_start_month) % 12
    quarter_num = months_since_fy_start // 3
    
    quarter_start_month = fiscal_start_month + (quarter_num * 3)
    if quarter_start_month > 12:
        quarter_start_month -= 12
        quarter_year = fiscal_year + 1
    else:
        quarter_year = fiscal_year
    
    # Generate quarter string (e.g., JFM, AMJ, JAS, OND)
    month_abbrevs = ['', 'J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']
    q_abbrev = ''.join([
        month_abbrevs[quarter_start_month],
        month_abbrevs[quarter_start_month + 1] if quarter_start_month + 1 <= 12 else month_abbrevs[1],
        month_abbrevs[quarter_start_month + 2] if quarter_start_month + 2 <= 12 else month_abbrevs[(quarter_start_month + 2) - 12]
    ])
    quarter_str = f"{q_abbrev}{quarter_year}"
    
    # Fiscal year as FYYYY
    year_str = f"F{fiscal_year + 1}"
    
    return current_date_str, week_str, month_str, quarter_str, year_str


def k39(resources_file, jira_issues_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    KPP K39 - Design Bugs Count
    Counts bugs with label 'bug-ui-functional' at Team level.
    
    Args:
        resources_file (str): Path to Resources.csv file
        jira_issues_file (str): Path to JIRAIssues.csv file
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    print("\n" + "="*60)
    print("KPP K39 - Design Bugs Count")
    print(f"Date: {datetime.now().strftime('%Y%m%d')}")
    print("="*60)
    
    try:
        # Use current date if not provided
        if current_date is None:
            current_date = date.today()
        elif isinstance(current_date, str):
            current_date = datetime.strptime(current_date, '%Y%m%d').date()
        
        # Load resources data
        print("Loading resources data...")
        resources = pd.read_csv(resources_file)
        print(f"  ✓ Loaded {len(resources)} resources")
        
        # Load JIRA issues data
        print("Loading JIRA issues data...")
        jira_issues = pd.read_csv(jira_issues_file)
        print(f"  ✓ Loaded {len(jira_issues)} JIRA issues")
        
        # Get unique teams
        teams = resources['Team'].dropna().unique()
        print(f"Calculating design bugs for {len(teams)} teams...")
        
        # Calculate bug counts for each team
        team_bug_counts = {}
        label = 'bug-ui-functional'
        
        for team in teams:
            counts = count_bugs_by_label(
                jira_issues_df=jira_issues,
                resources_df=resources,
                group_by='team',
                group_value=team,
                label=label,
                current_date=current_date,
                fiscal_start_month=fiscal_start_month
            )
            team_bug_counts[team] = counts
        
        print(f"  ✓ Calculated bug counts for {len(team_bug_counts)} teams")
        
        # Generate date strings
        current_date_str, week_str, month_str, quarter_str, year_str = get_date_strings(
            current_date, fiscal_start_month
        )
        
        # Create output for all employees
        print("Creating output for all employees...")
        output_rows = []
        
        for _, employee in resources.iterrows():
            sapid = employee['SAPID']
            name = employee['Name']
            team = employee.get('Team', None)
            
            # Get team's bug counts (or 0 if no team)
            if pd.notna(team) and team in team_bug_counts:
                counts = team_bug_counts[team]
            else:
                counts = {'Weekly': 0, 'Monthly': 0, 'Quarterly': 0, 'Annual': 0}
            
            output_rows.append({
                'CurrentDate': current_date_str,
                'Week': week_str,
                'Month': month_str,
                'Quarter': quarter_str,
                'Year': year_str,
                'SAPID': sapid,
                'Name': name,
                'Weekly': counts['Weekly'],
                'Monthly': counts['Monthly'],
                'Quarterly': counts['Quarterly'],
                'Annual': counts['Annual']
            })
        
        # Create DataFrame and save to CSV
        output_df = pd.DataFrame(output_rows)
        output_file = os.path.join(output_dir, 'k39-data.csv')
        output_df.to_csv(output_file, index=False)
        
        print(f"  ✓ Created design bug data for {len(output_df)} employees")
        print(f"  ✓ Updated {output_file} with {len(output_df)} records")
        print("="*60)
        
        return True
        
    except Exception as e:
        print(f"Error in K39: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    # For testing
    import sys
    from pathlib import Path
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    resources_file = project_root / 'config' / 'Resources.csv'
    jira_issues_file = project_root / 'output' / 'JIRAIssues.csv'
    output_dir = project_root / 'output'
    
    success = k39(
        resources_file=str(resources_file),
        jira_issues_file=str(jira_issues_file),
        output_dir=str(output_dir)
    )
    
    sys.exit(0 if success else 1)
