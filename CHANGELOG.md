# Changelog

All notable changes to `oort-shared` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **JWT contract changes** must be called out explicitly in every release — adding, removing, renaming, or retyping a claim is the most load-bearing thing this library does. If a release does not change the JWT contract, say so explicitly under the version heading.

## [Unreleased]

## [0.5.0] — 2026-05-22

### Added
- `department_id` claim on `TokenClaims` and `OORTContext` (`UUID | None`, default `None`). Mirrors the HUB-emitted department the user belongs to.
- `department_name` claim on `TokenClaims` and `OORTContext` (`str | None`, default `None`). Human-readable name of the department referenced by `department_id`.

### JWT contract change
- New optional claim `department_id` (string UUID). Decoded to `UUID`; absent or falsy value yields `None`.
- New optional claim `department_name` (string). Absent value yields `None`.
- Both are paired the same way as `tenant_id` / `tenant_slug`. HUB emits them together; tokens issued before this release omit them and decode cleanly to `None`.
- The legacy `role` claim removal previously slated for `0.5.0` is **deferred to `0.6.0`** — `role` remains required and unchanged in `0.5.x`.

## [0.4.0] — 2026-05-13

### Added
- `roles` claim on `TokenClaims` and `OORTContext` (`list[str]`, default `[]`). Entries are either bare tenant-wide role names (`"Admin"`, `"User"`, `"FinOps Manager"`, `"Department Manager"`, `"Service Account"`) or per-product roles in the form `"<role>:<product_slug>"` (`"Builder:flows"`, `"Reviewer:assessment-ai"`). `super_admin` is **never** in this list — it remains a global flag on the legacy `role` claim.
- `session_id` claim on `TokenClaims` and `OORTContext` (`str | None`, default `None`). Correlates the token with the HUB `sessions` table row.
- `has_role(ctx, name)` — exact tenant-wide membership check against `ctx.roles`.
- `has_role_in_product(ctx, name, product_slug)` — checks `f"{name}:{product_slug}"` membership in `ctx.roles`.
- `is_super_admin(ctx)` — returns `ctx.role == "super_admin"`. Does **not** inspect `ctx.roles`; super-admin is intentionally outside the list.
- Re-exports `has_role`, `has_role_in_product`, `is_super_admin` from the package root.

### Deprecated
- `role: str` on `TokenClaims` / `OORTContext`. HUB still emits it during the transition window and the decoder still requires it, so existing code keeps working unchanged. Removal is planned for `0.5.0` once leaf products have migrated to `roles` + `is_super_admin`.

### JWT contract change
- New optional claim `roles` (list of strings). Format:
  - Tenant-wide role: bare name, e.g. `"Admin"`, `"User"`, `"FinOps Manager"`.
  - Per-product role: `"<role>:<product_slug>"`, e.g. `"Builder:flows"`, `"Reviewer:assessment-ai"`.
  - `super_admin` is **never** included; it lives only on the legacy `role` claim.
- New optional claim `session_id` (string). Correlates with the HUB `sessions` row.
- `role` claim remains **required** for `0.4.x`. HUB dual-emits `role` and `roles` during the transition; the decoder is tolerant of either:
  - If `roles` is present in the payload, it is used verbatim.
  - If `roles` is absent and `role == "super_admin"`, `ctx.roles` is `[]`.
  - If `roles` is absent and `role` is anything else, `ctx.roles` is `[role]`.
- Tokens minted by older HUB deployments (with only `role`, no `roles`, no `session_id`) continue to decode cleanly. This is the load-bearing compatibility guarantee for the transition.

## [0.3.1] — 2026-05-08

### Fixed
- `emit_usage_event` now sends the request body wrapped in the `{"events": [...]}` envelope expected by HUB's `POST /api/v1/usage/events` (`UsageEventBatchIn`). Previous releases (`0.2.0`, `0.3.0`) sent the events as a bare JSON list, which HUB rejected with `422 model_attributes_type` (`loc=["body"]`). Because the helper swallows non-2xx responses with a `logger.warning` and never raises, the bug was silent — every usage emission from leaf products has been failing since `0.2.0`. Bump to `v0.3.1` and check leaf-product logs for the warning to confirm.
- Test `test_emit_happy_path` was asserting the bug rather than the contract; now asserts the envelope shape.

### JWT contract change
- None.

## [0.3.0] — 2026-05-06

### Added
- `features` claim support on `TokenClaims` and `OORTContext` (`list[str]`, default `[]`). Each entry is `"<product_slug>:<key>"`. Older HUB tokens without the claim continue to decode cleanly with `features == []` — no breaking change.
- `has_feature(ctx: OORTContext, key: str) -> bool` — predicate that returns `key in ctx.features`. Standardizes the call site so leaf products don't reach into the list directly.
- Re-exports `has_feature` from the package root.

### JWT contract change
- New optional claim `features` (list of strings, format `"<product_slug>:<key>"`). The Hub must include it when encoding tokens for downstream products to read `OORTContext.features`. Absence of the claim is treated as an empty list, so older Hub deployments stay compatible.

## [0.2.0] — 2026-05-06

### Added
- `oort_shared.usage` module exposing the HUB usage-ingestion contract:
  - `UsageEvent` Pydantic model — mirrors one item in the `POST /api/v1/usage/events` request body. Fields: `event_type` (≤64 chars), `quantity` (Decimal 12,2), `unit` (≤32 chars), `occurred_at` (timezone-aware datetime), `tenant_id`, optional `user_id`, optional `idempotency_key`, free-form `metadata` dict.
  - `emit_usage_event(client, *, hub_url, service_token, events, local_buffer=None)` — async helper that POSTs the batch to `{hub_url}/api/v1/usage/events` with `Authorization: Bearer {service_token}`. Retries up to 3 attempts on network errors and 5xx responses with exponential backoff (0.2s → 0.6s base, ±20% jitter). 4xx responses are not retried. Never raises; on terminal failure logs a warning and, if `local_buffer` is supplied, hands the batch to it for persistence.
- Re-exports `UsageEvent` and `emit_usage_event` from the package root.

### Dependencies
- `httpx>=0.27.0` and `pydantic>=2.7.0` are now runtime dependencies (httpx was previously dev-only; pydantic was a transitive dep of fastapi). Leaf products typically already have both.

### JWT contract change
- None. `TokenClaims` and `OORTContext` are unchanged.

## [0.1.1] — 2026-04-13

### Added
- `full_name` optional claim on `TokenClaims` and `OORTContext`. Populated from the JWT `full_name` claim when present; `None` otherwise. Old tokens without the claim remain valid.

### JWT contract change
- New optional claim `full_name` (string). The Hub must include it when encoding tokens for downstream products to read `OORTContext.full_name`.

## [0.1.0] — 2026-04-11

Initial extraction from the `oort-hub` repo into a standalone package. This is the first release every OORT product will pin against.

### Added
- `decode_token(token, secret, algorithm="HS256")` — validates signature, expiry, and required claims; returns a typed `TokenClaims` dataclass.
- `require_product_access(claims, product_slug)` — raises `AccessDeniedError` if the slug is not present in `claims.product_access`.
- `get_oort_context` — FastAPI dependency that extracts a `Bearer` token from the `Authorization` header, decodes it via `JWT_SECRET` from the environment, and returns an `OORTContext`.
- `OORTContext` — frozen dataclass with `user_id`, `email`, `tenant_id`, `tenant_slug`, `role`, `group_ids`, `product_access`.
- `TokenClaims` — frozen dataclass mirroring the raw decoded JWT payload.
- `TokenError`, `AccessDeniedError` — narrow exception types so consumers can catch precisely.

### JWT contract (current — through v0.5.0)

| Claim | Type | Required | Since | Notes |
|---|---|---|---|---|
| `sub` | UUID string | yes | 0.1.0 | Hub user id |
| `email` | string | yes | 0.1.0 | |
| `full_name` | string | no | 0.1.1 | `null` if absent |
| `tenant_id` | UUID string | no | 0.1.0 | `null` for unscoped super admins |
| `tenant_slug` | string | no | 0.1.0 | |
| `department_id` | UUID string | no | 0.5.0 | `null` if absent; paired with `department_name` |
| `department_name` | string | no | 0.5.0 | `null` if absent |
| `role` | string | yes | 0.1.0 | `super_admin` / `admin` / `member`. **Deprecated** — removal planned for 0.6.0 |
| `group_ids` | list of UUID strings | no | 0.1.0 | defaults to `[]` |
| `product_access` | list of slug strings | no | 0.1.0 | defaults to `[]` |
| `features` | list of strings | no | 0.3.0 | each `"<product_slug>:<key>"`; defaults to `[]` |
| `roles` | list of strings | no | 0.4.0 | bare tenant-wide name or `"<role>:<product_slug>"`; never includes `super_admin`; defaults to `[]` |
| `session_id` | string | no | 0.4.0 | correlates with the HUB `sessions` row; `null` if absent |
| `iat` | int (unix ts) | yes | 0.1.0 | |
| `exp` | int (unix ts) | yes | 0.1.0 | |
| `jti` | string | no | 0.1.0 | unique token id; required by the Hub for blacklisting on logout |

[Unreleased]: https://github.com/oort-labs/oort-shared/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/oort-labs/oort-shared/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/oort-labs/oort-shared/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/oort-labs/oort-shared/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/oort-labs/oort-shared/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/oort-labs/oort-shared/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/oort-labs/oort-shared/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/oort-labs/oort-shared/releases/tag/v0.1.0
