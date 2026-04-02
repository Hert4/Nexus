"""Tests cho auth module."""

import pytest
from datetime import UTC, datetime, timedelta


class TestJWT:
    def test_create_and_verify_token(self):
        from src.auth.jwt import create_token, verify_token
        token = create_token("user123")
        payload = verify_token(token)
        assert payload.sub == "user123"

    def test_invalid_token_raises_401(self):
        from fastapi import HTTPException
        from src.auth.jwt import verify_token
        with pytest.raises(HTTPException) as exc_info:
            verify_token("invalid.token.here")
        assert exc_info.value.status_code == 401

    def test_expired_token_raises_401(self):
        from fastapi import HTTPException
        from jose import jwt
        from src.config import settings
        from src.auth.jwt import verify_token

        expired_payload = {
            "sub": "user123",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        }
        token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)
        assert exc_info.value.status_code == 401
