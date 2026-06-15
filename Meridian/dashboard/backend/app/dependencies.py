"""
FastAPI dependencies for authentication and authorization.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

from app.services.auth_service import AuthService
from app.models.user import TokenData

logger = logging.getLogger(__name__)

security = HTTPBearer()
auth_service = AuthService()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    """
    Get current authenticated user from JWT token
    
    Args:
        credentials: HTTP Bearer token
    
    Returns:
        TokenData with user info
    
    Raises:
        HTTPException if token is invalid or expired
    """
    token = credentials.credentials
    
    # Verify token
    token_data = auth_service.verify_token(token)
    if not token_data:
        logger.warning("Invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return token_data


def require_role(*allowed_roles: str):
    """
    Dependency for requiring specific roles
    
    Args:
        allowed_roles: List of allowed role names
    
    Returns:
        Dependency function
    """
    async def check_role(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if current_user.role not in allowed_roles:
            logger.warning(
                f"Role check failed: {current_user.role} not in {allowed_roles} "
                f"for user {current_user.sapid}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    
    return check_role


def require_permission(permission: str):
    """
    Dependency for requiring specific permission
    
    Args:
        permission: Permission string to check
    
    Returns:
        Dependency function
    """
    async def check_permission(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        from app.services.role_service import RoleService
        
        role_service = RoleService()
        if not role_service.check_permission(current_user.role, permission):
            logger.warning(
                f"Permission check failed: {current_user.role} missing {permission} "
                f"for user {current_user.sapid}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    
    return check_permission


def require_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """
    Dependency for requiring Admin or API User role.
    API User is granted admin-equivalent API permissions for now.
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        TokenData if user is Admin or API User
    
    Raises:
        HTTPException if user is neither Admin nor API User
    """
    if current_user.role not in ["Admin", "API User"]:
        logger.warning(f"Admin/API access check failed for user {current_user.sapid}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def require_admin_or_read_api(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """
    Dependency for admin-level read access to resource data.
    
    Allowed:
    - Admin role
    - API User role  
    - Any role with 'api:read_all' permission
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        TokenData if user has required permission
    
    Raises:
        HTTPException if user lacks required permission
    """
    if current_user.role in ["Admin", "API User"]:
        return current_user
    
    from app.services.role_service import RoleService
    
    role_service = RoleService()
    if role_service.check_permission(current_user.role, "api:read_all"):
        return current_user
    
    logger.warning(f"Admin/read-API access check failed for user {current_user.sapid} role={current_user.role}")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin or read-only API access required"
    )


def require_report_access(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """
    Dependency for report access.

    Allowed roles: Team Manager, Lead, Admin, API User.
    Also allows any role that has view:reports or view:all_dashboards permission.
    """
    if current_user.role in ["Team Manager", "Lead", "Admin", "API User"]:
        return current_user

    from app.services.role_service import RoleService

    role_service = RoleService()
    if role_service.check_permission(current_user.role, "view:reports") or role_service.check_permission(current_user.role, "view:all_dashboards"):
        return current_user

    logger.warning(f"Report access denied for user {current_user.sapid} role={current_user.role}")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Report access not permitted for this role"
    )
    return current_user
