"""
Role service for managing roles and permissions.
"""
import os
from typing import Optional, List, Dict, Any
import logging
from pathlib import Path

from app.utils.json_handler import load_json_safe, save_json_atomic

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ROLE_PERMISSIONS_FILE = os.getenv(
    "TEAMSIGHT_ROLE_PERMISSIONS_FILE",
    str(PROJECT_ROOT / "data" / "role_permissions.json")
)

# Built-in roles that cannot be deleted
BUILT_IN_ROLES = {"User", "Team Manager", "Lead", "API User", "Admin", "Admin Viewer"}


class RoleService:
    """Role and permission management service"""
    
    def __init__(self):
        """Initialize with roles from JSON file"""
        self.roles_file = ROLE_PERMISSIONS_FILE
        self._reload_roles()
    
    def _reload_roles(self) -> None:
        """Reload roles from JSON file"""
        data = load_json_safe(
            self.roles_file,
            {"built_in_roles": {}, "custom_roles": {}}
        )
        self.roles_data = data
        logger.info(
            f"Loaded {len(self._get_custom_roles())} custom roles "
            f"and {len(self._get_built_in_roles())} built-in roles"
        )
    
    def _get_built_in_roles(self) -> Dict[str, List[str]]:
        """Get built-in roles"""
        return self.roles_data.get("built_in_roles", {})
    
    def _get_custom_roles(self) -> Dict[str, List[str]]:
        """Get custom roles"""
        return self.roles_data.get("custom_roles", {})
    
    def _save_roles(self) -> None:
        """Save roles to JSON file atomically"""
        save_json_atomic(self.roles_file, self.roles_data)
    
    def get_all_roles(self) -> Dict[str, Any]:
        """
        Get all roles (built-in and custom)
        
        Returns:
            Dict with 'built_in' and 'custom' roles
        """
        built_in = self._get_built_in_roles()
        custom = self._get_custom_roles()
        
        return {
            "built_in": [
                {"name": name, "permissions": perms, "is_built_in": True}
                for name, perms in built_in.items()
            ],
            "custom": [
                {"name": name, "permissions": perms["permissions"], "is_built_in": False}
                for name, perms in custom.items()
            ]
        }
    
    def get_role(self, role_name: str) -> Optional[Dict[str, Any]]:
        """Get role by name (built-in or custom)"""
        built_in = self._get_built_in_roles()
        if role_name in built_in:
            return {
                "name": role_name,
                "permissions": built_in[role_name],
                "is_built_in": True
            }
        
        custom = self._get_custom_roles()
        if role_name in custom:
            return {
                "name": role_name,
                "permissions": custom[role_name].get("permissions", []),
                "is_built_in": False
            }
        
        return None
    
    def get_permissions_for_role(self, role_name: str) -> List[str]:
        """Get permissions for a role"""
        built_in = self._get_built_in_roles()
        if role_name in built_in:
            return built_in[role_name]
        
        custom = self._get_custom_roles()
        if role_name in custom:
            return custom[role_name].get("permissions", [])
        
        return []
    
    def role_exists(self, role_name: str) -> bool:
        """Check if role exists (built-in or custom)"""
        built_in = self._get_built_in_roles()
        custom = self._get_custom_roles()
        return role_name in built_in or role_name in custom
    
    def create_custom_role(self, role_name: str, permissions: List[str]) -> bool:
        """
        Create new custom role
        
        Args:
            role_name: Role name
            permissions: List of permission strings
        
        Returns:
            True if created, False if already exists or is built-in
        """
        if role_name in BUILT_IN_ROLES:
            logger.warning(f"Cannot create custom role: {role_name} is built-in")
            return False
        
        custom = self._get_custom_roles()
        if role_name in custom:
            logger.warning(f"Custom role already exists: {role_name}")
            return False
        
        custom[role_name] = {"permissions": permissions}
        self._save_roles()
        logger.info(f"Created custom role: {role_name}")
        return True
    
    def update_custom_role(self, role_name: str, permissions: List[str]) -> bool:
        """
        Update custom role permissions
        
        Args:
            role_name: Role name
            permissions: New list of permission strings
        
        Returns:
            True if updated, False if not found or is built-in
        """
        if role_name in BUILT_IN_ROLES:
            logger.warning(f"Cannot update built-in role: {role_name}")
            return False
        
        custom = self._get_custom_roles()
        if role_name not in custom:
            logger.warning(f"Custom role not found: {role_name}")
            return False
        
        custom[role_name]["permissions"] = permissions
        self._save_roles()
        logger.info(f"Updated custom role: {role_name}")
        return True
    
    def delete_custom_role(self, role_name: str) -> bool:
        """
        Delete custom role
        
        Args:
            role_name: Role name
        
        Returns:
            True if deleted, False if not found, is built-in, or error
        """
        if role_name in BUILT_IN_ROLES:
            logger.warning(f"Cannot delete built-in role: {role_name}")
            return False
        
        custom = self._get_custom_roles()
        if role_name not in custom:
            logger.warning(f"Custom role not found: {role_name}")
            return False
        
        del custom[role_name]
        self._save_roles()
        logger.info(f"Deleted custom role: {role_name}")
        return True
    
    def check_permission(self, role_name: str, permission: str) -> bool:
        """
        Check if role has permission
        
        Args:
            role_name: Role name
            permission: Permission string
        
        Returns:
            True if role has permission
        """
        permissions = self.get_permissions_for_role(role_name)
        return permission in permissions
    
    def get_all_available_permissions(self) -> List[str]:
        """
        Get all available permissions across all roles
        
        Returns:
            List of unique permissions
        """
        all_perms = set()
        
        built_in = self._get_built_in_roles()
        for perms in built_in.values():
            all_perms.update(perms)
        
        custom = self._get_custom_roles()
        for role_data in custom.values():
            all_perms.update(role_data.get("permissions", []))
        
        return sorted(list(all_perms))
