"""KPP K253 - Equivalent KPI of K200."""

from datetime import datetime

from kpp_k200 import k200


def get_description():
    """Return KPI description."""
    return "Delayed Story Points at Scrum Team Level - Equivalent of K200"


def k253(resources_file, current_date=None, fiscal_start_month=4, output_folder='../output', jira_issues_file='../output/JIRAIssues.csv'):
    """Run K253 as an equivalent alias of K200."""
    print("\nNote: K253 is equivalent to K200 (shares computation and data)")
    return k200(
        resources_file=resources_file,
        current_date=current_date,
        fiscal_start_month=fiscal_start_month,
        output_folder=output_folder,
        jira_issues_file=jira_issues_file
    )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Compute KPP K253 - Equivalent of K200')
    parser.add_argument('--resources', default='../config/Resources.csv', help='Path to Resources.csv')
    parser.add_argument('--jira-issues', default='../output/JIRAIssues.csv', help='Path to JIRA issues CSV')
    parser.add_argument('--date', default=datetime.now().strftime('%Y%m%d'), help='Current date (YYYYMMDD)')
    parser.add_argument('--fiscal-month', type=int, default=4, help='Fiscal year start month (1-12)')
    parser.add_argument('--output', default='../output', help='Output folder path')
    
    args = parser.parse_args()
    
    success = k253(
        resources_file=args.resources,
        current_date=args.date,
        fiscal_start_month=args.fiscal_month,
        output_folder=args.output,
        jira_issues_file=args.jira_issues
    )
    
    exit(0 if success else 1)
