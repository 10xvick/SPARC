#!/usr/bin/env python3
"""
KPP K59 - Individual UI Design Bugs Count
Counts bugs attributable to UI design assigned to individual.
"""

import pandas as pd
import os
from datetime import datetime, date
from kpi_helpers import count_bugs_by_label, get_date_strings


def get_description():
    """Return KPI description."""
    return "Individual UI Design Bugs - Counts bugs attributable to UI design assigned to individual"


def compute_k59(current_date=None, resources_file=None, jira_issues_file=None, output_dir=None, fiscal_start_month=4):
    """
    Compute K59 - Individual UI Design bugs count per person.
    
    This counts bugs with label 'bug-ui-functional' that are assigned to each individual.
    Uses the 'Assignee' field to attribute bugs to individuals.
    
    Args:
        current_date: Optional date object (default: today)
        resources_file: Path to Resources.csv (default: auto-detected)
        jira_issues_file: Path to JIRAIssues.csv (default: auto-detected)
        output_dir: Path to output directory (default: auto-detected)
        fiscal_start_month: Fiscal year start month (default: 4 for April)
        
    Returns:
        bool: True if successful, False otherwise
    """
    if current_date is None:
        current_date = date.today()
    
    # Auto-detect file paths if not provided
    if jira_issues_file is None:
        jira_file = os.path.join(os.path.dirname(__file__), '..', 'output', 'JIRAIssues.csv')
    else:
        jira_file = jira_issues_file
        
    if resources_file is None:
        resources_file = os.path.join(os.path.dirname(__file__), '..', 'config', 'Resources.csv')
        
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
    
    if not os.path.exists(jira_file):
        print(f"Warning: {jira_file} not found")
        return False
    
    try:
        jira_df = pd.read_csv(jira_file)
    except Exception as e:
        print(f"Error reading JIRA file: {e}")
        return False
    
    # Filter for bugs with 'bug-ui-functional' label
    if 'Labels' not in jira_df.columns:
        print("Warning: 'Labels' column not found in JIRA data")
        return False
    
    # Filter bugs with the specific label
    ui_bugs = jira_df[jira_df['Labels'].fillna('').str.contains('bug-ui-functional', case=False, na=False)].copy()
    
    if ui_bugs.empty:
        print("No bugs found with 'bug-ui-functional' label")
        # Still create an output file with all zeros
    
    # Count bugs by assignee
    if 'Assignee' not in ui_bugs.columns:
        print("Warning: 'Assignee' column not found in JIRA data")
        return False
    
    # Group by assignee and count
    if not ui_bugs.empty:
        assignee_counts = ui_bugs.groupby('Assignee').size().reset_index(name='bug_count')
    else:
        assignee_counts = pd.DataFrame(columns=['Assignee', 'bug_count'])
    
    # Load resources to get all employees
    if not os.path.exists(resources_file):
        print(f"Warning: {resources_file} not found")
        return False
    
    try:
        resources_df = pd.read_csv(resources_file)
    except Exception as e:
        print(f"Error reading resources file: {e}")
        return False
    
    # Create result dataframe with all employees — include SAPID for standard schema
    result_df = resources_df[['SAPID', 'Name']].copy()
    result_df['SAPID'] = result_df['SAPID'].apply(
        lambda v: str(int(float(str(v).strip()))) if str(v).strip() not in ('', 'nan') else ''
    )
    
    # Merge with bug counts
    result_df = result_df.merge(assignee_counts, left_on='Name', right_on='Assignee', how='left')
    result_df['bug_count'] = result_df['bug_count'].fillna(0).astype(int)
    
    # All time periods get the same count (snapshot data)
    result_df['Weekly'] = result_df['bug_count']
    result_df['Monthly'] = result_df['bug_count']
    result_df['Quarterly'] = result_df['bug_count']
    result_df['Annual'] = result_df['bug_count']
    
    # Add date strings
    current_date_str, week_str, month_str, quarter_str, year_str = get_date_strings(current_date)
    
    result_df['Date'] = current_date_str
    result_df['Week'] = week_str
    result_df['Month'] = month_str
    result_df['Quarter'] = quarter_str
    result_df['Year'] = year_str

    # Standard column order: CurrentDate,Week,Month,Quarter,Year,SAPID,Name,Weekly,Monthly,Quarterly,Annual
    final_df = result_df[['Date', 'Week', 'Month', 'Quarter', 'Year', 'SAPID', 'Name', 'Weekly', 'Monthly', 'Quarterly', 'Annual']]
    final_df = final_df.rename(columns={'Date': 'CurrentDate'})
    
    # Save to output file
    try:
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, 'k59-data.csv')
        final_df.to_csv(output_file, index=False)
        print(f"K59 data saved to {output_file}")
        print(f"Total records: {len(final_df)}")
        
        # Show sample statistics
        non_zero = final_df[final_df['Annual'] > 0]
        if not non_zero.empty:
            print(f"Employees with UI design bugs: {len(non_zero)}")
            print(f"Average bugs per person (non-zero): {non_zero['Annual'].mean():.1f}")
            print(f"Max bugs: {final_df['Annual'].max()}")
            top5 = non_zero.nlargest(5, 'Annual')[['Name', 'Annual']]
            top5_str = ', '.join([f"{row['Name']}({row['Annual']})" for _, row in top5.iterrows()])
            print(f"Top 5: {top5_str}")
        
        return True
    except Exception as e:
        print(f"Error saving K59 data: {e}")
        return False


def run():
    """Main execution function."""
    print("Computing K59 - Individual UI Design Bugs...")
    
    success = compute_k59()
    
    if not success:
        print("Failed to compute K59")
        return
    
    print("K59 computation completed successfully")


if __name__ == '__main__':
    run()
