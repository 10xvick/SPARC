"""
User, Role, and Permission models for RBAC system.
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


# ==================== Permission Models ====================

class Permission(BaseModel):
    """Single permission string (e.g., 'view:employee_dashboard')"""
    name: str


class RolePermissions(BaseModel):
    """Permissions for a role"""
    permissions: List[str] = Field(default_factory=list)


# ==================== Role Models ====================

class RoleBase(BaseModel):
    """Base role data"""
    name: str
    permissions: List[str] = Field(default_factory=list)


class Role(RoleBase):
    """Full role data"""
    pass


class RoleCreate(RoleBase):
    """Create role request"""
    pass


class RoleUpdate(BaseModel):
    """Update role request"""
    permissions: List[str] = Field(default_factory=list)


# ==================== User Models ====================

class UserBase(BaseModel):
    """Base user data"""
    sapid: str
    name: str
    email: Optional[str] = None
    role: str
    is_active: bool = True
    team_ids: List[str] = Field(default_factory=list)
    managed_user_ids: List[int] = Field(default_factory=list)
    source: str = "manual"  # manual | resources_csv


class User(UserBase):
    """Full user data (from JSON)"""
    id: int
    password_hash: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserCreate(UserBase):
    """Create user request (password provided separately)"""
    password: str


class UserUpdate(BaseModel):
    """Update user request"""
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    team_ids: Optional[List[str]] = None
    managed_user_ids: Optional[List[int]] = None
    source: Optional[str] = None


class UserPasswordChange(BaseModel):
    """Change password request"""
    current_password: str
    new_password: str


class UserPasswordReset(BaseModel):
    """Reset password response (returns new password and user email)"""
    new_password: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    user_sapid: Optional[str] = None
    email_notification_status: Optional[str] = None
    email_notification_message: Optional[str] = None


# ==================== API Response Models ====================

class UserResponse(BaseModel):
    """User response for API (no password hash)"""
    id: int
    sapid: str
    name: str
    email: Optional[str]
    role: str
    is_active: bool
    team_ids: List[str]
    managed_user_ids: List[int]
    source: str
    last_login: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class UserCreateResponse(BaseModel):
    """Create user response with optional email notification status."""
    user: UserResponse
    email_notification_status: Optional[str] = None
    email_notification_message: Optional[str] = None


# ==================== Auth Models ====================

class LoginRequest(BaseModel):
    """Login request"""
    sapid: str
    password: str


class TokenResponse(BaseModel):
    """Token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
    permissions: List[str] = Field(default_factory=list)


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str


class TokenData(BaseModel):
    """JWT token payload data"""
    sub: str  # user_id as string (JWT standard)
    sapid: str
    name: str
    role: str
    team_ids: List[str] = Field(default_factory=list)
    managed_user_ids: List[int] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)

    @property
    def user_id(self) -> int:
        """Convenience property to read user ID as int."""
        return int(self.sub)


class RoleResponse(BaseModel):
    """Role response for API"""
    name: str
    permissions: List[str]
    is_built_in: bool = False


class SyncResponse(BaseModel):
    """CSV sync response"""
    created: int
    updated: int
    errors: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Auth system health response"""
    status: str
    users_loaded: int
    roles_loaded: int
