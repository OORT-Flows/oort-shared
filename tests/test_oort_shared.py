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
    has_role,
    has_role_in_product,
    is_super_admin,
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


def test_legacy_token_without_roles_mirrors_role():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret, role="tenant_admin")  # no `roles` claim
    ctx = OORTContext.from_claims(decode_token(token, secret))
    assert ctx.roles == ["tenant_admin"]


def test_legacy_super_admin_token_without_roles_yields_empty_list():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret, role="super_admin")  # no `roles` claim
    ctx = OORTContext.from_claims(decode_token(token, secret))
    assert ctx.roles == []


def test_new_token_with_roles_claim_uses_it_verbatim():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret, role="tenant_admin", roles=["Admin"])
    ctx = OORTContext.from_claims(decode_token(token, secret))
    assert ctx.roles == ["Admin"]
    assert has_role(ctx, "Admin") is True
    assert has_role(ctx, "User") is False


def test_per_product_role_membership():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret, roles=["Builder:flows"])
    ctx = OORTContext.from_claims(decode_token(token, secret))
    assert has_role_in_product(ctx, "Builder", "flows") is True
    assert has_role_in_product(ctx, "Builder", "assessment-ai") is False
    assert has_role(ctx, "Builder") is False


def test_session_id_absent_is_none():
    secret = os.environ["JWT_SECRET"]
    ctx = OORTContext.from_claims(decode_token(_make_token(secret), secret))
    assert ctx.session_id is None


def test_session_id_present_is_preserved():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret, session_id="sess-abc-123")
    ctx = OORTContext.from_claims(decode_token(token, secret))
    assert ctx.session_id == "sess-abc-123"


def test_department_absent_is_none():
    secret = os.environ["JWT_SECRET"]
    ctx = OORTContext.from_claims(decode_token(_make_token(secret), secret))
    assert ctx.department_id is None
    assert ctx.department_name is None


def test_department_present_is_preserved():
    secret = os.environ["JWT_SECRET"]
    dept_id = str(uuid4())
    token = _make_token(secret, department_id=dept_id, department_name="Engineering")
    ctx = OORTContext.from_claims(decode_token(token, secret))
    assert str(ctx.department_id) == dept_id
    assert ctx.department_name == "Engineering"


def test_is_super_admin_true_for_super_admin_role():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret, role="super_admin", roles=["Admin"])
    ctx = OORTContext.from_claims(decode_token(token, secret))
    assert is_super_admin(ctx) is True


def test_is_super_admin_false_for_non_super_admin_role():
    secret = os.environ["JWT_SECRET"]
    token = _make_token(secret, role="tenant_admin", roles=["Admin"])
    ctx = OORTContext.from_claims(decode_token(token, secret))
    assert is_super_admin(ctx) is False


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
