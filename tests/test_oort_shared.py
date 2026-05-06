import os
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from oort_shared import (
    AccessDeniedError,
    OORTContext,
    TokenError,
    decode_token,
    get_oort_context,
    has_feature,
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


def test_decode_token_without_features_claim_defaults_empty():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret)  # no features in payload
    claims = decode_token(token, secret)
    assert claims.features == []


def test_decode_token_with_features_claim():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret, features=["flows:beta_canvas", "flows:export_v2"])
    claims = decode_token(token, secret)
    assert claims.features == ["flows:beta_canvas", "flows:export_v2"]


def test_has_feature_returns_expected_booleans():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret, features=["flows:beta_canvas"])
    ctx = OORTContext.from_claims(decode_token(token, secret))
    assert has_feature(ctx, "flows:beta_canvas") is True
    assert has_feature(ctx, "flows:other") is False


def test_has_feature_empty_features_always_false():
    secret = os.environ["JWT_SECRET"]
    ctx = OORTContext.from_claims(decode_token(_make_token(secret), secret))
    assert has_feature(ctx, "flows:beta_canvas") is False


def test_get_oort_context_carries_features():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret, features=["flows:beta_canvas"])

    app = FastAPI()

    @app.get("/me")
    def me(ctx: Annotated[OORTContext, Depends(get_oort_context)]) -> dict[str, list[str]]:
        return {"features": ctx.features}

    with TestClient(app) as client:
        response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"features": ["flows:beta_canvas"]}
