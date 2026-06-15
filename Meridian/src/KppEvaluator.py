#!/usr/bin/env python3
"""
KppEvaluator - KPI Evaluator Orchestrator
Main entry point for running multiple KPI evaluation functions.
"""

import argparse
import sys
import os
import csv
import tempfile
from datetime import date, datetime
from pathlib import Path
from collections import defaultdict

# Import KPI functions
from kpp_k1 import k1
from kpp_k2 import k2
from kpp_k3 import k3
from kpp_k4 import k4
from kpp_k49 import k49
from kpp_k56 import k56
from kpp_k57 import k57
from kpp_k12 import k12
from kpp_k7 import k7
from kpp_k9 import k9
from kpp_k13 import k13
from kpp_k14 import k14
from kpp_k16 import k16
from kpp_k18 import k18
from kpp_k200 import k200
from kpp_k31 import k31
from kpp_k38 import k38
from kpp_k39 import k39
from kpp_k59 import compute_k59 as k59
from kpp_k64 import k64
from kpp_k68 import k68
from kpp_k77 import k77
from kpp_k94 import k94
from kpp_k138 import k138
from kpp_k204 import k204
from kpp_k205 import k205
from kpp_k208 import k208
from kpp_k222 import k222
from kpp_k206 import k206
from kpp_k227 import k227
from kpp_k259 import k259
from kpp_k268 import k268
from kpp_k299 import k299
from kpp_k300 import k300
from kpp_k301 import k301
from kpp_k302 import k302
from kpp_k303 import k303
from kpp_k304 import k304
from kpp_k305 import k305
from kpp_k308 import k308


def _resolve_project_root(project_root_arg=None):
    """Resolve TeamSight project root for config/output paths."""
    if project_root_arg:
        return Path(project_root_arg).expanduser().resolve()

    env_root = os.getenv('TEAMSIGHT_HOME')
    if env_root:
        return Path(env_root).expanduser().resolve()

    source_root = Path(__file__).resolve().parent.parent
    if (source_root / 'config').exists():
        return source_root

    cwd_root = Path.cwd()
    return cwd_root


class KppEvaluator:
    """Orchestrates evaluation of multiple KPIs."""
    
    def __init__(self, resources_file, jira_issues_file, github_commits_file, output_dir, fiscal_start_month=4):
        """
        Initialize the KppEvaluator.
        
        Args:
            resources_file (str): Path to Resources.csv file
            jira_issues_file (str): Path to JIRAIssues.csv file
            github_commits_file (str): Path to github_commits.csv file
            output_dir (str): Directory for output files
            fiscal_start_month (int): Starting month for fiscal year (default: 4 for April)
        """
        self.resources_file = resources_file
        self.jira_issues_file = jira_issues_file
        self.github_commits_file = github_commits_file
        self.output_dir = output_dir
        self.fiscal_start_month = fiscal_start_month
        self.active_resources_file = self._build_active_resources_snapshot(resources_file)
        
        # Equivalent KPI mapping - maps alias KPIs to their base implementation
        # Format: 'alias_kpi': 'base_kpi'
        # The alias will use the base's computation and data file,
        # but can have independent roles and targets in Roles.csv
        self.kpi_equivalents = {
            'k7': 'k3',   # K7 (Junior Software Engineer) uses K3's computation and data
            'k6': 'k1',   # K6 (Junior Software Engineer) uses K1's computation and data
            'k75': 'k1',  # K75 (Trainee) uses K1's computation and data
            'k88': 'k1',  # K88 (IoT Developer) uses K1's computation and data
            'k111': 'k1', # K111 (Senior Engineer - Research) uses K1's computation and data
            'k148': 'k1', # K148 (DSP Algorithm Engineer) uses K1's computation and data
            'k8': 'k4',   # K8 uses K4's computation and data
            'k136': 'k14', # K136 uses K14's computation and data
            'k20': 'k16', # K20 uses K16's computation and data
            'k22': 'k18', # K22 uses K18's computation and data
            'k24': 'k16', # K24 (QA Engineer) uses K16's computation and data
            'k60': 'k39', # K60 (UI Designer) uses K39's computation and data (product level)
            'k253': 'k200', # K253 uses K200's computation and data
            # New role KPIs (k269-k298) mapped to existing KPIs
            'k269': 'k3',   # Data Engineer - Feature Implementation → Developer
            'k270': 'k4',   # Data Engineer - Code Quality → Developer
            'k271': 'k31',  # Data Engineer - Query Performance → Database Administrator
            'k272': 'k3',   # Data Scientist - Feature Implementation → Developer
            'k273': 'k4',   # Data Scientist - Code Quality → Developer
            'k274': 'k105', # Data Scientist - Research Technologies → Research Architect (not yet implemented, will need base)
            'k278': 'k12',  # Lead Data Scientist - Code Review → Tech Lead
            'k279': 'k13',  # Lead Data Scientist - Project Delivery → Tech Lead
            'k280': 'k105', # Lead Data Scientist - Research Technologies → Research Architect (not yet implemented)
            'k281': 'k12',  # Lead Developer - Code Review → Tech Lead
            'k282': 'k13',  # Lead Developer - Project Delivery → Tech Lead
            'k284': 'k12',  # Lead Tester - Code Review → Tech Lead
            'k285': 'k16',  # Lead Tester - Bug Identification → Integration Tester
            'k286': 'k17',  # Lead Tester - Automation → Integration Tester (not yet implemented, will need base)
            'k287': 'k18',  # Lead Tester - Test Documentation → Integration Tester
            'k288': 'k12',  # Offshore Lead - Code Review → Tech Lead
            'k289': 'k13',  # Offshore Lead - Project Delivery → Tech Lead
            'k296': 'k4',   # Web Developer - Code Quality → Developer
            'k306': 'k305', # Architect - equivalent to unified security gating
            'k307': 'k305', # Program Manager - equivalent to unified security gating
            # Note: k275-k277 (Development Manager), k283 (Lead Developer Architecture),
            # k290 (Offshore Lead Team Coordination), k291-k293 (Splunk Architect),
            # k294-k295 (Support), k297-k298 (Web Developer UI/UX) are unique KPIs
            # and will need their own implementations or remain as placeholders
        }
        
        # Registry of available KPI functions
        self.kpi_functions = {
            'k2': k2,
            'k3': k3,
            'k4': k4,
            'k7': k3,   # K7 (Junior Software Engineer) - equivalent to K3
            'k9': k9,
            'k12': k12,
            'k13': k13,
            'k14': k14,
            'k16': k16,
            'k18': k18,
            'k200': k200,
            'k31': k31,
            'k38': k38,
            'k39': k39,
            'k49': k49,
            'k56': k56,
            'k59': k59,   # K59 - Individual UI Design Bugs (assigned to person)
            'k60': k39,   # K60 (UI Designer) uses K39's computation (product level)
            'k57': k57,
            'k64': k64,
            'k68': k68,
            'k77': k77,
            'k94': k94,
            'k138': k138,
            'k204': k204,
            'k205': k205,
            'k208': k208,  # K208 - Copilot LOC Team Average
            'k222': k222,
            'k206': k206,
            'k227': k227,
            'k259': k259,
            'k268': k268,  # K268 - Code Generation Ratio (k227/k1)
            'k299': k299,  # K299 - Total Test Code Lines Committed
            'k300': k300,  # K300 - Test Code to Total Code Ratio
            'k301': k301,  # K301 - DAST Gating Issues
            'k302': k302,  # K302 - SAST Gating Issues
            'k303': k303,  # K303 - SCA Gating Issues
            'k304': k304,  # K304 - MEND Gating Issues
            'k305': k305,  # K305 - Unified Security Gating Issues
            'k306': k305,  # K306 - Architect (equivalent to K305)
            'k307': k305,  # K307 - Program Manager (equivalent to K305)
            'k308': k308,  # K308 - Copilot Agent or Chat Usage
            # Equivalent KPIs (use base KPI's function)
            'k8': k4,   # K8 uses K4's computation
            'k136': k14, # K136 uses K14's computation
            'k253': k200, # K253 uses K200's computation
            'k20': k16, # K20 uses K16's computation
            'k22': k18, # K22 uses K18's computation
            'k24': k16, # K24 (QA Engineer) uses K16's computation
            # New role KPIs (k269-k298) - equivalent KPIs using base implementations
            'k269': k3,   # Data Engineer - Feature Implementation
            'k270': k4,   # Data Engineer - Code Quality
            'k271': k31,  # Data Engineer - Query Performance
            'k272': k3,   # Data Scientist - Feature Implementation
            'k273': k4,   # Data Scientist - Code Quality
            # k274: Research Technologies - needs k105 implementation
            'k278': k12,  # Lead Data Scientist - Code Review
            'k279': k13,  # Lead Data Scientist - Project Delivery
            # k280: Research Technologies - needs k105 implementation
            'k281': k12,  # Lead Developer - Code Review
            'k282': k13,  # Lead Developer - Project Delivery
            'k284': k12,  # Lead Tester - Code Review
            'k285': k16,  # Lead Tester - Bug Identification
            # k286: Automation - needs k17 implementation
            'k287': k18,  # Lead Tester - Test Documentation
            'k288': k12,  # Offshore Lead - Code Review
            'k289': k13,  # Offshore Lead - Project Delivery
            'k296': k4,   # Web Developer - Code Quality
            # Note: k275-k277, k283, k290-k295, k297-k298 are unique KPIs
            # Future KPIs will be added here
            'k1': k1,
            'k6': k1,    # K6 - Junior Software Engineer (equivalent to K1)
            'k75': k1,   # K75 - Trainee (equivalent to K1)
            'k88': k1,   # K88 - IoT Developer (equivalent to K1)
            'k111': k1,  # K111 - Senior Engineer - Research (equivalent to K1)
            'k148': k1,  # K148 - DSP Algorithm Engineer (equivalent to K1)
        }

    @staticmethod
    def _normalize_employment_status(raw_value):
        value = str(raw_value).strip().lower() if raw_value is not None else ''
        if value in {'inactive', 'false', 'no', 'n', '0', 'disabled'}:
            return 'Inactive'
        return 'Active'

    def _build_active_resources_snapshot(self, resources_file):
        """Create a temp active-only resources snapshot for KPI execution."""
        try:
            with open(resources_file, 'r', newline='', encoding='utf-8') as handle:
                reader = csv.DictReader(handle)
                fieldnames = reader.fieldnames or []
                rows = list(reader)

            if not rows:
                return resources_file

            status_column = 'Employment Status' if 'Employment Status' in fieldnames else None
            if status_column is None:
                return resources_file

            active_rows = [
                row for row in rows
                if self._normalize_employment_status(row.get(status_column, 'Active')) == 'Active'
            ]

            if len(active_rows) == len(rows):
                return resources_file

            temp_dir = tempfile.gettempdir()
            snapshot_path = os.path.join(temp_dir, 'teamsight_active_resources.csv')
            with open(snapshot_path, 'w', newline='', encoding='utf-8') as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(active_rows)

            print(
                f"Using active-only resources snapshot: {len(active_rows)}/{len(rows)} employees "
                f"from {resources_file}"
            )
            return snapshot_path
        except Exception as exc:
            print(f"Warning: failed to prepare active-only resources snapshot: {exc}")
            return resources_file
    
    def list_kpis(self):
        """List all available KPI functions (including equivalents)."""
        return sorted(self.kpi_functions.keys(), key=lambda x: int(x[1:]))
    
    def get_base_kpi(self, kpi_name):
        """
        Get the base KPI name for a given KPI.
        If the KPI is an equivalent, returns the base KPI name.
        Otherwise, returns the KPI name itself.
        
        Args:
            kpi_name (str): KPI name (e.g., 'k8')
            
        Returns:
            str: Base KPI name (e.g., 'k4' for 'k8')
        """
        return self.kpi_equivalents.get(kpi_name, kpi_name)
    
    def is_equivalent_kpi(self, kpi_name):
        """
        Check if a KPI is an equivalent (alias) of another KPI.
        
        Args:
            kpi_name (str): KPI name to check
            
        Returns:
            bool: True if KPI is an equivalent, False otherwise
        """
        return kpi_name in self.kpi_equivalents
    
    def describe_kpis(self):
        """Display descriptions of all available KPIs."""
        import textwrap
        import pandas as pd
        from pathlib import Path
        
        # Load Goal Types from Roles.csv
        roles_file = Path(self.resources_file).parent.parent / 'config' / 'Roles.csv'
        roles_df = pd.read_csv(roles_file)
        goal_type_map = {}
        if 'Goal Type' in roles_df.columns:
            for _, row in roles_df.iterrows():
                index_val = str(row['Index'])
                # Handle both formats: "k205" or "205"
                kpi_id = index_val if index_val.startswith('k') else f"k{index_val}"
                goal_type = row.get('Goal Type', '')
                if pd.notna(goal_type) and str(goal_type).strip():
                    goal_type_map[kpi_id] = str(goal_type).strip()
        
        # Collect KPI descriptions
        kpi_data = []
        for kpi in self.kpi_functions.keys():
            kpi_module = self.kpi_functions[kpi]
            # Get the description from the KPI module's get_description function
            if hasattr(kpi_module, '__module__'):
                module_name = kpi_module.__module__
                try:
                    # Import the module to access get_description
                    import importlib
                    mod = importlib.import_module(module_name)
                    if hasattr(mod, 'get_description'):
                        description = mod.get_description()
                    else:
                        description = 'No description available'
                except Exception:
                    description = 'No description available'
            else:
                description = 'No description available'
            
            # Get Goal Type for this KPI
            goal_type = goal_type_map.get(kpi, 'N/A')
            
            # Extract numeric part for sorting
            kpi_num = int(kpi[1:])  # Remove 'k' and convert to int
            kpi_data.append((kpi_num, kpi.upper(), goal_type, description))
        
        # Sort by KPI number
        kpi_data.sort(key=lambda x: x[0])
        
        # Calculate column widths
        max_kpi_width = max(len(item[1]) for item in kpi_data)
        max_goal_type_width = max(len(item[2]) for item in kpi_data) if kpi_data else 10
        desc_width = 100
        
        # Print header
        print("\n" + "="*150)
        print(f"{'KPI':<{max_kpi_width}}   {'Goal Type':<{max_goal_type_width}}   {'Description'}")
        print("="*150)
        
        # Print each KPI with wrapped description
        for _, kpi_name, goal_type, description in kpi_data:
            # Wrap the description at desc_width characters
            wrapped_lines = textwrap.wrap(description, width=desc_width)
            
            # Print first line with KPI name and Goal Type
            if wrapped_lines:
                print(f"{kpi_name:<{max_kpi_width}}   {goal_type:<{max_goal_type_width}}   {wrapped_lines[0]}")
                
                # Print subsequent wrapped lines with indentation
                for line in wrapped_lines[1:]:
                    print(f"{'':<{max_kpi_width}}   {'':<{max_goal_type_width}}   {line}")
            else:
                print(f"{kpi_name:<{max_kpi_width}}   {goal_type:<{max_goal_type_width}}   {description}")
        
        print("="*150 + "\n")

    
    def run_kpi(self, kpi_name, current_date=None):
        """
        Run a specific KPI function.
        For equivalent KPIs, runs the base KPI's function.
        
        Args:
            kpi_name (str): Name of the KPI to run (e.g., 'k3' or 'k8')
            current_date (date): The current date for reporting (default: today)
        
        Returns:
            bool: True if successful, False otherwise
        """
        if kpi_name not in self.kpi_functions:
            print(f"Error: KPI '{kpi_name}' not found")
            print(f"Available KPIs: {', '.join(self.list_kpis())}")
            return False
        
        # For equivalent KPIs, use the base KPI's function
        base_kpi = self.get_base_kpi(kpi_name)
        kpi_func = self.kpi_functions[kpi_name]
        
        # If this is an equivalent KPI, inform the user
        if self.is_equivalent_kpi(kpi_name):
            print(f"Note: {kpi_name.upper()} is equivalent to {base_kpi.upper()} (shares computation and data)")
            print(f"Running {base_kpi.upper()} computation...")
        
        try:
            # Determine which parameters this KPI needs based on BASE KPI
            if base_kpi == 'k222' or base_kpi == 'k268':
                # K222 and K268 need both JIRA and GitHub data
                success = kpi_func(
                    resources_file=self.active_resources_file,
                    jira_issues_file=self.jira_issues_file,
                    github_commits_file=self.github_commits_file,
                    output_dir=self.output_dir,
                    fiscal_start_month=self.fiscal_start_month,
                    current_date=current_date
                )
            elif base_kpi in ['k3', 'k7', 'k9', 'k16', 'k31', 'k38', 'k39', 'k64', 'k68', 'k77', 'k94', 'k138', 'k259', 'k308', 'k1', 'k208']:
                # K3, K7, K9, K16, K31, K38, K39, K64, K68, K77, K94, K138, K259, and K308 need JIRA data
                # (K308 uses similar interface with jira_issues_file param kept for compatibility)
                success = kpi_func(
                    resources_file=self.active_resources_file,
                    jira_issues_file=self.jira_issues_file,
                    output_dir=self.output_dir,
                    fiscal_start_month=self.fiscal_start_month,
                    current_date=current_date
                )
            elif base_kpi in ['k4', 'k12', 'k49', 'k56', 'k204', 'k206', 'k227', 'k18', 'k299', 'k300']:
                # K4, K8 (equivalent), K12, K18, K49, K56, K204, K206, K227, K299, and K300 need GitHub commits data
                success = kpi_func(
                    resources_file=self.active_resources_file,
                    github_commits_file=self.github_commits_file,
                    output_dir=self.output_dir,
                    fiscal_start_month=self.fiscal_start_month,
                    current_date=current_date
                )
            elif base_kpi == 'k301':
                # K301 reads from scan output HTML files and security_scan_config.json
                success = kpi_func(
                    resources_file=self.active_resources_file,
                    output_dir=self.output_dir,
                    fiscal_start_month=self.fiscal_start_month,
                    current_date=current_date
                )
            elif base_kpi == 'k302':
                # K302 reads from scan output HTML files and security_scan_config.json
                success = kpi_func(
                    resources_file=self.active_resources_file,
                    output_dir=self.output_dir,
                    fiscal_start_month=self.fiscal_start_month,
                    current_date=current_date
                )
            elif base_kpi == 'k303':
                # K303 reads from scan output HTML files and security_scan_config.json
                success = kpi_func(
                    resources_file=self.active_resources_file,
                    output_dir=self.output_dir,
                    fiscal_start_month=self.fiscal_start_month,
                    current_date=current_date
                )
            elif base_kpi == 'k304':
                # K304 reads from scan output PDF files and security_scan_config.json
                success = kpi_func(
                    resources_file=self.active_resources_file,
                    output_dir=self.output_dir,
                    fiscal_start_month=self.fiscal_start_month,
                    current_date=current_date
                )
            elif base_kpi == 'k305':
                # K305 aggregates k301+k302+k303+k304 outputs
                success = kpi_func(
                    resources_file=self.active_resources_file,
                    output_dir=self.output_dir,
                    fiscal_start_month=self.fiscal_start_month,
                    current_date=current_date
                )
            elif base_kpi == 'k57':
                # K57 needs both JIRA and GitHub data (for UI bugs)
                success = kpi_func(
                    resources_file=self.active_resources_file,
                    jira_issues_file=self.jira_issues_file,
                    output_dir=self.output_dir,
                    fiscal_start_month=self.fiscal_start_month,
                    current_date=current_date
                )
            elif base_kpi == 'k13':
                # K13 needs K3 data (depends on K3 output)
                k3_data_file = os.path.join(self.output_dir, 'k3-data.csv')
                success = kpi_func(
                    resources_file=self.active_resources_file,
                    k3_data_file=k3_data_file,
                    output_dir=self.output_dir,
                    jira_issues_file=self.jira_issues_file,
                    fiscal_start_month=self.fiscal_start_month,
                    current_date=current_date
                )
            elif base_kpi in ['k14', 'k200']:
                # K14 and K200 need K64 data (depend on K64 output)
                success = kpi_func(
                    resources_file=self.active_resources_file,
                    current_date=current_date,
                    fiscal_start_month=self.fiscal_start_month,
                    output_folder=self.output_dir,
                    jira_issues_file=self.jira_issues_file
                )
            else:
                # Default case for future KPIs
                success = kpi_func(
                    resources_file=self.active_resources_file,
                    jira_issues_file=self.jira_issues_file,
                    output_dir=self.output_dir,
                    fiscal_start_month=self.fiscal_start_month,
                    current_date=current_date
                )
            return success
        except Exception as e:
            print(f"Error running KPI {kpi_name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_all_kpis(self, current_date=None):
        """
        Run all available KPI functions.
        
        Args:
            current_date (date): The current date for reporting (default: today)
        
        Returns:
            dict: Dictionary with KPI names as keys and success status as values
        """
        results = {}
        for kpi_name in self.kpi_functions.keys():
            print(f"\nRunning KPI: {kpi_name.upper()}")
            success = self.run_kpi(kpi_name, current_date)
            results[kpi_name] = success
        return results
    
    def read_kpi_data(self, kpi_name, period='Annual', as_of_date: str = None):
        """
        Read KPI data from CSV file for a specific KPI.
        For equivalent KPIs, reads from the base KPI's data file.

        Args:
            kpi_name (str): Name of the KPI (e.g., 'k3' or 'k8')
            period (str): Period column to extract (Weekly, Monthly, Quarterly, or Annual)
            as_of_date (str): Optional date filter in YYYYMMDD format. When provided, only
                              rows matching this CurrentDate are returned. When None, the
                              last row per SAPID/Name is used (current behaviour).

        Returns:
            dict: Dictionary mapping SAPID (preferred) or Name (fallback) to KPI value.
                  Using SAPID as the key avoids collisions when two employees share the
                  same display name across different teams.
        """
        # For equivalent KPIs, use the base KPI's data file
        base_kpi = self.get_base_kpi(kpi_name)
        kpi_file = os.path.join(self.output_dir, f'{base_kpi}-data.csv')

        if not os.path.exists(kpi_file):
            return {}

        kpi_data = {}
        try:
            with open(kpi_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sapid = str(row.get('SAPID', '')).strip()
                    name = str(row.get('Name', '')).strip()
                    # Prefer SAPID as key to avoid same-name collisions across teams
                    key = sapid if sapid else name

                    if as_of_date:
                        row_date = str(row.get('CurrentDate', '')).strip()
                        if row_date != as_of_date:
                            continue

                    value = row.get(period, '')
                    if key and value:
                        try:
                            value = float(value)
                        except ValueError:
                            pass
                        kpi_data[key] = value
        except Exception as e:
            print(f"Warning: Could not read {kpi_file}: {e}")

        return kpi_data
    
    def generate_matrix_report(self, kpis=None, period='Annual', sort_by=None):
        """
        Generate a matrix report showing individuals and their KPI values.
        
        Args:
            kpis (list): List of KPI names to include (default: all available)
            period (str): Period to display (Weekly, Monthly, Quarterly, or Annual)
            sort_by (str): KPI name to sort by, or 'Name' for alphabetical (default: 'Name')
        
        Returns:
            bool: True if successful
        """
        # Determine which KPIs to include
        if kpis is None:
            kpis = self.list_kpis()
        else:
            # Validate KPIs
            invalid_kpis = [k for k in kpis if k not in self.kpi_functions]
            if invalid_kpis:
                print(f"Error: Invalid KPIs: {', '.join(invalid_kpis)}")
                return False
        
        # Sort KPIs by numeric value (k3, k4, k7, k9, k12, etc.)
        kpis = sorted(kpis, key=lambda x: int(x[1:]))
        
        # Read data for all KPIs
        all_data = {}
        for kpi in kpis:
            all_data[kpi] = self.read_kpi_data(kpi, period)
        
        # Collect all unique individuals
        all_individuals = set()
        for kpi_data in all_data.values():
            all_individuals.update(kpi_data.keys())
        
        if not all_individuals:
            print("No data found for the specified KPIs.")
            return False
        
        # Create matrix data structure
        matrix_data = []
        for individual in all_individuals:
            row = {'Name': individual}
            for kpi in kpis:
                row[kpi] = all_data[kpi].get(individual, 0)
            matrix_data.append(row)
        
        # Sort the matrix
        if sort_by is None or sort_by.lower() == 'name':
            matrix_data.sort(key=lambda x: x['Name'])
        elif sort_by in kpis:
            matrix_data.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
        else:
            print(f"Warning: Invalid sort_by '{sort_by}'. Sorting by Name instead.")
            matrix_data.sort(key=lambda x: x['Name'])
        
        # Display the matrix
        self._display_matrix(matrix_data, kpis, period, sort_by)
        
        # Save to CSV
        self._save_matrix_to_csv(matrix_data, kpis, period, sort_by)
        
        return True
    
    def _display_matrix(self, matrix_data, kpis, period, sort_by):
        """
        Display the matrix report in a formatted table.
        
        Args:
            matrix_data (list): List of dictionaries with Name and KPI values
            kpis (list): List of KPI names (column headers)
            period (str): Period being displayed
            sort_by (str): Column used for sorting
        """
        if not matrix_data:
            return
        
        # Calculate column widths
        name_width = max(len('Name'), max(len(row['Name']) for row in matrix_data))
        name_width = min(name_width, 30)  # Cap at 30 characters
        
        kpi_widths = {}
        for kpi in kpis:
            max_value_width = max(len(str(row[kpi])) for row in matrix_data)
            kpi_widths[kpi] = max(len(kpi.upper()), max_value_width, 5)
        
        # Print header
        print("\n" + "="*100)
        print(f"KPI Matrix Report - {period} Period")
        if sort_by:
            sort_display = sort_by if sort_by.lower() != 'name' else 'Name'
            print(f"Sorted by: {sort_display}")
        print("="*100)
        
        # Print column headers
        header = f"{'Name':<{name_width}}"
        for kpi in kpis:
            header += f"  {kpi.upper():>{kpi_widths[kpi]}}"
        print(header)
        print("-"*100)
        
        # Print data rows
        for row in matrix_data:
            name = row['Name']
            if len(name) > name_width:
                name = name[:name_width-3] + '...'
            
            row_str = f"{name:<{name_width}}"
            for kpi in kpis:
                value = row[kpi]
                if isinstance(value, float):
                    if value.is_integer():
                        value_str = f"{int(value)}"
                    else:
                        value_str = f"{value:.1f}"
                else:
                    value_str = str(value)
                row_str += f"  {value_str:>{kpi_widths[kpi]}}"
            print(row_str)
        
        print("="*100)
        print(f"Total Individuals: {len(matrix_data)}")
        print(f"Total KPIs: {len(kpis)}")
        print("="*100 + "\n")
    
    def _save_matrix_to_csv(self, matrix_data, kpis, period, sort_by):
        """
        Save the matrix report to a timestamped CSV file.
        
        Args:
            matrix_data (list): List of dictionaries with Name and KPI values
            kpis (list): List of KPI names (column headers)
            period (str): Period being displayed
            sort_by (str): Column used for sorting
        """
        if not matrix_data:
            return
        
        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"kpi_matrix_{period.lower()}_{timestamp}.csv"
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                # Create CSV writer
                fieldnames = ['Name'] + [kpi.upper() for kpi in kpis]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                
                # Write header
                writer.writeheader()
                
                # Write data rows
                for row in matrix_data:
                    csv_row = {'Name': row['Name']}
                    for kpi in kpis:
                        csv_row[kpi.upper()] = row[kpi]
                    writer.writerow(csv_row)
            
            print(f"Matrix report saved to: {filename}")
        except Exception as e:
            print(f"Warning: Could not save matrix report to CSV: {e}")


def main():
    """Main entry point for command line execution."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='KPI Evaluator - Run KPI evaluation functions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all KPIs (default)
  python KppEvaluator.py
  
  # Run specific KPIs
  python KppEvaluator.py -k k3
  python KppEvaluator.py -k k1 k2 k3
  python KppEvaluator.py --kpis k3
  
  # List available KPIs
  python KppEvaluator.py --list
  
  # Display matrix report
  python KppEvaluator.py --matrix
  python KppEvaluator.py --matrix --kpis k3 k4 k7
  python KppEvaluator.py --matrix --period Quarterly --sort-by k3
        """
    )
    
    parser.add_argument(
        '-k', '--kpis',
        nargs='+',
        metavar='KPI',
        help='Specify one or more KPIs to run (e.g., k1 k2 k3). If not specified, all KPIs will run.'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all available KPIs and exit'
    )
    
    parser.add_argument(
        '--describe',
        action='store_true',
        help='Show descriptions of all available KPIs and exit'
    )
    
    parser.add_argument(
        '--matrix',
        action='store_true',
        help='Display KPI matrix report showing individuals and their KPI values'
    )
    
    parser.add_argument(
        '--period',
        type=str,
        choices=['Weekly', 'Monthly', 'Quarterly', 'Annual'],
        default='Annual',
        help='Period to display in matrix report (default: Annual)'
    )
    
    parser.add_argument(
        '--sort-by',
        type=str,
        metavar='KPI',
        help='KPI to sort by in matrix report (default: Name). Use "Name" for alphabetical sorting.'
    )
    
    parser.add_argument(
        '--fiscal-month',
        type=int,
        default=4,
        metavar='MONTH',
        help='Fiscal year start month (1-12, default: 4 for April)'
    )

    parser.add_argument(
        '--project-root',
        type=str,
        default=None,
        metavar='PATH',
        help='TeamSight project root containing config/ and output/ (defaults: TEAMSIGHT_HOME, then current directory)'
    )
    
    args = parser.parse_args()
    
    # Get the TeamSight project root directory
    project_root = _resolve_project_root(args.project_root)
    
    # Set up paths
    resources_file = project_root / 'config' / 'Resources.csv'
    jira_issues_file = project_root / 'output' / 'JIRAIssues.csv'
    github_commits_file = project_root / 'output' / 'github_commits.csv'
    output_dir = project_root / 'output'

    if not resources_file.exists():
        print(f"Error: Resources file not found at {resources_file}")
        print("Set --project-root or TEAMSIGHT_HOME to your TeamSight installation directory.")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create evaluator instance
    evaluator = KppEvaluator(
        resources_file=str(resources_file),
        jira_issues_file=str(jira_issues_file),
        github_commits_file=str(github_commits_file),
        output_dir=str(output_dir),
        fiscal_start_month=args.fiscal_month
    )
    
    # Handle --list option
    if args.list:
        print("Available KPIs:")
        for kpi in evaluator.list_kpis():
            print(f"  - {kpi}")
        sys.exit(0)
    
    # Handle --describe option
    if args.describe:
        evaluator.describe_kpis()
        sys.exit(0)
    
    # Handle --matrix option
    if args.matrix:
        success = evaluator.generate_matrix_report(
            kpis=args.kpis,
            period=args.period,
            sort_by=args.sort_by
        )
        sys.exit(0 if success else 1)
    
    # Determine which KPIs to run
    if args.kpis:
        kpis_to_run = args.kpis
        print(f"Running specified KPIs: {', '.join(kpis_to_run)}\n")
    else:
        kpis_to_run = evaluator.list_kpis()
        print(f"Running all KPIs: {', '.join(kpis_to_run)}\n")
    
    # Run the KPIs
    results = {}
    for kpi in kpis_to_run:
        success = evaluator.run_kpi(kpi)
        results[kpi] = success
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    for kpi, success in results.items():
        status = "✓" if success else "✗"
        print(f"{status} {kpi.upper()}: {'Success' if success else 'Failed'}")
    
    print(f"\nCompleted: {success_count}/{total_count} KPIs successful")
    
    # Exit with appropriate status code
    if success_count == total_count:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
