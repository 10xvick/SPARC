"""
KPI Helper Functions
Reusable utility functions for KPI calculations.
"""

import pandas as pd
from datetime import datetime, timedelta


# Date formatting helper functions
def get_week_number(dt):
    """Get ISO week number as YYYYWw format."""
    year, week, _ = dt.isocalendar()
    return f"{year}{week:02d}"


def get_month_string(dt):
    """Get month as MmmYYYY format (e.g., Mar2026)."""
    return dt.strftime('%b%Y')


def get_quarter_string(dt):
    """Get quarter as XXXYYY format (e.g., JFM2026 for Jan-Feb-Mar 2026)."""
    month = dt.month
    year = dt.year
    if month in [1, 2, 3]:
        quarter = 'JFM'
    elif month in [4, 5, 6]:
        quarter = 'AMJ'
    elif month in [7, 8, 9]:
        quarter = 'JAS'
    else:
        quarter = 'OND'
    return f"{quarter}{year}"


def get_fiscal_year(dt, fiscal_start_month=4):
    """Get fiscal year as FYYYY format."""
    year = dt.year
    month = dt.month
    if month >= fiscal_start_month:
        fiscal_year = year
    else:
        fiscal_year = year - 1
    return f"FY{fiscal_year}"


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
    week_str = get_week_number(current_date)
    
    # Month as MmmYYYY
    month_str = get_month_string(current_date)
    
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


def count_bugs_by_label(jira_issues_df, resources_df, group_by, group_value, label, 
                        current_date, fiscal_start_month=4):
    """
    Count bugs that have a specific label in their Labels column.
    
    Args:
        jira_issues_df (DataFrame): JIRA issues data
        resources_df (DataFrame): Resources data with SAPID, Name, JIRA Name, Team, Scrum
        group_by (str): Grouping level - 'individual', 'scrum', or 'team'
        group_value (str): The specific value to filter by (SAPID for individual, Scrum name, or Team name)
        label (str): The label to search for in the Labels column
        current_date (date or str): Current date for period calculations
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
    
    Returns:
        dict: Dictionary with 'Weekly', 'Monthly', 'Quarterly', 'Annual' counts
    """
    # Convert current_date to datetime if it's a string
    if isinstance(current_date, str):
        current_dt_obj = datetime.strptime(current_date, '%Y%m%d').date()
    else:
        current_dt_obj = current_date
    
    # Filter for Bug issues only
    bugs_df = jira_issues_df[jira_issues_df['Issue Type'] == 'Bug'].copy()
    
    # Merge with resources to get Team/Scrum information
    bugs_df = bugs_df.merge(
        resources_df[['JIRA Name', 'SAPID', 'Team', 'Scrum']],
        left_on='Assignee',
        right_on='JIRA Name',
        how='inner'
    )
    
    # Filter by group
    if group_by == 'individual':
        bugs_df = bugs_df[bugs_df['SAPID'].astype(str) == str(group_value)]
    elif group_by == 'scrum':
        bugs_df = bugs_df[bugs_df['Scrum'] == group_value]
    elif group_by == 'team':
        bugs_df = bugs_df[bugs_df['Team'] == group_value]
    else:
        raise ValueError(f"Invalid group_by value: {group_by}. Must be 'individual', 'scrum', or 'team'")
    
    # Filter by label - check if the label exists in the Labels column
    # Labels column may contain multiple comma-separated labels
    bugs_df = bugs_df[bugs_df['Labels'].notna()].copy()
    bugs_df = bugs_df[bugs_df['Labels'].str.contains(label, case=False, na=False)]
    
    # Parse Created date
    bugs_df['Created'] = pd.to_datetime(bugs_df['Created'], errors='coerce')
    bugs_df = bugs_df[bugs_df['Created'].notna()]
    bugs_df['Created Date'] = bugs_df['Created'].dt.date
    
    # Calculate period boundaries
    current_year = current_dt_obj.year
    current_month = current_dt_obj.month
    
    # Week calculation (ISO week)
    current_week_num = current_dt_obj.isocalendar()[1]
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
