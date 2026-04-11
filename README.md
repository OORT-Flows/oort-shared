# oort-shared

The shared Python library every OORT product uses to validate Hub-issued JWTs and read identity context. **The only sanctioned way for a product to authenticate a Hub user.**

> **Why this exists.** OORT products (OORT Flows, OORT Assessment, OORT Analytics, …) live in **separate repos** with their **own databases**. They do not own users, groups, passwords, or token signing — the Hub does. A product receives a signed JWT from the Hub and must validate it locally on every request, with zero network calls back to the Hub. `oort-shared` is the canonical implementation of that validation. If you find yourself writing `jwt.decode(...)` by hand inside a product, stop and use this library instead.

---

## Install

`oort-shared` is distributed as a **git-pinned dependency** — no PyPI, no Azure Artifacts, no monorepo path source. Pin a tag in your product's `pyproject.toml`:

```toml
[project]
dependencies = [
    "oort-shared @ git+ssh://git@github.com/oort-labs/oort-shared.git@v0.1.0",
]
```

Then:

```bash
uv lock     # freezes the resolved commit SHA into uv.lock
uv sync
```

`uv.lock` is committed, so CI builds resolve to the exact same commit byte-for-byte.

### Auth

CI pulls via an SSH deploy key attached to the `oort-shared` repo. Developers use their own SSH keys. There is no package registry.

### Local hacking

When you need to iterate on `oort-shared` itself from inside a product, clone it as a sibling directory and override the git source temporarily:

```bash
uv add --editable ../oort-shared
```

**Revert before committing.** The committed `pyproject.toml` must always point at a git tag, never a local path — otherwise CI breaks for everyone else.

---

## What it gives you

```python
from oort_shared import (
    decode_token,           # raw decode → TokenClaims
    require_product_access, # raises AccessDeniedError if slug missing
    get_oort_context,       # FastAPI Depends() → OORTContext
    OORTContext,            # typed context: user_id, tenant_id, role, group_ids, product_access
    TokenClaims,            # raw claims dataclass
    TokenError,             # signature / expiry / malformed failures
    AccessDeniedError,      # product_slug not in claims.product_access
)
```

### `decode_token(token, secret, algorithm="HS256") -> TokenClaims`

Validates signature, expiry, and required claims (`sub`, `email`, `role`, `iat`, `exp`). Raises `TokenError` on any failure with a generic message — never leaks why validation failed.

### `require_product_access(claims, product_slug) -> None`

Raises `AccessDeniedError` if `product_slug` is not in `claims.product_access`. No-op on success.

### `get_oort_context` — FastAPI dependency

Reads a `Bearer` token from the `Authorization` header, decodes it via `JWT_SECRET` from the environment, and returns a typed `OORTContext`. Raises `HTTPException(401)` on any failure.

```python
from typing import Annotated
from fastapi import Depends
from oort_shared import OORTContext, get_oort_context

OORTCtx = Annotated[OORTContext, Depends(get_oort_context)]

@router.get("/workflows")
async def list_workflows(ctx: OORTCtx):
    return await repo.list_by_tenant(db, ctx.tenant_id)
```

---

## The product-side wrapper you should write

Don't call `get_oort_context` directly from routes — wrap it once per product so the product slug check is enforced consistently:

```python
# app/core/dependencies.py
from typing import Annotated
from fastapi import Depends, HTTPException, status
from oort_shared import OORTContext, get_oort_context
from app.core.config import settings


def product_context(
    ctx: Annotated[OORTContext, Depends(get_oort_context)],
) -> OORTContext:
    if settings.PRODUCT_SLUG not in ctx.product_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this product",
        )
    return ctx


ProductCtx = Annotated[OORTContext, Depends(product_context)]
```

Now every protected route is one annotation away from being correctly authenticated **and** authorized for this product.

---

## Environment variables consumed

| Variable | Required | Default | Notes |
|---|---|---|---|
| `JWT_SECRET` | yes | — | Must match the Hub's signing secret exactly. In production, sourced from Azure Key Vault via Managed Identity. |
| `JWT_ALGORITHM` | no | `HS256` | Will gain `RS256` support during a future migration; both will be accepted during the transition. |

If `JWT_SECRET` is missing, `get_oort_context` raises `HTTPException(500, "Server misconfigured")`. **Never** transport tokens in URL query params — only `Authorization: Bearer` headers or HttpOnly cookies forwarded to the header.

---

## Versioning & releases

`oort-shared` follows **semantic versioning** and every tag documents the JWT contract it expects:

- **Patch** (`v0.1.0` → `v0.1.1`) — bug fixes, no contract changes. Safe to bump anywhere.
- **Minor** (`v0.1.x` → `v0.2.0`) — new optional claim, new helper. Old products keep working; new products opt in.
- **Major** (`v0.x` → `v1.0`) — breaking change to the JWT contract or public API. Coordinated rollout across the Hub and every product.

Cutting a release:

1. Update `CHANGELOG.md` with what changed (especially any new/changed claims).
2. Bump `version` in `pyproject.toml`.
3. `git tag vX.Y.Z && git push --tags`.
4. Bump the `@vX.Y.Z` suffix in each consumer's `pyproject.toml`, run `uv lock`, open a PR.

The Hub itself consumes `oort-shared` the same way every other product does — there is no special path.

---

## Anti-patterns

| ❌ Don't | ✅ Do |
|---|---|
| `jwt.decode(...)` directly inside a product router | `get_oort_context` / `decode_token` from `oort_shared` |
| Accept `tenant_id` from a query param or request body | Read `ctx.tenant_id` from the decoded JWT only |
| Catch `TokenError` and return its message verbatim | Return a generic 401 — never leak validation reasons |
| Cache decoded claims in Redis "for performance" | There is nothing to cache — validation is a local HMAC check |
| Vendor the file into your product's source tree | Pin a git tag and let `uv lock` reproduce the build |
| Commit a local-path `[tool.uv.sources]` override | Revert the override before pushing |

---

## Development

```bash
uv sync                       # install runtime + dev deps
uv run pytest                 # run tests
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy oort_shared       # type-check
```

Tests live under `tests/` and use `pytest` + `pytest-asyncio`. Every public function in `oort_shared/` must have at least one happy-path and one error-path test. PRs that change the JWT contract must update the corresponding tests in the same commit.

---

## Layout

```
oort_shared/
├── __init__.py     # public re-exports
├── jwt.py          # decode_token()
├── auth.py         # require_product_access(), get_oort_context()
├── schemas.py      # OORTContext, TokenClaims
└── errors.py       # TokenError, AccessDeniedError
```

Keep the surface area small. New helpers should be justified by **at least two** consuming products — otherwise they belong in the product, not here.
