"""
User sync service for syncing users from Resources.csv.
Sync is add-only: creates new users and updates existing ones, but does not delete.
"""
import os
import pandas as pd
from typing import Dict, List, Any
import logging
from pathlib import Path

from app.services.user_service import UserService
from app.models.user import UserCreate, UserUpdate
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
RESOURCES_CSV_FILE = os.getenv(
    "TEAMSIGHT_RESOURCES_CSV",
    str(PROJECT_ROOT / "config" / "Resources.csv")
)


class UserSyncService:
    """User sync service for Resources.csv"""
    
    def __init__(self, user_service: UserService):
        """
        Initialize sync service
        
        Args:
            user_service: UserService instance
        """
        self.user_service = user_service
        self.resources_file = RESOURCES_CSV_FILE
    
    @staticmethod
    def _determine_role(row: pd.Series) -> str:
        """
        Determine user role based on Resources.csv columns
        
        Role assignment logic (priority order):
        1. If Reporting > 0 and role contains 'manager' → "Team Manager"
        2. Else if Reporting > 0 → "Lead"
        3. Else → "User"
        
        Args:
            row: DataFrame row
        
        Returns:
            Role name
        """
        reporting = pd.to_numeric(row.get("Reporting", 0), errors="coerce")
        reporting_count = int(reporting) if pd.notna(reporting) else 0
        primary_role = str(row.get("Primary Role", "")).strip().lower()

        if reporting_count > 0 and "manager" in primary_role:
            return "Team Manager"
        if reporting_count > 0:
            return "Lead"
        return "User"

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize names for matching."""
        return str(name or "").strip().lower()

    @staticmethod
    def _derive_email(row: pd.Series, name: str) -> str:
        """Get email from CSV or derive a default."""
        email_value = str(row.get("EMail", "")).strip()
        if email_value and email_value.lower() != "nan":
            return email_value
        return f"{name.lower().replace(' ', '.')}@company.com"

    def _build_manager_relationships(self, df: pd.DataFrame) -> Dict[int, List[int]]:
        """
        Build manager -> report user_id mapping from Resources.csv.

        Uses `Manager Name` column to map employee rows to manager users.
        """
        users = self.user_service.get_all_users(active_only=False)
        user_by_sapid = {str(u.sapid): u for u in users}
        user_id_by_name = {
            self._normalize_name(u.name): u.id
            for u in users
        }

        manager_to_reports: Dict[int, List[int]] = {}

        for _, row in df.iterrows():
            user_sapid = str(row.get("SAPID", "")).strip()
            if not user_sapid:
                continue

            report_user = user_by_sapid.get(user_sapid)
            if not report_user:
                continue

            manager_name = self._normalize_name(str(row.get("Manager Name", "")))
            if not manager_name:
                continue

            manager_id = user_id_by_name.get(manager_name)
            if not manager_id:
                continue

            manager_to_reports.setdefault(manager_id, []).append(report_user.id)

        # Deduplicate and sort
        for manager_id, report_ids in list(manager_to_reports.items()):
            manager_to_reports[manager_id] = sorted(set(report_ids))

        return manager_to_reports
    
    def sync_users(self) -> Dict[str, Any]:
        """
        Sync users from Resources.csv
        
        Add-only logic:
        - Creates new users from CSV
        - Updates existing users (team, role changes)
        - Does NOT delete or deactivate users
        
        Returns:
            Summary dict: { created: int, updated: int, errors: List[str] }
        """
        try:
            df = pd.read_csv(self.resources_file)
        except FileNotFoundError:
            logger.error(f"Resources.csv not found: {self.resources_file}")
            return {
                "created": 0,
                "updated": 0,
                "errors": [f"Resources.csv not found: {self.resources_file}"]
            }
        except Exception as e:
            logger.error(f"Error reading Resources.csv: {e}")
            return {
                "created": 0,
                "updated": 0,
                "errors": [str(e)]
            }
        
        created = 0
        updated = 0
        errors: List[str] = []
        
        logger.info(f"Starting user sync from {self.resources_file}")
        
        for idx, row in df.iterrows():
            try:
                sapid = str(row.get("SAPID", "")).strip()
                name = str(row.get("Name", "")).strip()
                team = str(row.get("Team", "")).strip()
                
                if not sapid or not name:
                    logger.warning(f"Row {idx}: Missing SAPID or Name, skipping")
                    continue
                
                # Determine role
                role = self._determine_role(row)
                email = self._derive_email(row, name)
                
                # Check if user exists
                existing_user = self.user_service.get_user_by_sapid(sapid)
                
                if existing_user:
                    # User exists: update if needed
                    team_ids = [team] if team else []
                    
                    # Add-only sync: updates existing users from CSV, no removals
                    if (
                        existing_user.team_ids != team_ids
                        or existing_user.role != role
                        or existing_user.name != name
                        or (existing_user.email or "") != email
                        or existing_user.source != "resources_csv"
                    ):
                        self.user_service.update_user(
                            existing_user.id,
                            UserUpdate(
                                name=name,
                                email=email,
                                role=role,
                                team_ids=team_ids,
                                source="resources_csv"
                            )
                        )
                        updated += 1
                    
                else:
                    # New user: create
                    team_ids = [team] if team else []
                    
                    # Generate default password
                    default_password = AuthService.generate_default_password()
                    
                    user_create = UserCreate(
                        sapid=sapid,
                        name=name,
                        email=email,
                        role=role,
                        team_ids=team_ids,
                        password=default_password,
                        source="resources_csv"
                    )
                    
                    self.user_service.create_user(user_create)
                    created += 1
            
            except Exception as e:
                error_msg = f"Row {idx}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Second pass: build managed_user_ids from manager relationships
        try:
            manager_to_reports = self._build_manager_relationships(df)
            for manager_id, report_ids in manager_to_reports.items():
                manager_user = self.user_service.get_user_by_id(manager_id)
                if not manager_user:
                    continue

                current_reports = sorted(manager_user.managed_user_ids or [])
                if current_reports != report_ids:
                    new_role = manager_user.role
                    if manager_user.role == "User" and report_ids:
                        new_role = "Lead"

                    self.user_service.update_user(
                        manager_id,
                        UserUpdate(
                            role=new_role,
                            managed_user_ids=report_ids
                        )
                    )
                    updated += 1
        except Exception as e:
            relationship_error = f"Manager relationship sync failed: {str(e)}"
            logger.error(relationship_error)
            errors.append(relationship_error)
        
        logger.info(
            f"User sync completed: created={created}, updated={updated}, "
            f"errors={len(errors)}"
        )
        
        return {
            "created": created,
            "updated": updated,
            "errors": errors
        }
