import os
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from oort_shared.errors import AccessDeniedError, TokenError
from oort_shared.jwt import decode_token
from oort_shared.schemas import OORTContext, TokenClaims

_bearer = HTTPBearer(auto_error=False)


def require_product_access(claims: TokenClaims, product_slug: str) -> None:
    if product_slug not in claims.product_access:
        raise AccessDeniedError(f"No access to product '{product_slug}'")


def has_feature(ctx: OORTContext, key: str) -> bool:
    """Return True if `key` (format ``<product_slug>:<flag>``) is enabled on the token."""
    return key in ctx.features


def has_role(ctx: OORTContext, name: str) -> bool:
    """Return True if `name` is present in ctx.roles as a tenant-wide role."""
    return name in ctx.roles


def has_role_in_product(ctx: OORTContext, name: str, product_slug: str) -> bool:
    """Return True if `<name>:<product_slug>` is present in ctx.roles."""
    return f"{name}:{product_slug}" in ctx.roles


def is_super_admin(ctx: OORTContext) -> bool:
    """Return True if the token represents a super admin (global flag, never in `roles`)."""
    return ctx.role == "super_admin"


def get_oort_context(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> OORTContext:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Server misconfigured")
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_token(
            creds.credentials,
            secret,
            algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
        )
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return OORTContext.from_claims(claims)
