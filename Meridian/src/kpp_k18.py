#!/usr/bin/env python3
"""
KPP K18 - Test Documentation (Test Plans, Test Cases, Test Strategy)
Counts unique test documentation files developed/modified per individual using github_commit_files data.
"""

import pandas as pd
import os
from datetime import date
from kpi_helpers import get_week_number, get_month_string, get_quarter_string, get_fiscal_year


def get_description():
    """Return KPI description."""
    return "Test Documentation - Counts unique test documentation files (test plans, test cases, test strategy) developed/modified per individual"


def is_test_documentation_file(filepath):
    """
    Determine if a file is test documentation based on file path and name patterns.
    
    Args:
        filepath (str): File path to check
        
    Returns:
        str: 'high', 'medium', 'low' confidence, or None if not test documentation
    """
    if not filepath or pd.isna(filepath):
        return None
    
    filepath_lower = filepath.lower()
    filename = os.path.basename(filepath_lower)
    
    # High confidence patterns - specific test documentation files
    high_confidence_patterns = [
        'test_plan', 'testplan', 'test-plan',
        'test_case', 'testcase', 'test-case',
        'test_strategy', 'teststrategy', 'test-strategy',
        'qa_plan', 'qaplan', 'qa-plan',
        'test_scenario', 'testscenario', 'test-scenario',
        'test_suite', 'testsuite', 'test-suite',
        'testing_plan', 'testingplan', 'testing-plan',
        'test_specification', 'testspecification',
        'test_design', 'testdesign',
        'acceptance_criteria', 'acceptancecriteria',
    ]
    
    # Medium confidence patterns - test-related documentation in specific folders
    medium_confidence_folders = [
        'test/docs', 'tests/docs', 'test/documentation', 'tests/documentation',
        'qa/docs', 'qa/documentation', 'quality/docs',
        'testing/docs', 'testing/documentation',
        'test_docs', 'test-docs', 'testdocs',
    ]
    
    # Medium confidence file patterns
    medium_confidence_patterns = [
        'testing_guide', 'test_guide',
        'qa_document', 'qa_doc',
        'test_checklist', 'testing_checklist',
        'test_report_template', 'test_template',
    ]
    
    # File extensions that are likely documentation
    doc_extensions = ['.md', '.doc', '.docx', '.pdf', '.txt', '.rst', '.adoc', '.confluence']
    
    # Check if file has documentation extension
    has_doc_extension = any(filepath_lower.endswith(ext) for ext in doc_extensions)
    
    # High confidence: specific test documentation file names with doc extensions
    if has_doc_extension:
        for pattern in high_confidence_patterns:
            if pattern in filename:
                return 'high'
    
    # Medium confidence: test documentation in specific folders
    for folder_pattern in medium_confidence_folders:
        if folder_pattern in filepath_lower and has_doc_extension:
            return 'medium'
    
    # Medium confidence: medium pattern files with doc extensions
    if has_doc_extension:
        for pattern in medium_confidence_patterns:
            if pattern in filename:
                return 'medium'
    
    # Low confidence: any test-related docs (but exclude actual test code files)
    test_keywords = ['test', 'qa', 'quality']
    doc_keywords = ['doc', 'plan', 'strategy', 'guide', 'specification']
    
    if has_doc_extension:
        has_test_keyword = any(kw in filepath_lower for kw in test_keywords)
        has_doc_keyword = any(kw in filepath_lower for kw in doc_keywords)
        
        if has_test_keyword and has_doc_keyword:
            return 'low'
    
    return None


def k18(resources_file, github_commits_file, output_dir, fiscal_start_month=4, current_date=None):
    """
    K18: Test Documentation at Individual Level.
    
    Args:
        resources_file (str): Path to Resources.csv file
        github_commits_file (str): Path to github_commits.csv file (not used directly)
        output_dir (str): Directory for output files
        fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        current_date (date): The current date for reporting (default: today)
    
    Returns:
        bool: True if successful, False otherwise
    """
    output_file = os.path.join(output_dir, 'k18-data.csv')
    commit_files_file = os.path.join(output_dir, 'github_commit_files.csv')
    
    if current_date is None:
        current_date = date.today()
    
    current_date_str = current_date.strftime('%Y%m%d')
    
    print(f"\n{'='*60}")
    print(f"KPP K18 - Test Documentation")
    print(f"Date: {current_date_str}")
    print(f"{'='*60}")
    
    # Load resources
    print("Loading resources data...")
    try:
        resources_df = pd.read_csv(resources_file)
        resources = resources_df[['SAPID', 'Name', 'GitHUB Name']].copy()
        resources['SAPID'] = resources['SAPID'].fillna(0).astype(int).astype(str)
        resources = resources[resources['GitHUB Name'].notna()]
        resources = resources[resources['GitHUB Name'] != '-NA-']
        print(f"  ✓ Loaded {len(resources)} resources")
    except Exception as e:
        print(f"  ✗ Error loading resources file: {e}")
        return False
    
    if resources.empty:
        print("  ✗ No resources data loaded")
        return False
    
    # Load commit files data
    print("Loading GitHub commit files data...")
    if not os.path.exists(commit_files_file):
        print(f"  ✗ Error: {commit_files_file} not found")
        print(f"      Please run 'python github_fetch.py fetch' to generate file details")
        return False
    
    try:
        files_df = pd.read_csv(commit_files_file)
        files_df['date'] = pd.to_datetime(files_df['date'], errors='coerce')
        files_df = files_df[files_df['date'].notna()]
        print(f"  ✓ Loaded {len(files_df)} file changes")
    except Exception as e:
        print(f"  ✗ Error loading commit files: {e}")
        return False
    
    if files_df.empty:
        print("  ⚠ Warning: No commit file data found")
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
    
    # Identify test documentation files
    print("Identifying test documentation files...")
    files_df['test_doc_confidence'] = files_df['filepath'].apply(is_test_documentation_file)
    
    # Filter for test documentation files (high and medium confidence)
    test_doc_files = files_df[
        files_df['test_doc_confidence'].isin(['high', 'medium'])
    ].copy()
    
    if test_doc_files.empty:
        print("  ⚠ Warning: No test documentation files found")
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
    
    print(f"  ✓ Found {len(test_doc_files)} test documentation file changes")
    confidence_counts = test_doc_files['test_doc_confidence'].value_counts()
    for conf, count in confidence_counts.items():
        print(f"     - {conf} confidence: {count}")
    
    # Merge with resources to get SAPID and Name
    print("Matching test documentation files with resources...")
    test_doc_merged = test_doc_files.merge(
        resources, 
        left_on='author', 
        right_on='GitHUB Name', 
        how='inner'
    )
    
    if test_doc_merged.empty:
        print("  ⚠ Warning: No matching records found between commit files and Resources")
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
    
    print(f"  ✓ Matched {len(test_doc_merged)} test documentation changes to resources")
    
    # Add time period columns
    test_doc_merged['Week'] = test_doc_merged['date'].apply(get_week_number)
    test_doc_merged['Month'] = test_doc_merged['date'].apply(get_month_string)
    test_doc_merged['Quarter'] = test_doc_merged['date'].apply(get_quarter_string)
    test_doc_merged['FiscalYear'] = test_doc_merged['date'].apply(lambda x: get_fiscal_year(x, fiscal_start_month))
    
    # Calculate current period values
    current_dt = pd.Timestamp(current_date)
    current_week = get_week_number(current_dt)
    current_month = get_month_string(current_dt)
    current_quarter = get_quarter_string(current_dt)
    current_fiscal_year = get_fiscal_year(current_dt, fiscal_start_month)
    
    print("Counting unique test documentation files per individual...")
    
    # Count unique test documentation files (filepath) per individual for each period
    result = []
    
    for _, emp in resources.iterrows():
        sapid = emp['SAPID']
        name = emp['Name']
        github_name = emp['GitHUB Name']
        
        # Filter test docs for this individual
        emp_docs = test_doc_merged[test_doc_merged['SAPID'] == sapid]
        
        # Count unique test documentation files for each period
        weekly_docs = emp_docs[emp_docs['Week'] == current_week]['filepath'].nunique()
        monthly_docs = emp_docs[emp_docs['Month'] == current_month]['filepath'].nunique()
        quarterly_docs = emp_docs[emp_docs['Quarter'] == current_quarter]['filepath'].nunique()
        annual_docs = emp_docs[emp_docs['FiscalYear'] == current_fiscal_year]['filepath'].nunique()
        
        result.append({
            'CurrentDate': current_date_str,
            'Week': current_week,
            'Month': current_month,
            'Quarter': current_quarter,
            'Year': current_fiscal_year,
            'SAPID': sapid,
            'Name': name,
            'Weekly': weekly_docs,
            'Monthly': monthly_docs,
            'Quarterly': quarterly_docs,
            'Annual': annual_docs
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
    print(f"  ✓ {len(non_zero)} individuals with test documentation work")
    if len(non_zero) > 0:
        total_docs = new_df['Annual'].sum()
        print(f"  ✓ Total unique test documents created/modified: {total_docs}")
        # Show top contributors
        top_contributors = new_df.nlargest(5, 'Annual')[['Name', 'Annual']]
        if len(top_contributors) > 0:
            print(f"  ✓ Top contributors:")
            for _, row in top_contributors.iterrows():
                if row['Annual'] > 0:
                    print(f"     - {row['Name']}: {int(row['Annual'])} documents")
    
    print(f"{'='*60}\n")
    return True


if __name__ == '__main__':
    # For testing
    import sys
    from pathlib import Path
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    resources_file = project_root / 'config' / 'Resources.csv'
    github_commits_file = project_root / 'output' / 'github_commits.csv'
    output_dir = project_root / 'output'
    
    success = k18(
        resources_file=str(resources_file),
        github_commits_file=str(github_commits_file),
        output_dir=str(output_dir)
    )
    
    sys.exit(0 if success else 1)
