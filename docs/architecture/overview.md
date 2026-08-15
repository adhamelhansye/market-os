# Architecture Overview

## System at a glance (Phase 0)

Phase 0 is the foundation of MarketingOS: a monolith with two deployable
components plus supporting infrastructure.

| Component | Technology | Role |
| --- | --- | --- |
| `apps/api` | Python, FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2 | All business logic, auth, tenancy, RBAC — the only source of truth |
| `apps/web` | Next.js 15 (App Router), TypeScript, Tailwind, shadcn-style UI, TanStack-free Phase 0, next-intl | Locale-first UI (en/ar, LTR/RTL) over the API |
| `packages/shared-types` | TypeScript types generated from OpenAPI | Single source of API contract types for the frontend |
| Postgres 16 | Database (UUID PKs, UTC timestamps, constraints, indexes) | Primary store |
| Redis 7 | Refresh-token sessions, rate limiting | Session/abuse store |

Infrastructure lives in `docker-compose.yml`; services are built with
`infra/docker/Dockerfile.api` and `Dockerfile.web`.

## Modular monolith (ADR-0001)

There is exactly one backend service and one frontend service. Feature code
inside the API is organized in `src/modules/*` (auth, organizations,
businesses, health, integrations, sync, metrics) sharing `src/core`
primitives (config, security, RBAC, tenancy, dependencies, middleware). This
is a deliberate choice: a modular monolith keeps Phase 0 and 1 fast to ship
while retaining clear seams for later extraction. **Microservices are not
introduced unless explicitly requested.**

## The product loop

Understand → Research → Strategize → Simulate → Forecast → Launch → Measure →
Diagnose → Optimize → Scale → Retain → Learn

Phase 0 implements only the foundation of this loop. None of the loop's
data-gathering or analysis features exist yet. Phase 3A ships the first
**Measure** brick: unified metrics and a deterministic KPI engine (see
`docs/architecture/metrics.md`). Phase 3B layers deterministic, evidence-backed
**Diagnose** on top of the KPI engine (see `docs/architecture/diagnostics.md`).

## Layering (backend)

```
HTTP
  └─ src/main.py                 # FastAPI app, middleware, exception handlers, /api/v1 routers
      └─ src/modules/*/router.py # Routes declare dependencies; no auth logic inline
          └─ src/core/dependencies.py  # get_current_user, resolve tenant, require_permission, rate_limit
              └─ src/core/security.py  # Argon2id, JWT, cookies
              └─ src/core/tenancy.py   # TenantContext, business access checks
              └─ src/modules/*/service.py  # Business logic (e.g. signup, token rotation)
                  └─ src/db/models/    # SQLAlchemy models (not exposed to clients)
                      └─ Postgres (Alembic-managed)
```

Rules:

- Routes never implement authorization themselves; they use dependencies from
  `src/core/dependencies.py`.
- Internal models are never returned as API responses; Pydantic schemas in
  `src/schemas/entities.py` define the API contract.
- All endpoints live under `/api/v1`.
- Provider-specific logic (Shopify today; Meta, GA4, TikTok, Google Ads
  later) stays inside provider adapters behind the `IntegrationAdapter`
  interface — core business logic never calls provider APIs directly (see
  `docs/architecture/integrations.md` and `docs/architecture/shopify.md`).

## Schema

Migration `0001_initial` creates seven tables:

- `users` — email (unique), Argon2id password hash, name, locale, is_active
- `organizations` — name, unique slug, `type` (`agency` | `business`),
  `locale_default`
- `roles` — name + `permissions_json`; **system roles have `organization_id`
  NULL** (global), org-scoped roles are per-organization
- `memberships` — user ↔ organization with a role; unique per
  (user, organization); status `active | invited | suspended`
- `businesses` — owned by `organization_id`, optionally
  `managed_by_organization_id` (agency-managed); onboarding status, currency,
  timezone
- `invitations` — pending membership invites (`token_hash`, `expires_at`,
  `accepted_at`)

See `docs/architecture/tenancy.md` for the tenancy model and
`docs/architecture/authentication.md` for security flows.

## API surface (Phase 0)

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/v1/health` | — | liveness |
| GET | `/api/v1/health/ready` | — | postgres + redis readiness |
| POST | `/api/v1/auth/signup` | — | rate-limited; creates user + org + owner role |
| POST | `/api/v1/auth/login` | — | rate-limited; sets refresh cookie |
| POST | `/api/v1/auth/refresh` | — | rotation; sets new refresh cookie |
| POST | `/api/v1/auth/logout` | — | revokes refresh session |
| GET | `/api/v1/auth/me` | bearer | user + memberships summary |
| GET | `/api/v1/organizations` | bearer | current tenant organizations |
| GET | `/api/v1/organizations/{id}` | bearer | detail gated by membership |
| GET | `/api/v1/businesses` | bearer | org-owned + managed businesses |
| GET | `/api/v1/businesses/{id}` | bearer | detail gated by business access |
| GET | `/api/v1/businesses/{id}/metrics/summary` | bearer | period KPIs (see `metrics.md`) |
| GET | `/api/v1/businesses/{id}/metrics/timeseries` | bearer | daily facts-only points |
| GET | `/api/v1/businesses/{id}/metrics/funnel` | bearer | funnel stages + rates |
| GET | `/api/v1/businesses/{id}/metrics/campaigns` | bearer | campaign rollups (ad grain) |
| GET | `/api/v1/businesses/{id}/metrics/adsets` | bearer | ad set rollups (ad grain) |
| GET | `/api/v1/businesses/{id}/metrics/ads` | bearer | ad rollups (ad grain) |
| GET | `/api/v1/businesses/{id}/metrics/products` | bearer | per-product units/revenue/AOV |
| GET | `/api/v1/businesses/{id}/metrics/data-quality` | bearer | provider freshness |
| GET | `/api/v1/businesses/{id}/metrics/comparison` | bearer | current vs previous period |
| GET | `/api/v1/businesses/{id}/diagnostics` | bearer | deterministic findings + summary + campaign states (see `diagnostics.md`) |
| GET | `/api/v1/businesses/{id}/diagnostics/summary` | bearer | counts only |
| GET | `/api/v1/businesses/{id}/campaigns/{cid}/diagnostics` | bearer | findings scoped to one campaign |

Schema: `/openapi.json` (served by FastAPI). Client types are generated from
this live schema into `packages/shared-types` by
`infra/scripts/generate-types.sh`.

## Frontend structure

- All routes are locale-first: `/[locale]` root segment with `en` and `ar`;
  middleware redirects `/` → `/en` and matches only `/(en|ar)/*`.
- `html lang` and `dir` are set from the resolved locale (Inter for Latin,
  Noto Sans Arabic for Arabic) in `src/app/[locale]/layout.tsx`.
- All user-facing strings live in `apps/web/messages/{en,ar}/*.json`
  (namespaces: `common`, `auth`, `dashboard`, `metrics`) and are reached
  through next-intl keys. No strings are hardcoded in components.
- UI components in `src/components/ui/*` (button, input, label, card, select)
  are shadcn-style primitives; no component is a "giant" file.
- State: `AuthProvider` + `BusinessProvider` (React context) in
  `src/context`; API calls go through `src/features/*/api.ts` using the
  shared `api-client` (silent refresh-token rotation). Phase 0 pages are
  read-only views of the auth/organization/business foundation.
- The metrics dashboard (`/business/[business_id]/metrics`) renders the
  analytics API: KPI cards, Recharts trend charts, funnel and campaigns
  tables, data-quality cards. Money is displayed only through
  `src/lib/money.ts` formatters; no arithmetic happens in the browser.

## Testing strategy

- Backend (`apps/api/tests`): auth flows, Argon2id hashing, RBAC matrices,
  tenant isolation, agency-managed business access, rate limiting, health,
  integrations, sync, and metrics (KPI engine unit tests + analytics API
  integration tests with a seeded data contract).
  Tenant isolation tests assert that an organization can never read another
  organization's records even with a valid token.
- Frontend (`apps/web/src/test`): locale helpers, `html lang`/`dir` for LTR
  and RTL, login/signup rendering in both locales, zod validation messages,
  dashboard empty states, and metrics dashboard rendering in both locales.
- CI (`.github/workflows/ci.yml`) runs lint, typechecks, backend tests,
  frontend tests and the production build on every push/PR.

## Financial-data guardrails (Phase 3A enforced)

- Money, revenue, cost, profit, spend and price are only ever handled as
  `Decimal`/`NUMERIC`; floats are prohibited for monetary values.
- KPI calculations (CPA, ROAS, MER, CTR, ...) are deterministic server-side
  code computed by the KPI engine; LLMs never produce or invent numerical
  marketing metrics.
- Measures are `available` | `unavailable` (with reason) |
  `insufficient_data` | `invalid`; zeros are never fabricated and ratios are
  never invented for missing denominators.
- Period KPIs are always computed from aggregated totals, never by averaging
  daily or per-campaign ratios. API responses serialize money as strings and
  counts as integers.

## Environment & configuration

- Settings are read from environment by Pydantic (`src/core/config.py`) and
  validated at startup; unknown/extra keys are ignored, required secrets are
  mandatory.
- `.env.example` documents every variable (including `TEST_DATABASE_URL` and
  `TEST_REDIS_URL` used by the test suite against the Docker services).
- The web app talks to the API at `NEXT_PUBLIC_API_URL`; CORS is restricted
  to the configured web origin.

## Financial-data guardrails (future phases)

- KPI calculations (CPA, ROAS, ...) are deterministic server-side code; LLMs
  never produce or invent numerical marketing metrics.
- Future phases (LLM research, forecasting, recommendations) receive metrics
  as **inputs** from the deterministic pipeline only; they never compute or
  override them.

## Related documents

- `docs/architecture/tenancy.md` — tenancy model and enforcement
- `docs/architecture/authentication.md` — auth flows and security
- `docs/architecture/integrations.md` — adapter core, credentials, sync/webhooks
- `docs/architecture/shopify.md` — Shopify provider specifics
- `docs/architecture/metrics.md` — unified metrics, KPI engine, analytics API
- `docs/architecture/diagnostics.md` — deterministic findings, evidence-backed diagnostics layer
- `docs/adr/0001-monolith.md` — monolith decision
- `docs/adr/0002-multi-tenancy.md` — tenancy decision (incl. why no RLS yet)
- `AGENTS.md` — permanent engineering rules