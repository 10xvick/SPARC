"""
Authentication routes (login, refresh token, change password).
"""
from fastapi import APIRouter, HTTPException, Depends, status, Request
from datetime import timedelta
import logging

from app.models.user import (
    LoginRequest, TokenResponse, RefreshTokenRequest, 
    UserPasswordChange, TokenData, UserResponse
)
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.services.role_service import RoleService
from app.services import AuditTrailService
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Service instances (will be injected via dependencies)
user_service = UserService()
auth_service = AuthService()
role_service = RoleService()
audit_trail_service = AuditTrailService()


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, http_request: Request):
    """
    Login endpoint
    
    Args:
        request: Login credentials (sapid + password)
    
    Returns:
        Token response with access_token, refresh_token, and user info
    """
    # Get user by SAPID
    user = user_service.get_user_by_sapid(request.sapid)
    if not user:
        audit_trail_service.record_login_event(
            sapid=request.sapid,
            success=False,
            failure_reason="user_not_found",
            ip_address=http_request.client.host if http_request.client else None,
            user_agent=http_request.headers.get("user-agent"),
        )
        logger.warning(f"Login failed: user not found - {request.sapid}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Verify password
    if not auth_service.verify_password(request.password, user.password_hash or ""):
        audit_trail_service.record_login_event(
            sapid=request.sapid,
            user_id=user.id,
            user_name=user.name,
            role=user.role,
            success=False,
            failure_reason="invalid_password",
            ip_address=http_request.client.host if http_request.client else None,
            user_agent=http_request.headers.get("user-agent"),
        )
        logger.warning(f"Login failed: invalid password - {request.sapid}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Check if user is active
    if not user.is_active:
        audit_trail_service.record_login_event(
            sapid=request.sapid,
            user_id=user.id,
            user_name=user.name,
            role=user.role,
            success=False,
            failure_reason="user_inactive",
            ip_address=http_request.client.host if http_request.client else None,
            user_agent=http_request.headers.get("user-agent"),
        )
        logger.warning(f"Login failed: user inactive - {request.sapid}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive"
        )
    
    # Create token data
    permissions = role_service.get_permissions_for_role(user.role)
    token_data = TokenData(
        sub=str(user.id),
        sapid=user.sapid,
        name=user.name,
        role=user.role,
        team_ids=user.team_ids,
        managed_user_ids=user.managed_user_ids,
        permissions=permissions
    )
    
    # Generate tokens
    access_token = auth_service.create_access_token(token_data)
    refresh_token = auth_service.create_refresh_token(token_data)
    
    # Update last login
    user_service.update_last_login(user.id)

    audit_trail_service.record_login_event(
        sapid=user.sapid,
        user_id=user.id,
        user_name=user.name,
        role=user.role,
        success=True,
        ip_address=http_request.client.host if http_request.client else None,
        user_agent=http_request.headers.get("user-agent"),
    )
    
    logger.info(f"Login successful: {request.sapid}")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(
            id=user.id,
            sapid=user.sapid,
            name=user.name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            team_ids=user.team_ids,
            managed_user_ids=user.managed_user_ids,
            source=user.source,
            last_login=user.last_login,
            created_at=user.created_at,
            updated_at=user.updated_at
        ),
        permissions=permissions
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: RefreshTokenRequest):
    """
    Refresh token endpoint
    
    Args:
        request: Refresh token
    
    Returns:
        New token response
    """
    # Verify refresh token
    token_data = auth_service.verify_token(request.refresh_token)
    if not token_data:
        logger.warning("Refresh failed: invalid refresh token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Get updated user info
    user = user_service.get_user_by_id(token_data.user_id)
    if not user or not user.is_active:
        logger.warning(f"Refresh failed: user not found or inactive - {token_data.sapid}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new token data with current user info
    permissions = role_service.get_permissions_for_role(user.role)
    new_token_data = TokenData(
        sub=str(user.id),
        sapid=user.sapid,
        name=user.name,
        role=user.role,
        team_ids=user.team_ids,
        managed_user_ids=user.managed_user_ids,
        permissions=permissions
    )
    
    # Generate new tokens
    access_token = auth_service.create_access_token(new_token_data)
    refresh_token = auth_service.create_refresh_token(new_token_data)
    
    logger.info(f"Token refreshed: {user.sapid}")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(
            id=user.id,
            sapid=user.sapid,
            name=user.name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            team_ids=user.team_ids,
            managed_user_ids=user.managed_user_ids,
            source=user.source,
            last_login=user.last_login,
            created_at=user.created_at,
            updated_at=user.updated_at
        ),
        permissions=permissions
    )


@router.post("/change-password")
def change_password(
    request: UserPasswordChange,
    current_user = Depends(get_current_user)
):
    """
    Change user's own password
    
    Args:
        request: Current and new password
        current_user: Authenticated user
    
    Returns:
        Success message
    """
    user = user_service.get_user_by_id(current_user.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify current password
    if not auth_service.verify_password(request.current_password, user.password_hash or ""):
        logger.warning(f"Password change failed: invalid current password - {user.sapid}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is invalid"
        )
    
    # Update password
    if user_service.change_password(user.id, request.new_password):
        logger.info(f"Password changed: {user.sapid}")
        return {"message": "Password changed successfully"}
    
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to change password"
    )


@router.get("/me")
def get_current_user_info(current_user = Depends(get_current_user)):
    """
    Get current user info
    
    Args:
        current_user: Authenticated user
    
    Returns:
        Current user info
    """
    user = user_service.get_user_by_id(current_user.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user
