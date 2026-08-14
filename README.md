# MarketingOS

MarketingOS is a production-grade multi-tenant AI marketing operating system for business owners, marketing agencies and media buyers.

This repository contains **Phase 0**: the foundation — monorepo scaffolding, authentication, multi-tenancy with RBAC, localization (English/Arabic with RTL), a Docker development environment, and test suites. Later phases (integrations, research, forecasting, etc.) are intentionally **not** implemented yet.

## Core product loop

Understand → Research → Strategize → Simulate → Forecast → Launch → Measure → Diagnose → Optimize → Scale → Retain → Learn

## Repository layout

```
├── apps/
│   ├── api/                    # Python FastAPI backend
│   │   ├── alembic/            # Migrations
│   │   ├── src/
│   │   │   ├── core/           # config, security, rbac, tenancy, dependencies, middleware
│   │   │   ├── db/models/      # SQLAlchemy models
│   │   │   ├── modules/        # auth, organizations, businesses, health
│   │   │   └── schemas/        # Pydantic schemas (API contracts)
│   │   └── tests/              # pytest suites
│   └── web/                    # Next.js frontend (App Router)
│       ├── messages/{en,ar}/   # Translation messages (namespaced)
│       └── src/
│           ├── app/[locale]/   # Locale-first routes (login, signup, dashboard, settings)
│           ├── components/     # shadcn-style UI, layout, providers
│           ├── context/        # Auth + Business providers
│           ├── i18n/           # next-intl routing/request/messages
│           └── test/           # vitest + testing-library suites
├── packages/
│   └── shared-types/           # TypeScript types generated from the API's OpenAPI schema
├── infra/
│   ├── docker/                 # Dockerfiles
│   └── scripts/                # seed, generate-types
└── docs/
    ├── architecture/           # overview, tenancy, authentication
    └── adr/                    # architectural decision records
```

## Quick start

Prerequisites: Docker, Docker Compose.

```bash
cp .env.example .env
docker compose up --build -d
# API:      http://localhost:8000  (docs at /docs, schema at /openapi.json)
# Web:      http://localhost:3000  (root redirects to /en)
# Postgres: localhost:5432  Redis: localhost:6379
```

Seed system roles (idempotent):

```bash
make seed
```

## Development

```bash
make dev          # run API + web locally
make migrate      # apply Alembic migrations in the API container
make test-api     # backend tests (pytest, expects Docker postgres/redis)
make test-web     # frontend tests (vitest)
make lint         # ruff + next lint
make types        # TypeScript typechecks both workspaces
make build        # Next.js production build
```

Regenerate shared TypeScript types from the live OpenAPI schema (API must be running on `localhost:8000`):

```bash
infra/scripts/generate-types.sh
```

## What's included (Phase 0)

- **Authentication**: Argon2id password hashing, short-lived access tokens (15 min), revocable refresh sessions stored as SHA-256 fingerprints in Redis, refresh-token rotation, httpOnly secure cookie.
- **Multi-tenancy**: every organization-owned record carries `organization_id`; membership-based access (owner/admin/member/viewer); business records can be owned by an organization or managed on its behalf (`managed_by_organization_id`). Tenant and business access is validated server-side — the frontend cannot escalate.
- **RBAC**: system roles seeded via `infra/scripts/seed.py`; endpoints enforce permissions (e.g. `business:read`, `org:manage`) through central dependencies.
- **Localization**: English (LTR) and Arabic (RTL). `html lang`/`dir` are set per locale; all user-facing strings live in `messages/{en,ar}/`.
- **API contract**: all endpoints under `/api/v1`, Pydantic request/response schemas; shared TypeScript types generated from OpenAPI.
- **Financial safety guardrails**: monetary values only ever travel as `Decimal`/`NUMERIC` (see `docs/architecture/tenancy.md`); the LLM is not the source of truth for numbers (future phases).

## Testing

- Backend: `apps/api/tests` — authentication, password hashing, RBAC, tenant isolation, agency/business access, health.
- Frontend: `apps/web/src/test` — locale helpers, `html lang`/`dir` (LTR/RTL), login/signup rendering both locales, signup validation, dashboard empty states.

## Standards

See `AGENTS.md` for the permanent engineering rules (security, tenancy, financial data, integrations, code quality, testing, git).

## Roadmap

Phase 0 is the foundation only. Future phases (marked for later, per product spec): data integrations (Meta, Shopify, GA4, TikTok, Google Ads), AI research, strategy, simulation, forecasting, creative generation, autonomous campaign execution, metrics/KPI systems, and notifications (Celery workers, RLS hardening).

Do not start any Phase 1+ work without an explicit request.