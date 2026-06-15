"""
Service for loading and managing Resources.csv (Employee data).
"""
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from app.config import settings

logger = logging.getLogger(__name__)

class ResourcesService:
    def __init__(self):
        self.csv_path = settings.resources_csv_path
        self._data: Optional[pd.DataFrame] = None
        self._last_load: Optional[datetime] = None
        self.STATUS_COLUMN = 'Employment Status'

    FISCAL_START_MONTH: int = 4  # April

    def _get_fiscal_year_start_str(self) -> str:
        """Return current fiscal year start as YYYY-MM-DD string."""
        from datetime import date as _date
        today = _date.today()
        year = today.year if today.month >= self.FISCAL_START_MONTH else today.year - 1
        return f"{year}-{self.FISCAL_START_MONTH:02d}-01"

    def _ensure_start_date_column(self, df: 'pd.DataFrame') -> 'pd.DataFrame':
        """Ensure Start Date column exists, filling blanks with fiscal year start."""
        default = self._get_fiscal_year_start_str()
        if 'Start Date' not in df.columns:
            df['Start Date'] = default
        else:
            s = df['Start Date'].fillna('').astype(str).str.strip()
            df['Start Date'] = s.where(s.str.len() > 0, default)
            df.loc[df['Start Date'] == 'nan', 'Start Date'] = default
        return df

    @classmethod
    def normalize_employment_status(cls, value) -> str:
        """Normalize employment status values to Active/Inactive."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return 'Active'

        normalized = str(value).strip().lower()
        if normalized in {'inactive', 'false', 'no', 'n', '0', 'disabled'}:
            return 'Inactive'
        return 'Active'

    @staticmethod
    def _safe_str(value, default: str = '') -> str:
        """Return str(value) or default if value is NaN/None - prevents JSON nan crash."""
        if value is None:
            return default
        try:
            if pd.isna(value):
                return default
        except (TypeError, ValueError):
            pass
        return str(value)

    @staticmethod
    def _is_valid_team_name(value: Any) -> bool:
        """Exclude placeholder/no-team markers from team dropdown options."""
        if value is None:
            return False
        try:
            if pd.isna(value):
                return False
        except (TypeError, ValueError):
            pass

        normalized = str(value).strip()
        if not normalized:
            return False

        return normalized.lower() != '-na-'

    @classmethod
    def is_employee_active(cls, value) -> bool:
        return cls.normalize_employment_status(value) == 'Active'

    def _ensure_status_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure status column exists and contains normalized values."""
        if self.STATUS_COLUMN not in df.columns:
            df[self.STATUS_COLUMN] = 'Active'
        df[self.STATUS_COLUMN] = df[self.STATUS_COLUMN].apply(self.normalize_employment_status)
        return df
    
    def load_data(self, force_reload: bool = False) -> pd.DataFrame:
        """Load or reload Resources.csv data."""
        if self._data is None or force_reload:
            try:
                logger.info(f"Loading Resources.csv from {self.csv_path}")
                # Read SAPID as string to preserve leading zeros
                self._data = pd.read_csv(self.csv_path, dtype={'SAPID': str})
                self._data.columns = [str(column).strip() for column in self._data.columns]
                object_columns = self._data.select_dtypes(include=['object']).columns
                for column in object_columns:
                    self._data[column] = self._data[column].apply(
                        lambda value: str(value).strip() if pd.notna(value) else value
                    )
                self._data = self._ensure_status_column(self._data)
                self._data = self._ensure_start_date_column(self._data)
                self._last_load = datetime.now()
                logger.info(f"Loaded {len(self._data)} employees")
            except Exception as e:
                logger.error(f"Error loading Resources.csv: {e}")
                raise
        return self._data
    
    def get_ref_by_sapid(self, sapid: str) -> Optional[str]:
        """Get the Ref number for a given SAPID."""
        df = self.load_data()
        employee = df[df['SAPID'].astype(str) == sapid]
        if employee.empty:
            return None
        return str(employee.iloc[0].get('Ref', ''))
    
    def get_sapid_by_ref(self, ref: str) -> Optional[str]:
        """Get the SAPID for a given Ref number."""
        df = self.load_data()
        employee = df[df['Ref'].astype(str) == ref]
        if employee.empty:
            return None
        return str(employee.iloc[0]['SAPID'])

    def get_ref_by_name(self, name: str) -> Optional[str]:
        """Get the Ref number for a given employee name (case-insensitive)."""
        normalized_name = str(name or '').strip().lower()
        if not normalized_name:
            return None

        df = self.load_data()
        matches = df[df['Name'].astype(str).str.strip().str.lower() == normalized_name]
        if matches.empty:
            return None
        return str(matches.iloc[0].get('Ref', ''))
    
    def get_all_employees(self, 
                         team: Optional[str] = None,
                         scrum: Optional[str] = None,
                         primary_role: Optional[str] = None,
                         secondary_role: Optional[str] = None,
                         search: Optional[str] = None,
                         include_inactive: bool = True) -> List[Dict]:
        """Get all employees with optional filtering."""
        df = self.load_data()

        if not include_inactive:
            df = df[df[self.STATUS_COLUMN].apply(self.is_employee_active)]
        
        # Apply filters
        if team:
            df = df[df['Team'] == team]
        if scrum:
            df = df[df['Scrum'] == scrum]
        if primary_role:
            df = df[df['Primary Role'] == primary_role]
        if secondary_role:
            df = df[df['Secondary Role'] == secondary_role]
        if search:
            mask = (
                df['Name'].str.contains(search, case=False, na=False) |
                df['SAPID'].astype(str).str.contains(search, case=False, na=False)
            )
            df = df[mask]
        
        # Convert to list of dicts
        employees = []
        for _, row in df.iterrows():
            # Convert manager Ref to SAPID for display
            manager_ref = str(row.get('Manager', ''))
            manager_sapid = self.get_sapid_by_ref(manager_ref) if manager_ref else None
            
            employees.append({
                'ref': self._safe_str(row.get('Ref')),
                'sapid': self._safe_str(row.get('SAPID')),
                'name': self._safe_str(row.get('Name')),
                'team': self._safe_str(row.get('Team')),
                'scrum': self._safe_str(row.get('Scrum')),
                'primary_role': self._safe_str(row.get('Primary Role')),
                'secondary_role': self._safe_str(row.get('Secondary Role')),
                'reporting': float(row.get('Reporting', 0)) if pd.notna(row.get('Reporting')) else None,
                'manager': manager_sapid if manager_sapid else '',
                'manager_name': self._safe_str(row.get('Manager Name')),
                'email': self._safe_str(row.get('EMail')),
                'resource_sheet_name': self._safe_str(row.get('ResourceSheetName')),
                'resource_sheet_id': self._safe_str(row.get('ResourceSheetID')),
                'jira_name': self._safe_str(row.get('JIRA Name')),
                'git_email': self._safe_str(row.get('GIT Email')),
                'udeid': self._safe_str(row.get('UDEID')),
                'tacid': self._safe_str(row.get('TACID')),
                'url': self._safe_str(row.get('URL')),
                'github_name': self._safe_str(row.get('GitHUB Name')),
                'copilot_user': self._safe_str(row.get('copilot_user')),
                'employment_status': self.normalize_employment_status(row.get(self.STATUS_COLUMN, 'Active')),
                'start_date': self._safe_str(row.get('Start Date')),
            })
        
        return employees
    
    def get_employee_by_sapid(self, sapid: str) -> Optional[Dict]:
        """Get a single employee by SAPID."""
        df = self.load_data()
        employee = df[df['SAPID'].astype(str) == sapid]
        
        if employee.empty:
            return None
        
        row = employee.iloc[0]
        
        # Convert manager Ref to SAPID for display
        manager_ref = str(row.get('Manager', ''))
        manager_sapid = self.get_sapid_by_ref(manager_ref) if manager_ref else None
        
        return {
            'ref': self._safe_str(row.get('Ref')),
            'sapid': self._safe_str(row.get('SAPID')),
            'name': self._safe_str(row.get('Name')),
            'team': self._safe_str(row.get('Team')),
            'scrum': self._safe_str(row.get('Scrum')),
            'primary_role': self._safe_str(row.get('Primary Role')),
            'secondary_role': self._safe_str(row.get('Secondary Role')),
            'reporting': float(row.get('Reporting', 0)) if pd.notna(row.get('Reporting')) else None,
            'manager': manager_sapid if manager_sapid else '',
            'manager_name': self._safe_str(row.get('Manager Name')),
            'email': self._safe_str(row.get('EMail')),
            'resource_sheet_name': self._safe_str(row.get('ResourceSheetName')),
            'resource_sheet_id': self._safe_str(row.get('ResourceSheetID')),
            'jira_name': self._safe_str(row.get('JIRA Name')),
            'git_email': self._safe_str(row.get('GIT Email')),
            'udeid': self._safe_str(row.get('UDEID')),
            'tacid': self._safe_str(row.get('TACID')),
            'url': self._safe_str(row.get('URL')),
            'github_name': self._safe_str(row.get('GitHUB Name')),
            'copilot_user': self._safe_str(row.get('copilot_user')),
            'employment_status': self.normalize_employment_status(row.get(self.STATUS_COLUMN, 'Active')),
            'start_date': self._safe_str(row.get('Start Date')),
        }
    
    def get_teams(self) -> List[str]:
        """Get list of unique teams."""
        df = self.load_data()
        teams = [
            str(team).strip()
            for team in df['Team'].unique().tolist()
            if self._is_valid_team_name(team)
        ]
        return sorted(set(teams))
    
    def get_scrums(self) -> List[str]:
        """Get list of unique scrums."""
        df = self.load_data()
        return sorted(df['Scrum'].dropna().unique().tolist())
    
    def get_primary_roles(self) -> List[str]:
        """Get list of unique primary roles."""
        df = self.load_data()
        return sorted(df['Primary Role'].dropna().unique().tolist())
    
    def get_secondary_roles(self) -> List[str]:
        """Get list of unique secondary roles."""
        df = self.load_data()
        roles = df['Secondary Role'].dropna().unique().tolist()
        return sorted([r for r in roles if r])
    
    def get_manager_options(self) -> List[Dict]:
        """Get list of all employees formatted for manager dropdown."""
        df = self.load_data()
        df = df[df[self.STATUS_COLUMN].apply(self.is_employee_active)]
        managers = []
        for _, row in df.iterrows():
            sapid = str(row['SAPID'])
            name = row['Name']
            managers.append({
                'value': sapid,
                'label': f"{sapid} - {name}"
            })
        # Sort by SAPID
        return sorted(managers, key=lambda x: x['value'])
    
    def update_employee(self, sapid: str, updates: dict) -> Optional[Dict]:
        """Update employee information."""
        df = self.load_data()
        
        # Find employee
        mask = df['SAPID'].astype(str) == str(sapid)
        if not mask.any():
            return None

        # Normalize manager data from edit payload (supports SAPID/Ref/name/manual text)
        manager_value = str(updates.get('Manager', '')).strip() if 'Manager' in updates else None
        manager_name_input = str(updates.get('Manager Name', '')).strip() if 'Manager Name' in updates else ''
        if manager_value is not None:
            if manager_value:
                manager_ref = None
                manager_sapid = None

                if manager_value.replace('.', '', 1).isdigit():
                    manager_ref_candidate = str(int(float(manager_value)))
                    manager_sapid_from_ref = self.get_sapid_by_ref(manager_ref_candidate)
                    if manager_sapid_from_ref:
                        manager_ref = manager_ref_candidate
                        manager_sapid = manager_sapid_from_ref

                if manager_ref is None:
                    manager_ref = self.get_ref_by_sapid(manager_value)
                    if manager_ref:
                        manager_sapid = manager_value

                if manager_ref is None:
                    manager_ref = self.get_ref_by_name(manager_value)
                    if manager_ref:
                        manager_sapid = self.get_sapid_by_ref(manager_ref)

                if manager_ref:
                    updates['Manager'] = manager_ref
                    manager_info: Optional[Dict[str, Any]] = None
                    if manager_sapid:
                        manager_info = self.get_employee_by_sapid(manager_sapid)
                    updates['Manager Name'] = (
                        str((manager_info or {}).get('name', '')).strip()
                        or manager_name_input
                        or manager_value
                    )
                else:
                    updates['Manager'] = ''
                    updates['Manager Name'] = manager_name_input or manager_value
            else:
                updates['Manager'] = ''
                if 'Manager Name' not in updates:
                    updates['Manager Name'] = ''
        
        # Update fields
        for field, value in updates.items():
            target_field = field
            if field == 'employment_status':
                target_field = self.STATUS_COLUMN
            if target_field in df.columns:
                if target_field == self.STATUS_COLUMN:
                    df.loc[mask, target_field] = self.normalize_employment_status(value)
                else:
                    df.loc[mask, target_field] = value
        
        # Save changes
        self.save_data(df)
        
        # Return updated employee
        return self.get_employee_by_sapid(sapid)
    
    def add_employee(self, employee_data: dict) -> Dict:
        """Add a new employee."""
        df = self.load_data()
        
        # Auto-generate Ref — always override if blank/missing; guarantee uniqueness.
        incoming_ref = str(employee_data.get('Ref', '')).strip()
        if not incoming_ref:
            numeric_refs = pd.to_numeric(df['Ref'], errors='coerce').dropna()
            next_ref = int(numeric_refs.max()) + 1 if len(numeric_refs) > 0 else 1
            existing_ref_strs = set(df['Ref'].astype(str).str.strip().tolist())
            while str(next_ref) in existing_ref_strs:
                next_ref += 1
            employee_data['Ref'] = next_ref
        
        # Normalize manager data. Supports manager values as SAPID, Ref, or name.
        manager_sapid = None
        manager_value = str(employee_data.get('Manager', '')).strip()
        manager_name_input = str(employee_data.get('Manager Name', '')).strip()
        if manager_value:
            manager_ref = None

            # Accept existing Ref directly when provided.
            if manager_value.replace('.', '', 1).isdigit():
                manager_ref_candidate = str(int(float(manager_value)))
                manager_sapid_from_ref = self.get_sapid_by_ref(manager_ref_candidate)
                if manager_sapid_from_ref:
                    manager_ref = manager_ref_candidate
                    manager_sapid = manager_sapid_from_ref

            # Fall back to SAPID lookup.
            if manager_ref is None:
                manager_ref = self.get_ref_by_sapid(manager_value)
                if manager_ref:
                    manager_sapid = manager_value

            # Fall back to exact-name lookup.
            if manager_ref is None:
                manager_ref = self.get_ref_by_name(manager_value)
                if manager_ref:
                    manager_sapid = self.get_sapid_by_ref(manager_ref)

            if manager_ref:
                employee_data['Manager'] = manager_ref
                manager_info: Optional[Dict[str, Any]] = None
                if manager_sapid:
                    manager_info = self.get_employee_by_sapid(manager_sapid)
                employee_data['Manager Name'] = (
                    str((manager_info or {}).get('name', '')).strip()
                    or manager_name_input
                    or manager_value
                )
            else:
                # Manager not found in Resources.csv; preserve manager display name only.
                logger.info(f"Manager value '{manager_value}' not found in Resources.csv; storing as Manager Name")
                employee_data['Manager'] = ''
                if manager_name_input:
                    employee_data['Manager Name'] = manager_name_input
                else:
                    employee_data['Manager Name'] = manager_value
        
        # Create new row
        if self.STATUS_COLUMN not in employee_data:
            employee_data[self.STATUS_COLUMN] = 'Active'
        else:
            employee_data[self.STATUS_COLUMN] = self.normalize_employment_status(employee_data[self.STATUS_COLUMN])

        new_row = pd.DataFrame([employee_data])
        df = pd.concat([df, new_row], ignore_index=True)
        
        # Update manager's Reporting count if manager was set
        if manager_sapid:
            self._update_manager_reporting_count(df, manager_sapid)
        
        # Save changes
        self.save_data(df)
        
        # Return new employee
        return self.get_employee_by_sapid(employee_data['SAPID'])
    
    def _update_manager_reporting_count(self, df: pd.DataFrame, manager_sapid: str):
        """Update the Reporting count for a manager based on direct reports."""
        # Count how many employees report to this manager
        manager_ref = self.get_ref_by_sapid(manager_sapid)
        if manager_ref:
            # Count direct reports
            direct_reports = df[df['Manager'].astype(str) == str(manager_ref)].shape[0]
            # Update the manager's Reporting column
            manager_mask = df['SAPID'] == manager_sapid
            if manager_mask.any():
                df.loc[manager_mask, 'Reporting'] = direct_reports
                logger.info(f"Updated Reporting count for {manager_sapid} to {direct_reports}")
    
    def recalculate_all_reporting_counts(self):
        """Recalculate Reporting counts for all managers."""
        df = self.load_data()
        
        # Initialize all Reporting counts to 0
        df['Reporting'] = 0
        
        # Count direct reports for each manager
        manager_refs = df['Manager'].dropna().unique()
        for manager_ref in manager_refs:
            if manager_ref and str(manager_ref).strip():
                # Count employees reporting to this manager
                count = df[df['Manager'].astype(str) == str(manager_ref)].shape[0]
                # Get manager SAPID from Ref
                manager_sapid = self.get_sapid_by_ref(str(manager_ref))
                if manager_sapid:
                    manager_mask = df['SAPID'] == manager_sapid
                    if manager_mask.any():
                        df.loc[manager_mask, 'Reporting'] = count
        
        # Save changes
        self.save_data(df)
        logger.info("Recalculated all reporting counts")
        return {"success": True, "message": "Reporting counts recalculated"}
    
    def export_to_csv(self) -> str:
        """Export employees data to CSV string."""
        df = self.load_data()
        return df.to_csv(index=False)
    
    def import_from_csv(self, csv_content: str) -> dict:
        """Import employees from CSV content."""
        try:
            # Read CSV from string
            import io
            new_df = pd.read_csv(io.StringIO(csv_content))
            
            # Validate required columns
            required_columns = ['SAPID', 'Name', 'Team', 'Scrum', 'Primary Role']
            missing_columns = [col for col in required_columns if col not in new_df.columns]
            if missing_columns:
                return {
                    "success": False,
                    "message": f"Missing required columns: {', '.join(missing_columns)}"
                }
            
            # Load existing data
            existing_df = self.load_data()
            existing_df = self._ensure_status_column(existing_df)
            new_df = self._ensure_status_column(new_df)
            
            # Normalize SAPID columns for comparison
            # Convert to numeric (handles both "52090140" and "52090140.0" formats)
            # Then convert to int to remove decimals, then to string
            def normalize_sapid(sapid):
                """Convert SAPID to normalized string format (no decimal points)."""
                try:
                    # Convert to float first (handles string or numeric input)
                    # Then to int (removes .0), then to string
                    return str(int(float(sapid)))
                except (ValueError, TypeError):
                    return str(sapid).strip()
            
            existing_df['SAPID'] = existing_df['SAPID'].apply(normalize_sapid)
            new_df['SAPID'] = new_df['SAPID'].apply(normalize_sapid)
            
            # Track statistics
            added = 0
            updated = 0
            errors = []
            
            # Process each row
            for idx, row in new_df.iterrows():
                try:
                    sapid = normalize_sapid(row['SAPID'])
                    
                    # Check if employee exists
                    existing_mask = existing_df['SAPID'] == sapid
                    
                    if existing_mask.any():
                        # Update existing employee
                        for col in new_df.columns:
                            if col in existing_df.columns:
                                existing_df.loc[existing_mask, col] = row[col]
                        updated += 1
                    else:
                        # Add new employee
                        # Ensure Ref is set
                        if 'Ref' not in row or pd.isna(row['Ref']):
                            max_ref = existing_df['Ref'].astype(float).max()
                            row['Ref'] = int(max_ref + 1) if pd.notna(max_ref) else 1
                        
                        new_row = pd.DataFrame([row])
                        existing_df = pd.concat([existing_df, new_row], ignore_index=True)
                        added += 1
                        
                except Exception as e:
                    errors.append(f"Row {idx + 2}: {str(e)}")
            
            # Save changes
            self.save_data(existing_df)
            
            # Recalculate reporting counts
            self.recalculate_all_reporting_counts()
            
            return {
                "success": True,
                "message": f"Import completed: {added} added, {updated} updated",
                "details": {
                    "added": added,
                    "updated": updated,
                    "errors": errors
                }
            }
            
        except Exception as e:
            logger.error(f"Import failed: {e}")
            return {
                "success": False,
                "message": f"Import failed: {str(e)}"
            }
    
    def save_data(self, df: pd.DataFrame):
        """Save DataFrame back to CSV."""
        try:
            df = self._ensure_status_column(df.copy())
            df = self._ensure_start_date_column(df)
            # Strip column names to avoid formatting issues
            df.columns = [str(col).strip() for col in df.columns]
            
            # Backup existing file
            backup_path = self.csv_path.parent / f"Resources_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            if self.csv_path.exists():
                import shutil
                shutil.copy2(self.csv_path, backup_path)
            
            # Save new data
            df.to_csv(self.csv_path, index=False)
            self._data = None  # Force reload on next access
            logger.info(f"Saved Resources.csv ({len(df)} rows)")
        except Exception as e:
            logger.error(f"Error saving Resources.csv: {e}")
            raise

    def set_employee_status(self, sapid: str, status: str) -> Optional[Dict]:
        """Set employee employment status (Active/Inactive)."""
        normalized_status = self.normalize_employment_status(status)
        return self.update_employee(sapid, {self.STATUS_COLUMN: normalized_status})

    def delete_employee(self, sapid: str) -> bool:
        """Hard delete employee from Resources.csv."""
        df = self.load_data()
        mask = df['SAPID'].astype(str) == str(sapid)
        if not mask.any():
            return False

        deleted_rows = df[mask]
        deleted_ref = str(deleted_rows.iloc[0].get('Ref', '')).strip()

        df = df[~mask].copy()

        if deleted_ref:
            manager_mask = df['Manager'].astype(str).str.strip() == deleted_ref
            if manager_mask.any():
                df.loc[manager_mask, 'Manager'] = ''
                if 'Manager Name' in df.columns:
                    df.loc[manager_mask, 'Manager Name'] = ''

        self.save_data(df)
        self.recalculate_all_reporting_counts()
        return True

# Global instance
resources_service = ResourcesService()
