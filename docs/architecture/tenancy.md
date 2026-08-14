# Tenancy

## Model

MarketingOS is multi-tenant. The unit of tenancy is the **organization**.

- Every organization-owned record carries `organization_id` (see "Data
  model" below). This is mandatory, not optional.
- A user belongs to organizations through `memberships`, with a role per
  membership.
- Business records belong to an organization. An agency organization can
  additionally manage businesses whose `organization_id` is a client's — the
  agencies are management tenants, the clients remain data owners.

## Data model

```
organizations (type: 'agency' | 'business', unique slug)
   └── memberships (user_id, organization_id, role_id)   -- unique per user+org
   └── roles (name, permissions_json; system roles: organization_id IS NULL)
   └── businesses
         ├── organization_id               -- the owning organization
         └── managed_by_organization_id    -- optional agency manager
   └── invitations (email, role_id, token_hash, expires_at)
users (email unique, password_hash)
```

## Enforcement (application level)

The backend is the **only** source of truth for tenancy. The frontend never
influences authorization: submitted `X-Organization-Id` values and path
organization ids are treated as untrusted input.

### Tenant resolution

`src/core/dependencies.py` defines exactly two resolution paths:

1. `get_current_tenant` — reads `X-Organization-Id` (header for the current
   organization), loads the user's membership and returns a
   `TenantContext`; unknown ids, malformed uuids and non-member
   organizations all result in errors (never a fallback to another org).
2. `get_org_from_path` — same validation for an organization id that comes
   from the URL path.

`TenantContext` carries the membership's role permissions; access checks use
`tenant.has_permission(...)` only.

### Permission enforcement

`require_permission("business:read")` and
`require_org_permission("org:manage")` are dependency factories in
`src/core/dependencies.py`. Routes declare these dependencies and never
re-implement authorization. Permissions are defined centrally in
`src/core/rbac.py`:

| Permission | Owner | Admin | Member | Viewer |
| --- | --- | --- | --- | --- |
| `org:read` | ✓ | ✓ | ✓ | ✓ |
| `org:manage` | ✓ | ✓ | — | — |
| `members:read` | ✓ | ✓ | ✓ | ✓ |
| `members:manage` | ✓ | ✓ | — | — |
| `business:read` | ✓ | ✓ | ✓ | ✓ |
| `business:write` | ✓ | ✓ | ✓ | — |
| `dashboard:read` | ✓ | ✓ | ✓ | ✓ |
| `settings:read` | ✓ | ✓ | ✓ | ✓ |
| `settings:write` | ✓ | ✓ | — | — |

System roles are seeded by `infra/scripts/seed.py` (idempotent) with
`organization_id = NULL`; org-scoped custom roles are a later phase.

### Business access

`get_business_from_path` uses `can_access_business(session, org_id,
business_id)` (`src/core/tenancy.py`):

- the business `organization_id` equals the current organization, **or**
- `managed_by_organization_id` equals the current organization (agency
  management case).

Nothing else grants access. This is what makes the "agency manages client
business" flow possible without any client-supplied trust.

### Membership- and org-scoped queries

List endpoints filter by the membership's organizations; detail endpoints
validate access through the dependencies above. The database layer also
carries `organization_id` on every business/organization-owned row, which
keeps all future queries naturally tennant-bound.

## Rules

- `organization_id` (and `business_id`) supplied by the client are **never
  trusted**; membership is validated server-side on every request.
- Frontend hiding of controls is UX only and never a security boundary.
- Tests in `apps/api/tests/test_tenancy.py` assert cross-tenant isolation
  end to end: valid token + foreign organization id ⇒ 404, never data leak.
- `docs/adr/0002-multi-tenancy.md` records why Row-Level Security is
  deferred to a later phase and how to reintroduce it without schema
  changes.