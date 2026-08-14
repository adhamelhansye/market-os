# ADR-0001: Modular monolith

- Status: accepted
- Date: 2026-08-13

## Context

MarketingOS must support a wide product surface (auth, tenancy, businesses,
integrations, AI analysis, forecasting, billing, notifications) while being
developed incrementally and shipped fast. Distributed systems add operational
cost (observability, network failure modes, version skew, transaction
handling) that Phase 0-1 does not need and that would slow the core
product loop.

## Decision

Keep a modular monolith:

- one backend service (`apps/api`, FastAPI) and one frontend service
  (`apps/web`, Next.js), packaged with Docker Compose;
- feature code in `apps/api/src/modules/*` with clear boundaries
  (routers/services/schemas per module), sharing `src/core` primitives;
- shared API types in `packages/shared-types`, generated from OpenAPI.

## Consequences

- Faster iteration: one deployable, one test surface, local transactions
  across modules (e.g. signup creating user + org + membership atomically).
- Clear seams: if a module (e.g. billing) ever needs to be extracted, its
  module boundary is already explicit.
- Microservices are only introduced on explicit request; the default remains
  the monolith.

## References

- `docs/architecture/overview.md`
- `AGENTS.md` (Architecture)