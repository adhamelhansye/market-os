# Deterministic Decision Engine (Phase 4B)

The decision engine produces **review recommendations** — never actions —
from the deterministic pipeline: Metrics → Diagnostics → Forecast →
Economics → Goals → **Decision Engine** → Structured Decision.

Everything upstream (KPIs, findings, forecasts, economics, goals) is
computed by its own deterministic module; the engine only consumes it.
It never queries a provider, never invokes an LLM, never recomputes a KPI
formula and never executes anything.

## Scope

- `decide_business` — business-grain decision. Purchases/revenue/CPA are
  attributed. Business-level tracking and data-quality findings gate the
  decision.
- `decide_campaign` — campaign-grain decision. Campaigns have **no purchase
  attribution** (Phase 3B rule), so `purchases`/`revenue`/`cpa`/`cvr` are
  explicitly unavailable — never invented. ROAS uses Meta-reported
  conversion value. Business-level tracking/data-quality findings still
  gate the decision (they affect every campaign's truthfulness).

## Decision types (review labels, in precedence order)

| Decision | Precedence | Meaning |
| --- | --- | --- |
| `tracking_issue` | 1 | Conversion/revenue mismatch or stale sync — do not trust performance |
| `data_quality_issue` | 2 | Missing stages, incomplete reporting, stale data |
| `insufficient_data` | 3 | No spend/impressions or tiny samples (< $100 spend, < 1000 impressions) |
| `learning` | 4 | Has early signals but does not meet the full sample gates yet |
| `kill_review` | 5 | Persistent, evidence-backed unprofitability — human review only |
| `scale_review` | 6 | Profitable, sufficient sample, no major diagnostic — safe incremental growth review |
| `optimize` | 7 | Bottleneck or cost-efficiency issue (low CTR, high CPC, low CVR, CPA above viable) |
| `maintain` | 8 | Healthy, no bottleneck, economics positive |

First match wins (precedence implemented as an explicit ordered list in
`resolve_decision`, mirrored in `severity.DECISION_PRECEDENCE`).

### kill_review is strictly gated

`kill_review` fires ONLY when all of these hold:

- no tracking/data-quality issue,
- spend ≥ $500 in the range,
- range ≥ 14 days,
- enough loss evidence: ≥ 10 purchases at business grain, or ≥ 10 Meta
  conversions at campaign grain (no purchase attribution), or CPA > 2×
  viable CPA,
- ROAS below break-even − 0.1 **or** CPA > 2× viable CPA,
- forecast ROAS (when available) below break-even.

There is no autonomous kill: the label is always `kill_review` with
advisory `review_*` suggestions. Goals never override hard economics —
e.g. ROAS 2.5 with a goal target of 3 yields `optimize`, never `kill_review`.

### scale_review is strictly gated

Requires: fresh data, no tracking/data-quality issue, sample gates met,
ROAS ≥ break-even + 0.2, CPA ≤ viable CPA (90% band), no major
(high/critical) diagnostic, and forecast ROAS not deteriorating > 15%
from current ROAS (when forecast is available). A missing forecast degrades
gracefully instead of blocking.

## Evidence

Every decision carries structured evidence (`DecisionEvidence`):

- `evidence_items` — metric/threshold/comparison/funnel/facts items, each
  with `rule` and `source` (metrics, diagnostics, forecast, economics,
  goals)
- `diagnostics_refs` — ids of the findings that informed the decision
- `forecast_refs` / `goal_refs` — the forecast metric code / goal fields used
- `evidence_strength` — deterministic ratio of available inputs:
  ≥ 0.9 strong, ≥ 0.7 moderate, ≥ 0.5 weak, else insufficient
- `metrics_snapshot` — exact values at decision time (money as strings)
- `review_suggestions` — advisory translation-key-like labels, all starting
  with `review_` or `test_`; nothing is executed

Percentages, rates and money are `Decimal` end-to-end; JSONB persistence
serializes them as strings.

## Sample gates

Reuses the Phase 3B thresholds registry (`diagnostics.thresholds.value`,
resolved by code): ≥ $100 spend, ≥ 500 impressions, ≥ 3 conversions, ≥ 7
days. Below these, `insufficient_data`/`learning` keep the decision honest.

## Persistence & idempotency

- ORM model `Recommendation` (`recommendations` table, migration `0008`):
  `organization_id` + `business_id` (FK to businesses, CASCADE), optional
  `entity_id` FK to campaigns, decision, evidence_strength, primary_reason,
  diagnostics/evidence/review_suggestions/metrics_snapshot/forecast_snapshot
  JSONB, range_start/range_end, rules_version, fingerprint.
- Deterministic fingerprint = SHA-256 over
  `(organization_id, business_id, entity_type, entity_id, range.start,
  range.end, rules_version)` with a unique constraint — recomputation is an
  idempotent upsert, never a duplicate.
- The list/summary endpoints compute and upsert on read (cache rows,
  side-effect free for providers); `POST /generate` recomputes everything
  explicitly.

## API

All endpoints require `business:read` and resolve the business from the
tenant server-side (404 on unknown/cross-tenant ids, never a leak):

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/businesses/{id}/recommendations` | Decisions + summary, filters: `entity_type`, `entity_id`, `decision`, `severity`, `range_kind` / `date_from`/`date_to` |
| GET | `/api/v1/businesses/{id}/recommendations/summary` | Counters only |
| GET | `/api/v1/businesses/{id}/campaigns/{cid}/recommendation` | One campaign decision |
| POST | `/api/v1/businesses/{id}/recommendations/generate` | Recompute + persist idempotently |

Filters are validated server-side (`entity_type` must be
business/campaign, `decision` must be a known type, `severity` must be a
valid severity — else 422); entity ids must resolve inside the business
(else 404). Response schemas are explicit Pydantic contracts
(`DecisionRead`, `DecisionsRead`, `DecisionSummaryRead`); internal models
are never exposed.

## Frontend

`apps/web/src/features/recommendations` renders a Decisions section on the
metrics dashboard: summary counters, filterable decision cards
(entity/decision), evidence strength badges, reviewReason and advisory
suggestion keys. All strings are translation keys
(`messages/{en,ar}/recommendations.json`, exact key parity); there is no
client-side decision math. The section is never more than a viewer of the
server decision and its review labels.

## Safety invariants (tested)

The safety test suite enforces:

- the module import graph never reaches integration adapters, sync or jobs
  code (no mutation path exists),
- source contains no action verbs (pause/delete/update/set_budget/...),
- `generate` and reads leave provider-side state untouched (no sync runs,
  no webhook events, no connection changes),
- all decision types are review labels; responses contain no action keys.

## Testing

- `tests/test_recommendations_rules.py` — pure rule unit tests: every
  decision type, precedence, sample gates, forecast integration, economics
  gates, evidence strength, suggestion verb contract.
- `tests/test_recommendations_api.py` — endpoint integration over the
  seeded tenant: list/summary consistency, filters, 404/422 semantics,
  per-campaign endpoint, generate idempotency, money-as-strings.
- `tests/test_recommendations_safety.py` — spec §40: zero mutation calls.
- `tests/test_recommendations_tenancy.py` — spec §41: cross-tenant 404s.
- `apps/web/src/features/recommendations/recommendations-section.test.tsx`
  — frontend rendering in en/ar.

## Related documents

- `docs/architecture/metrics.md` — deterministic KPI engine
- `docs/architecture/diagnostics.md` — findings/gates reused by decisions
- `docs/architecture/forecasting.md` — forecast evidence used by decisions
- `docs/architecture/unit-economics.md` — break-even inputs