"""
User service for managing users JSON file and operations.
"""
import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging
from pathlib import Path

from app.utils.json_handler import load_json_safe, save_json_atomic, get_next_id
from app.models.user import User, UserCreate, UserUpdate
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
USERS_FILE = os.getenv("TEAMSIGHT_USERS_FILE", str(PROJECT_ROOT / "data" / "users.json"))


class UserService:
    """User management service"""
    
    def __init__(self):
        """Initialize with users from JSON file"""
        self.users_file = USERS_FILE
        self._reload_users()
    
    def _reload_users(self) -> None:
        """Reload users from JSON file"""
        data = load_json_safe(self.users_file, {"users": []})
        self.users_data = data
        logger.info(f"Loaded {len(self._get_users_list())} users from {self.users_file}")
    
    def _get_users_list(self) -> List[Dict[str, Any]]:
        """Get users list from data"""
        return self.users_data.get("users", [])
    
    def _save_users(self) -> None:
        """Save users to JSON file atomically"""
        save_json_atomic(self.users_file, self.users_data)
    
    def get_all_users(self, active_only: bool = False) -> List[User]:
        """
        Get all users
        
        Args:
            active_only: If True, only return active users
        
        Returns:
            List of User objects
        """
        self._reload_users()
        users = []
        for user_data in self._get_users_list():
            if active_only and not user_data.get("is_active", True):
                continue
            users.append(User(**user_data))
        return users
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        self._reload_users()
        for user_data in self._get_users_list():
            if user_data.get("id") == user_id:
                return User(**user_data)
        return None
    
    def get_user_by_sapid(self, sapid: str) -> Optional[User]:
        """Get user by SAPID"""
        self._reload_users()
        for user_data in self._get_users_list():
            if user_data.get("sapid") == sapid:
                return User(**user_data)
        return None

    def get_user_by_name(self, name: str) -> Optional[User]:
        """Get user by name (case-insensitive exact match)"""
        self._reload_users()
        target_name = name.strip().lower()
        for user_data in self._get_users_list():
            current_name = str(user_data.get("name", "")).strip().lower()
            if current_name == target_name:
                return User(**user_data)
        return None
    
    def create_user(self, user_create: UserCreate) -> User:
        """
        Create new user
        
        Args:
            user_create: User creation data
        
        Returns:
            Created user
        """
        self._reload_users()
        # Check if user already exists
        existing = self.get_user_by_sapid(user_create.sapid)
        if existing:
            raise ValueError(f"User with SAPID {user_create.sapid} already exists")
        
        users_list = self._get_users_list()
        new_id = get_next_id(users_list)
        now = datetime.now(timezone.utc)
        
        user_data = {
            "id": new_id,
            "sapid": user_create.sapid,
            "name": user_create.name,
            "email": user_create.email,
            "role": user_create.role,
            "password_hash": AuthService.hash_password(user_create.password),
            "is_active": user_create.is_active,
            "team_ids": user_create.team_ids,
            "managed_user_ids": user_create.managed_user_ids,
            "source": user_create.source,
            "last_login": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }
        
        users_list.append(user_data)
        self._save_users()
        logger.info(f"Created user: {user_create.sapid}")
        
        return User(**user_data)
    
    def update_user(self, user_id: int, user_update: UserUpdate) -> Optional[User]:
        """
        Update user
        
        Args:
            user_id: User ID
            user_update: Update data
        
        Returns:
            Updated user or None if not found
        """
        self._reload_users()
        users_list = self._get_users_list()
        now = datetime.now(timezone.utc)
        
        for user_data in users_list:
            if user_data.get("id") == user_id:
                # Update fields if provided
                if user_update.name is not None:
                    user_data["name"] = user_update.name
                if user_update.email is not None:
                    user_data["email"] = user_update.email
                if user_update.role is not None:
                    user_data["role"] = user_update.role
                if user_update.is_active is not None:
                    user_data["is_active"] = user_update.is_active
                if user_update.team_ids is not None:
                    user_data["team_ids"] = user_update.team_ids
                if user_update.managed_user_ids is not None:
                    user_data["managed_user_ids"] = user_update.managed_user_ids
                if user_update.source is not None:
                    user_data["source"] = user_update.source
                
                user_data["updated_at"] = now.isoformat()
                self._save_users()
                logger.info(f"Updated user: {user_id}")
                return User(**user_data)
        
        return None
    
    def delete_user(self, user_id: int) -> bool:
        """
        Delete user
        
        Args:
            user_id: User ID
        
        Returns:
            True if deleted, False if not found
        """
        self._reload_users()
        users_list = self._get_users_list()
        original_len = len(users_list)

        # Remove target user references from all manager assignment lists first.
        for user_data in users_list:
            managed = user_data.get("managed_user_ids", [])
            if isinstance(managed, list) and user_id in managed:
                user_data["managed_user_ids"] = [uid for uid in managed if uid != user_id]
                user_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        self.users_data["users"] = [
            u for u in users_list if u.get("id") != user_id
        ]
        
        if len(self.users_data["users"]) < original_len:
            self._save_users()
            logger.info(f"Deleted user: {user_id}")
            return True
        
        return False

    def delete_user_by_sapid(self, sapid: str) -> bool:
        """Delete RBAC user by SAPID, if present."""
        user = self.get_user_by_sapid(str(sapid))
        if not user:
            return False
        return self.delete_user(user.id)
    
    def change_password(self, user_id: int, new_password: str) -> bool:
        """
        Change user password
        
        Args:
            user_id: User ID
            new_password: New password
        
        Returns:
            True if changed, False if not found
        """
        self._reload_users()
        users_list = self._get_users_list()
        now = datetime.now(timezone.utc)
        
        for user_data in users_list:
            if user_data.get("id") == user_id:
                user_data["password_hash"] = AuthService.hash_password(new_password)
                user_data["updated_at"] = now.isoformat()
                self._save_users()
                logger.info(f"Changed password for user: {user_id}")
                return True
        
        return False
    
    def update_last_login(self, user_id: int) -> bool:
        """
        Update user's last login timestamp
        
        Args:
            user_id: User ID
        
        Returns:
            True if updated, False if not found
        """
        self._reload_users()
        users_list = self._get_users_list()
        now = datetime.now(timezone.utc)
        
        for user_data in users_list:
            if user_data.get("id") == user_id:
                user_data["last_login"] = now.isoformat()
                self._save_users()
                return True
        
        return False
    
    def reset_password(self, user_id: int) -> Optional[str]:
        """
        Reset user password to new default
        
        Args:
            user_id: User ID
        
        Returns:
            New password if successful, None if user not found
        """
        new_password = AuthService.generate_default_password()
        if self.change_password(user_id, new_password):
            logger.info(f"Reset password for user: {user_id}")
            return new_password
        return None
