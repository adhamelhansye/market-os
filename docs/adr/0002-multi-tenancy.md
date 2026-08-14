# ADR-0002: Application-level multi-tenancy (RLS deferred)

- Status: accepted
- Date: 2026-08-13

## Context

MarketingOS is multi-tenant by design: organizations own data; agencies may
manage client businesses; users belong to multiple organizations with
different roles. The failure mode to prevent is cross-tenant data leakage,
including leakage through "managed business" access.

## Decision

Enforce tenancy at the **application layer**:

1. Every organization-owned table carries `organization_id` (businesses
   additionally `managed_by_organization_id`).
2. All reads are scoped by membership and permission checks implemented as
   FastAPI dependencies (`get_current_tenant`, `require_permission`,
   `get_business_from_path`) — see `docs/architecture/tenancy.md`.
3. Client-supplied org/tenant identifiers are never trusted; membership is
   validated server-side per request.
4. Row-Level Security in Postgres is **not** enabled in Phase 0; the schema
   is already RLS-compatible (org ids present, no cross-tenant columns), and
   enabling RLS later is a migration-only change, not a redesign.

## Rationale

- Phase 0 has a small, fully testable surface; application-layer checks give
  immediate, debuggable isolation with the existing test suite.
- RLS adds operational complexity (per-request session variables, policy
  maintenance, and the same application checks anyway for business rules
  like agency-managed access) without replacing the dependency-based
  enforcement.
- Tenant isolation is already covered by dedicated tests
  (`apps/api/tests/test_tenancy.py`, `test_agency_business.py`), which will
  continue to guard RLS when it lands.

## Consequences

- No defense-in-depth at the DB layer yet; rely on tests + code review.
- Later hardening step: introduce RLS policies on `organizations`,
  `businesses`, `memberships` and future tenant-owned tables by migration,
  keeping `organization_id` in every query.

## References

- `docs/architecture/tenancy.md`
- `AGENTS.md` (Multi-tenancy, Security)