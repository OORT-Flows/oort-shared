# Changelog

All notable changes to `oort-shared` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **JWT contract changes** must be called out explicitly in every release — adding, removing, renaming, or retyping a claim is the most load-bearing thing this library does. If a release does not change the JWT contract, say so explicitly under the version heading.

## [Unreleased]

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

[Unreleased]: https://github.com/oort-labs/oort-shared/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/oort-labs/oort-shared/releases/tag/v0.1.0
