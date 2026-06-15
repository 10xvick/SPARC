"""
Service for loading and managing Roles.csv (KPI definitions).
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
import logging

from app.config import settings

logger = logging.getLogger(__name__)

class RolesService:
    def __init__(self):
        self.csv_path = settings.roles_csv_path
        self._data: Optional[pd.DataFrame] = None
        self._last_load: Optional[datetime] = None

    @staticmethod
    def _parse_target_value(value) -> float:
        """Convert target value to float, handling %, text, and empty values safely."""
        if pd.isna(value):
            return 0.0

        if isinstance(value, (int, float, np.number)):
            return float(value)

        text = str(value).strip()
        if text == "":
            return 0.0

        if text.endswith('%'):
            text = text[:-1].strip()

        text = text.replace(',', '')

        try:
            return float(text)
        except ValueError:
            return 0.0
    
    def load_data(self, force_reload: bool = False) -> pd.DataFrame:
        """Load or reload Roles.csv data."""
        if self._data is None or force_reload:
            try:
                logger.info(f"Loading Roles.csv from {self.csv_path}")
                self._data = pd.read_csv(self.csv_path)
                self._last_load = datetime.now()
                logger.info(f"Loaded {len(self._data)} KPIs/roles")
            except Exception as e:
                logger.error(f"Error loading Roles.csv: {e}")
                raise
        return self._data
    
    def get_all_roles(self,
                     primary_role: Optional[str] = None,
                     secondary_role: Optional[str] = None,
                     goal_type: Optional[str] = None,
                     active: Optional[bool] = None,
                     search: Optional[str] = None) -> List[Dict]:
        """Get all roles/KPIs with optional filtering."""
        df = self.load_data()
        
        # Apply filters
        if primary_role:
            df = df[df['Role'] == primary_role]
        if goal_type:
            df = df[df['Goal Type'] == goal_type]
        if search:
            mask = (
                df['Index'].str.contains(search, case=False, na=False) |
                df['KPP Goals'].str.contains(search, case=False, na=False)
            )
            df = df[mask]
        
        # Convert to list of dicts
        roles = []
        for _, row in df.iterrows():
            try:
                # Handle potential missing/nan values
                weekly = row.get('Weekly Target', 0)
                quarterly = row.get('Quarterly Target', 0)
                annual = row.get('Annual Target', 0)
                
                roles.append({
                    'index': str(row['Index']),
                    'name': str(row['KPP Goals']) if pd.notna(row.get('KPP Goals')) else '',
                    'primary_role': str(row['Role']) if pd.notna(row.get('Role')) else '',
                    'secondary_role': '',
                    'goal_type': str(row['Goal Type']) if pd.notna(row.get('Goal Type')) else '',
                    'kpp_goals': str(row['KPP Goals']) if pd.notna(row.get('KPP Goals')) else '',
                    'measurement_criteria': str(row['Measurement Criteria']) if pd.notna(row.get('Measurement Criteria')) else '',
                    'tool': str(row['Tool']) if pd.notna(row.get('Tool')) else '',
                    'measure': str(row['Measure']) if pd.notna(row.get('Measure')) else '',
                    'weekly_target': self._parse_target_value(weekly),
                    'quarterly_target': self._parse_target_value(quarterly),
                    'annual_target': self._parse_target_value(annual),
                    'aggregation_type': str(row['Aggregation Type']) if pd.notna(row.get('Aggregation Type')) else '',
                    'prorate': str(row.get('Prorate', 'Yes')).strip().lower() != 'no',
                    'active': True
                })
            except Exception as e:
                logger.error(f"Error processing role {row.get('Index', 'unknown')}: {e}")
                continue
        
        return roles
    
    def get_role_by_index(self, index: str) -> Optional[Dict]:
        """Get a single role/KPI by index."""
        df = self.load_data()
        role = df[df['Index'] == index]
        
        if role.empty:
            return None
        
        row = role.iloc[0]
        return {
            'index': str(row['Index']),
            'name': str(row['KPP Goals']) if pd.notna(row.get('KPP Goals')) else '',
            'primary_role': str(row['Role']) if pd.notna(row.get('Role')) else '',
            'secondary_role': '',
            'goal_type': str(row['Goal Type']) if pd.notna(row.get('Goal Type')) else '',
            'kpp_goals': str(row['KPP Goals']) if pd.notna(row.get('KPP Goals')) else '',
            'measurement_criteria': str(row['Measurement Criteria']) if pd.notna(row.get('Measurement Criteria')) else '',
            'tool': str(row['Tool']) if pd.notna(row.get('Tool')) else '',
            'measure': str(row['Measure']) if pd.notna(row.get('Measure')) else '',
            'weekly_target': self._parse_target_value(row.get('Weekly Target')),
            'quarterly_target': self._parse_target_value(row.get('Quarterly Target')),
            'annual_target': self._parse_target_value(row.get('Annual Target')),
            'aggregation_type': str(row['Aggregation Type']) if pd.notna(row.get('Aggregation Type')) else '',
            'prorate': str(row.get('Prorate', 'Yes')).strip().lower() != 'no',
            'active': True
        }
    
    def update_targets(self, index: str, weekly: float, quarterly: float, annual: float) -> Dict:
        """Update targets for a specific KPI."""
        df = self.load_data()
        mask = df['Index'] == index
        
        if not mask.any():
            raise ValueError(f"KPI {index} not found")
        
        df.loc[mask, 'Weekly Target'] = weekly
        df.loc[mask, 'Quarterly Target'] = quarterly
        df.loc[mask, 'Annual Target'] = annual
        
        self.save_data(df)
        
        return self.get_role_by_index(index)
    
    def get_goal_types(self) -> List[str]:
        """Get list of unique goal types."""
        df = self.load_data()
        return sorted(df['Goal Type'].dropna().unique().tolist())

    def get_primary_roles(self) -> List[str]:
        """Get list of unique primary roles."""
        df = self.load_data()
        if 'Role' not in df.columns:
            return []

        return sorted(
            role
            for role in df['Role'].dropna().astype(str).str.strip().unique().tolist()
            if role
        )
    
    def get_aggregation_types(self) -> List[str]:
        """Get list of unique aggregation types."""
        df = self.load_data()
        return sorted(df['Aggregation Type'].dropna().unique().tolist())
    
    def export_to_csv(self) -> str:
        """Export roles data to CSV string."""
        df = self.load_data()
        return df.to_csv(index=False)
    
    def import_from_csv(self, csv_content: str) -> dict:
        """Import roles/KPIs from CSV content."""
        try:
            # Read CSV from string
            import io
            new_df = pd.read_csv(io.StringIO(csv_content))
            
            # Validate required columns
            required_columns = ['Index', 'Role', 'KPP Goals']
            missing_columns = [col for col in required_columns if col not in new_df.columns]
            if missing_columns:
                return {
                    "success": False,
                    "message": f"Missing required columns: {', '.join(missing_columns)}"
                }
            
            # Load existing data
            existing_df = self.load_data()
            
            # Track statistics
            added = 0
            updated = 0
            errors = []
            
            # Process each row
            for idx, row in new_df.iterrows():
                try:
                    index = str(row['Index'])
                    
                    # Check if role exists
                    existing_mask = existing_df['Index'] == index
                    
                    if existing_mask.any():
                        # Update existing role
                        for col in new_df.columns:
                            if col in existing_df.columns:
                                existing_df.loc[existing_mask, col] = row[col]
                        updated += 1
                    else:
                        # Add new role
                        new_row = pd.DataFrame([row])
                        existing_df = pd.concat([existing_df, new_row], ignore_index=True)
                        added += 1
                        
                except Exception as e:
                    errors.append(f"Row {idx + 2}: {str(e)}")
            
            # Save changes
            self.save_data(existing_df)
            
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
            # Strip column names to avoid formatting issues
            df.columns = [str(col).strip() for col in df.columns]
            
            # Backup existing file
            backup_path = self.csv_path.parent / f"Roles_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            if self.csv_path.exists():
                import shutil
                shutil.copy2(self.csv_path, backup_path)
            
            # Save new data
            df.to_csv(self.csv_path, index=False)
            self._data = None  # Force reload on next access
            logger.info(f"Saved Roles.csv ({len(df)} rows)")
        except Exception as e:
            logger.error(f"Error saving Roles.csv: {e}")
            raise

# Global instance
roles_service = RolesService()
