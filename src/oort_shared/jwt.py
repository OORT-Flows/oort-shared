from uuid import UUID

import jwt

from oort_shared.errors import TokenError
from oort_shared.schemas import TokenClaims

_REQUIRED_CLAIMS = ("sub", "email", "role", "iat", "exp")


def decode_token(token: str, secret: str, algorithm: str = "HS256") -> TokenClaims:
    """Decode and validate a Hub-issued JWT.

    Raises TokenError on signature failure, expiry, or missing required claims.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token") from exc

    for claim in _REQUIRED_CLAIMS:
        if claim not in payload:
            raise TokenError(f"Missing claim: {claim}")

    try:
        return TokenClaims(
            sub=UUID(payload["sub"]),
            email=payload["email"],
            full_name=payload.get("full_name"),
            tenant_id=UUID(payload["tenant_id"]) if payload.get("tenant_id") else None,
            tenant_slug=payload.get("tenant_slug"),
            role=payload["role"],
            group_ids=[UUID(g) for g in payload.get("group_ids", [])],
            product_access=list(payload.get("product_access", [])),
            iat=int(payload["iat"]),
            exp=int(payload["exp"]),
            jti=str(payload.get("jti", "")),
        )
    except (ValueError, TypeError) as exc:
        raise TokenError("Malformed claim") from exc
