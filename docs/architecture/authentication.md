# Authentication

## Overview

Stateless access tokens (JWT, 15 min) + revocable refresh sessions stored in
Redis (7 days) with rotation. Passwords are hashed with Argon2id. The refresh
token is delivered as an httpOnly cookie scoped to the auth path.

```
POST /api/v1/auth/signup  → user + organization + owner membership created
POST /api/v1/auth/login   → access token (body) + refresh cookie (httpOnly)
POST /api/v1/auth/refresh → rotated refresh session + new cookie
POST /api/v1/auth/logout  → refresh session revoked
GET  /api/v1/auth/me      → current user + memberships
```

## Password storage

- Argon2id via `argon2-cffi` (`src/core/security.py`). `verify_password`
  treats both `Argon2Error` and `InvalidHashError` as verification failure —
  an invalid stored hash must never raise into a handler.
- Passwords, tokens and secrets are never logged (logging layer only emits
  whitelisted fields).

## Tokens

`src/core/security.py`:

| Token | Lifetime | Carrier | Purpose |
| --- | --- | --- | --- |
| access token | 15 min | `Authorization: Bearer` | Authorizes API calls |
| refresh token | 7 days | httpOnly cookie `mos_refresh` | Obtains new access tokens |

- Access tokens are JWTs signed with `JWT_SECRET` (HS256) and carry
  `sub` (user uuid) and `type` claims.
- Refresh tokens are **not stored as plaintext**. Redis key
  `refresh_token:{jti}` holds the SHA-256 fingerprint of the token, the
  user id and an expiry; the token itself exists only on the client.
- Refresh is rotation-based: each `/refresh` **atomically consumes** the
  presented session (Redis `GETDEL` plus fingerprint comparison) and issues
  a fresh pair. Because claim-and-validate is a single atomic operation,
  concurrent replays of the same refresh token can never both succeed:
  exactly one rotation wins, every other caller observes a consumed session
  (single-use semantics, correct across multiple API instances).
- `/logout` deletes the session fingerprint; a revoked session is rejected
  on any subsequent refresh attempt.
- Cookie attributes: `httponly`, `path=/api/v1/auth`, `samesite=lax`,
  `secure` when the deployment is not dev (per environment config).

## Request lifecycle

1. `HTTPBearer` dependency extracts the access token; `get_current_user`
   (`src/core/dependencies.py`) verifies signature/expiry, resolves the user
   by `sub`, and rejects inactive users.
2. Tenant resolution validates membership (see `docs/architecture/tenancy.md`).
3. Permission dependencies enforce RBAC.
4. Rate limiting (fixed-window, Redis) protects signup (5/min), login
   (10/min) and refresh (20/min) per client IP; disabled under `APP_ENV=test`
   so tests never depend on timing.

## Security posture

- Middleware (`src/core/middleware.py`): request id (`X-Request-Id`),
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy`, and HSTS in production.
- Errors: 401 for auth failures, 403 for permission failures, 404 for
  missing resources (incl. foreign-tenant resources, so existence is not
  leaked), 429 for rate limits, generic 500 messages to clients while real
  details go to logs.
- CORS restricted to the configured web origin; credentials allowed only for
  that origin.
- All DB access goes through SQLAlchemy (parameterized); no string-built SQL.
- No secrets in the repository; `.env.example` documents required variables;
  pydantic Settings validates required secrets at startup.

## Frontend behavior

- `apps/web/src/lib/api-client.ts` attaches the bearer token and, on a
  401 from a data call, attempts a silent refresh (rotating the cookie) and
  retries once before failing.
- `AuthProvider` exposes `status`, `user`, `signIn`, `signUp`, `signOut`.
- Authorization hints are UX only; every real check happens in the API.