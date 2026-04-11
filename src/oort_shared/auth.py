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
