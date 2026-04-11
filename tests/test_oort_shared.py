import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from oort_shared import (
    AccessDeniedError,
    TokenError,
    decode_token,
    require_product_access,
)


def _make_token(secret: str, **overrides) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid4()),
        "email": "user@test.com",
        "role": "member",
        "tenant_id": str(uuid4()),
        "tenant_slug": "acme",
        "group_ids": [],
        "product_access": ["prod_a"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "jti": str(uuid4()),
    }
    payload.update(overrides)
    return jwt.encode(payload, secret, algorithm="HS256")


def test_decode_valid_token():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret)
    claims = decode_token(token, secret)
    assert claims.email == "user@test.com"
    assert claims.product_access == ["prod_a"]


def test_decode_expired_token_raises():
    secret = os.environ["JWT_SECRET"]
    expired = _make_token(
        secret,
        iat=int((datetime.now(UTC) - timedelta(hours=2)).timestamp()),
        exp=int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
    )
    with pytest.raises(TokenError):
        decode_token(expired, secret)


def test_decode_bad_signature_raises():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret)
    with pytest.raises(TokenError):
        decode_token(token, "different-secret-also-32-chars-x")


def test_require_product_access_success():
    secret = os.environ["JWT_SECRET"]
    claims = decode_token(_make_token(secret), secret)
    require_product_access(claims, "prod_a")


def test_require_product_access_denied():
    secret = os.environ["JWT_SECRET"]
    claims = decode_token(_make_token(secret), secret)
    with pytest.raises(AccessDeniedError):
        require_product_access(claims, "missing")
