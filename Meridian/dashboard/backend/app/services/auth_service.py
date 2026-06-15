"""
Authentication service for password hashing, JWT generation, and verification.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets
import string
import logging
import hashlib
import hmac

from jose import jwt as jose_jwt, JWTError
from app.models.user import TokenData

logger = logging.getLogger(__name__)

# Password hashing settings (PBKDF2-SHA256)
PBKDF2_ITERATIONS = int(os.getenv("TEAMSIGHT_PASSWORD_ITERATIONS", "390000"))

# JWT settings
SECRET_KEY = os.getenv("TEAMSIGHT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("TEAMSIGHT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("TEAMSIGHT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))


class AuthService:
    """Authentication service"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using PBKDF2-SHA256."""
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            PBKDF2_ITERATIONS
        )
        return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password against PBKDF2-SHA256 hash."""
        if not hashed_password:
            return False

        if not hashed_password.startswith("pbkdf2_sha256$"):
            return False

        try:
            _, iterations_str, salt, expected_hex = hashed_password.split("$", 3)
            iterations = int(iterations_str)
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt.encode("utf-8"),
                iterations
            ).hex()
            return hmac.compare_digest(actual, expected_hex)
        except Exception:
            return False
    
    @staticmethod
    def generate_default_password() -> str:
        """Generate 8-character default password (alphanumeric)"""
        chars = string.ascii_letters + string.digits
        return ''.join(secrets.choice(chars) for _ in range(8))
    
    @staticmethod
    def create_access_token(
        token_data: TokenData,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create JWT access token
        
        Args:
            token_data: Token payload
            expires_delta: Token expiry duration
        
        Returns:
            JWT token string
        """
        to_encode = token_data.model_dump()
        
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=ACCESS_TOKEN_EXPIRE_MINUTES
            )
        
        to_encode.update({"exp": expire})
        encoded_jwt = jose_jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(
        token_data: TokenData,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create JWT refresh token
        
        Args:
            token_data: Token payload
            expires_delta: Token expiry duration
        
        Returns:
            JWT token string
        """
        to_encode = token_data.model_dump()
        
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                days=REFRESH_TOKEN_EXPIRE_DAYS
            )
        
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jose_jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> Optional[TokenData]:
        """
        Verify and decode JWT token
        
        Args:
            token: JWT token string
        
        Returns:
            TokenData if valid, None if invalid
        """
        try:
            payload = jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            token_data = TokenData(**payload)
            return token_data
        except JWTError as e:
            logger.warning(f"Invalid or expired token: {e}")
            return None
