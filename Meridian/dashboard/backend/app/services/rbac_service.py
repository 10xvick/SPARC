"""
RBAC (Role-Based Access Control) service for permission checking.
"""
from typing import List, Optional
import logging

from app.services.role_service import RoleService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)


class RBACService:
    """RBAC permission checking service"""
    
    def __init__(self, role_service: RoleService, user_service: UserService):
        """
        Initialize RBAC service
        
        Args:
            role_service: RoleService instance
            user_service: UserService instance
        """
        self.role_service = role_service
        self.user_service = user_service
    
    def has_permission(self, role: str, permission: str) -> bool:
        """
        Check if role has permission
        
        Args:
            role: Role name
            permission: Permission string
        
        Returns:
            True if role has permission
        """
        return self.role_service.check_permission(role, permission)
    
    def has_any_permission(self, role: str, permissions: List[str]) -> bool:
        """
        Check if role has any of the permissions
        
        Args:
            role: Role name
            permissions: List of permission strings
        
        Returns:
            True if role has at least one permission
        """
        for permission in permissions:
            if self.has_permission(role, permission):
                return True
        return False
    
    def has_all_permissions(self, role: str, permissions: List[str]) -> bool:
        """
        Check if role has all permissions
        
        Args:
            role: Role name
            permissions: List of permission strings
        
        Returns:
            True if role has all permissions
        """
        for permission in permissions:
            if not self.has_permission(role, permission):
                return False
        return True
    
    def can_view_employee_dashboard(self, viewer_id: int, target_id: int) -> bool:
        """
        Check if viewer can view target employee's dashboard
        
        Rules:
        - User can view own dashboard
        - Team Manager can view team members' dashboards
        - Lead can view managed employees' dashboards
        - Admin can view anyone's dashboard
        
        Args:
            viewer_id: Viewer user ID
            target_id: Target user ID
        
        Returns:
            True if viewer can access dashboard
        """
        # Admin and Admin Viewer can view anyone
        viewer = self.user_service.get_user_by_id(viewer_id)
        if not viewer:
            return False
        
        if viewer.role in ["Admin", "Admin Viewer", "API User"]:
            return True
        
        # Own dashboard
        if viewer_id == target_id:
            return True
        
        target = self.user_service.get_user_by_id(target_id)
        if not target:
            return False
        
        # Team Manager can view team members
        if viewer.role == "Team Manager":
            target_teams = set(target.team_ids or [])
            viewer_teams = set(viewer.team_ids or [])
            if target_teams & viewer_teams:  # Intersection (common teams)
                return True
        
        # Lead can view managed employees
        if viewer.role == "Lead":
            if target_id in (viewer.managed_user_ids or []):
                return True
        
        return False
    
    def can_view_team_dashboard(self, user_id: int, team_id: str) -> bool:
        """
        Check if user can view team dashboard
        
        Args:
            user_id: User ID
            team_id: Team ID
        
        Returns:
            True if user can access team dashboard
        """
        user = self.user_service.get_user_by_id(user_id)
        if not user:
            return False
        
        # Admin and Admin Viewer can view any team
        if user.role in ["Admin", "Admin Viewer", "API User"]:
            return True
        
        # Team Manager/Lead can view their teams
        if user.role in ["Team Manager", "Lead"]:
            return team_id in (user.team_ids or [])
        
        return False
    
    def get_accessible_users(self, user_id: int) -> List[int]:
        """
        Get list of user IDs that this user can access
        
        Args:
            user_id: User ID
        
        Returns:
            List of accessible user IDs
        """
        user = self.user_service.get_user_by_id(user_id)
        if not user:
            return []
        
        # Admin and Admin Viewer can access all users
        if user.role in ["Admin", "Admin Viewer", "API User"]:
            return [u.id for u in self.user_service.get_all_users()]
        
        accessible = {user_id}  # Can always access self
        
        # Team Manager can access team members
        if user.role == "Team Manager":
            for other_user in self.user_service.get_all_users():
                user_teams = set(user.team_ids or [])
                other_teams = set(other_user.team_ids or [])
                if user_teams & other_teams:
                    accessible.add(other_user.id)
        
        # Lead can access managed employees
        if user.role == "Lead":
            accessible.update(user.managed_user_ids or [])
        
        return list(accessible)
