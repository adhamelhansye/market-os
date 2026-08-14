Create a root-level "AGENTS.md" file for the MarketingOS repository.

This file is the permanent engineering instruction set for AI coding agents working on this repository.

Include these rules:

MarketingOS Engineering Rules

Product

MarketingOS is a production-grade multi-tenant AI marketing operating system for business owners, marketing agencies and media buyers.

Core product loop:

Understand → Research → Strategize → Simulate → Forecast → Launch → Measure → Diagnose → Optimize → Scale → Retain → Learn

Architecture

Use a modular monolith.

Frontend:

- Next.js
- TypeScript
- App Router
- Tailwind
- shadcn/ui
- TanStack Query
- React Hook Form
- Zod
- Recharts
- next-intl

Backend:

- Python
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic

Infrastructure:

- PostgreSQL
- Redis
- Docker

Do not introduce microservices unless explicitly requested.

Multi-tenancy

Every organization-owned database record must contain "organization_id".

Business-specific records must contain "business_id" where appropriate.

Never trust organization_id or business_id supplied by the client.

Always validate membership and permissions server-side.

Frontend authorization is UX only. Backend authorization is mandatory.

Security

Never log:

- passwords
- access tokens
- refresh tokens
- OAuth tokens
- encryption keys
- secrets

Use Argon2id for passwords.

Use secure httpOnly cookies for refresh tokens.

Validate all external webhook signatures.

Use parameterized database queries / ORM.

Never commit secrets.

Never disable security checks just to make tests pass.

Financial Data

Never use floating point for:

- money
- revenue
- cost
- profit
- spend
- price

Use NUMERIC/Decimal.

All KPI calculations must be deterministic.

The LLM must never invent numerical marketing metrics.

AI

LLMs may handle:

- reasoning
- classification
- research synthesis
- strategy
- explanations
- creative analysis
- recommendations

LLMs must NOT be the source of truth for:

- revenue
- spend
- CPA
- ROAS
- profit
- orders
- KPI calculations

Use deterministic code or statistical/ML systems for numerical calculations.

Integrations

Provider-specific code must stay inside provider adapters.

Core business logic must not directly call:

- Meta APIs
- Shopify APIs
- GA4 APIs
- TikTok APIs
- Google Ads APIs

Use adapter interfaces.

Localization

The product supports:

- English
- Arabic

English = LTR.

Arabic = RTL.

Never hardcode user-facing strings inside components.

All user-facing strings must use translation keys.

Do not translate technical metrics such as:
CTR, CPC, CPM, CPA, CVR, AOV, ROAS, CAC, MER.

Translate their descriptions and explanations.

Code Quality

Prefer:

- small functions
- clear names
- strict typing
- reusable modules
- explicit interfaces
- testable code

Avoid:

- giant components
- giant files
- duplicated logic
- "any"
- hidden global state
- magic numbers
- hardcoded URLs
- hardcoded secrets

Database

Use:

- UUID primary keys
- UTC timestamps
- Alembic migrations
- PostgreSQL constraints
- indexes based on query patterns

Never manually modify production schema without a migration.

API

All APIs must live under:

"/api/v1"

Use Pydantic request/response schemas.

Keep API contracts explicit.

Do not expose internal database models directly as API responses.

Testing

Every meaningful business rule must have tests.

Especially:

- authentication
- authorization
- tenant isolation
- financial calculations
- integrations
- forecasting
- recommendations

Do not delete or weaken tests to make a task pass.

Git

Make small logical commits.

Do not rewrite unrelated code.

Do not modify files unrelated to the current task.

Do not push to remote repositories unless explicitly requested.

Scope Control

IMPORTANT:

Only implement the task explicitly requested.

Do not proactively implement future modules.

Do not add:

- simulator
- forecasting
- Meta integration
- Shopify integration
- GA4 integration
- AI research
- competitor intelligence
- creative generation
- autonomous campaign execution

unless explicitly requested.

Before modifying architecture, explain why the change is necessary.

Before adding a dependency, explain why it is needed.

Agent Workflow

For every task:

1. Inspect the existing implementation.
2. Identify relevant files.
3. State a short plan.
4. Implement only the requested scope.
5. Run relevant tests.
6. Run lint/type checks.
7. Fix failures.
8. Review the diff.
9. Summarize changes and remaining issues.

Never claim a task is complete without actually testing it.

Important

Preserve existing working behavior.

Prefer incremental changes over rewrites.

If requirements are ambiguous, inspect the existing architecture and choose the smallest safe implementation consistent with these rules.
