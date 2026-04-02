"""
auth/middleware.py — FastAPI dependency để extract và verify JWT từ request.

Dùng FastAPI Depends:
    from src.auth.middleware import require_auth
    @router.get("/protected")
    async def protected(user = Depends(require_auth)):
        ...

Phase 1: Auth optional (dev mode bỏ qua nếu APP_ENV=development).
"""

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.jwt import TokenPayload, verify_token
from src.config import settings

logger = structlog.get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> TokenPayload:
    """
    FastAPI dependency — extract Bearer token và verify.

    Development mode: nếu không có token và APP_ENV=development,
    trả về fake payload thay vì reject (tiện test local).
    """
    if credentials is None:
        if settings.is_development:
            logger.debug("Auth skipped in development mode")
            return TokenPayload(sub="dev-user", exp_bypass=True)  # type: ignore[call-arg]
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_token(credentials.credentials)
