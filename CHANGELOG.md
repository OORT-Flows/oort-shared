# Changelog

All notable changes to `oort-shared` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **JWT contract changes** must be called out explicitly in every release — adding, removing, renaming, or retyping a claim is the most load-bearing thing this library does. If a release does not change the JWT contract, say so explicitly under the version heading.

## [Unreleased]

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

### JWT contract (v0.1.0)

| Claim | Type | Required | Notes |
|---|---|---|---|
| `sub` | UUID string | yes | Hub user id |
| `email` | string | yes | |
| `role` | string | yes | `super_admin` / `admin` / `member` |
| `iat` | int (unix ts) | yes | |
| `exp` | int (unix ts) | yes | |
| `tenant_id` | UUID string | no | `null` for unscoped super admins |
| `tenant_slug` | string | no | |
| `group_ids` | list of UUID strings | no | defaults to `[]` |
| `product_access` | list of slug strings | no | defaults to `[]` |
| `jti` | string | no | unique token id; required by the Hub for blacklisting on logout |

[Unreleased]: https://github.com/oort-labs/oort-shared/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/oort-labs/oort-shared/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/oort-labs/oort-shared/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/oort-labs/oort-shared/releases/tag/v0.1.0
