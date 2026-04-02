"""
auth/jwt.py — JWT token creation và verification.

Dùng python-jose để sign/verify HS256 JWT tokens.
Secret lấy từ env var JWT_SECRET.

Usage:
    from src.auth.jwt import create_token, verify_token
    token = create_token({"sub": "user123"})
    payload = verify_token(token)  # raises HTTPException nếu invalid
"""

from datetime import UTC, datetime, timedelta

import structlog
from fastapi import HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel

from src.config import settings

logger = structlog.get_logger(__name__)


class TokenPayload(BaseModel):
    sub: str  # user id hoặc username
    exp: datetime


def create_token(subject: str) -> str:
    """Tạo JWT token cho subject (user id)."""
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> TokenPayload:
    """
    Verify JWT token và trả về payload.
    Raise HTTP 401 nếu token invalid hoặc expired.
    """
    try:
        raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return TokenPayload(**raw)
    except JWTError as e:
        logger.warning("JWT verification failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
