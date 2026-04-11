from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class TokenClaims:
    sub: UUID
    email: str
    tenant_id: UUID | None
    tenant_slug: str | None
    role: str
    group_ids: list[UUID] = field(default_factory=list)
    product_access: list[str] = field(default_factory=list)
    iat: int = 0
    exp: int = 0
    jti: str = ""


@dataclass(frozen=True)
class OORTContext:
    user_id: UUID
    email: str
    tenant_id: UUID | None
    tenant_slug: str | None
    role: str
    group_ids: list[UUID]
    product_access: list[str]

    @classmethod
    def from_claims(cls, claims: TokenClaims) -> "OORTContext":
        return cls(
            user_id=claims.sub,
            email=claims.email,
            tenant_id=claims.tenant_id,
            tenant_slug=claims.tenant_slug,
            role=claims.role,
            group_ids=list(claims.group_ids),
            product_access=list(claims.product_access),
        )
