# Deterministic Analytics Diagnostics (Phase 3B)

Phase 3B layers a deterministic, evidence-backed diagnostics layer on top of
the Phase 3A KPI engine. Diagnoses are not LLM-generated narratives and they
are not single composite scores — every finding is a structured, inspectable
observation with metric, threshold, comparison, funnel context and the facts
that triggered it.

## Pipeline

```
KPI engine (Phase 3A)
  ├─ summary, funnel, campaigns, comparison, data quality
  └─► DiagnosticsEngine
        ├─ Thresholds (versionable, centralized)
        ├─ Rule set (traffic / creative / conversion / offer / funnel /
        │   economics / tracking / data quality / performance / scaling)
        ├─ Sample protection (insufficient_data instead of any verdict)
        └─► Finding list (FindingRead) ─► DiagnosticsRead
              ├─ summary (counts per severity, insufficient_data, entities)
              ├─ findings[]
              ├─ campaign_states[] (performance_state, scaling_readiness)
              └─ data quality + bottleneck highlight (UI)
```

- The diagnostics engine never touches the database or provider APIs. It
  consumes the typed `DiagnosticsContext` that the service assembles from
  existing KPI outputs (`service.entity_metrics_view`, funnel, comparison,
  data quality). One source of truth for numbers; one place to evolve them.
- Thresholds live in `src/modules/diagnostics/thresholds.py` as a typed
  dictionary (`{code: Threshold}`). They are versionable, tested and never
  embedded in rule code.
- Each rule returns `False` when sample minima are not met (impressions,
  clicks, purchases, spend). The engine then emits an
  `insufficient_data` finding instead of a performance verdict.

## Sample protection

Before any rule fires we enforce hard sample minima. A finding is only
emitted when the underlying facts cross the minimum; otherwise the engine
records an `insufficient_data` finding so the UI can show *why* there is no
verdict (see `diagnostics.insufficient_data.*` message keys).

| Minimum | Why |
| --- | --- |
| `sample_min_impressions` ≥ 500 | Confidence interval for click-through and rate metrics |
| `sample_min_clicks` ≥ 50 | Same, for downstream transition rates (impressions → clicks) |
| `sample_min_purchases` ≥ 3 | Conversion-rate and CPA verdicts |
| `sample_min_spend` ≥ 100 (in business currency) | Break-even / contribution analysis |

Per-statement and per-funnel minima are stacked: if any stage in a transition
is below the floor the bottleneck is suppressed; the UI surfaces the
insufficient sample instead.

## Finding shape

```ts
FindingRead = {
  id, business_id, entity_type, entity_id?, entity_name?,
  category, code, severity, status,
  title_key, description_key, // next-intl keys, never prose
  reason?, // machine-readable why
  evidence: {
    metric?: { code, current, previous? },
    threshold?: { code, operator, value, unit },
    comparison?: { code, change_percent },
    funnel?: { from_stage, to_stage, conversion_rate, previous_rate },
    facts: { code, value, unit }[]
  },
  affected_stage?, range, currency, review_status?
};
```

Findings carry translation keys (`diagnostics.<code>.title|description`) so
the UI can localize without leaking prose into the data model. Money values
are `Decimal` strings; ratios are stored as strings. The frontend formats
through `formatMoney` / `formatRatio` — no arithmetic happens in the browser.

## Severity and status

- `critical` — immediate economic or operational impact (negative profit,
  conversion API mismatch).
- `high` — performance pathologies outside tolerance (high CPC, funnel
  bottleneck, persistent unprofitability).
- `medium` — early warning (data-quality degradation, declining margin).
- `low` — informational, often a fingerprint needing human review.
- `info` — sample protection or rule preconditions not met
  (`status="insufficient_data"`).
- `resolved` — historical, kept for the audit trail.

Severities are mapped from the rule output through
`Severity` (`src/modules/diagnostics/evidence.py`). Every rule carries a
severity ceiling; the engine clamps any rule's severity to that ceiling to
keep the escalation coherent.

## Funnel diagnostics

Funnel findings respect the KPI engine's group semantics (`awareness`,
`traffic`, `intent`, `purchase`). The bottleneck rule walks the funnel chain
(`impressions → clicks → landing_page_views → purchases`) and only reports a
drop when:

- both adjacent stages have enough samples,
- the conversion rate is below `funnel_low_transition`,
- the drop is material relative to the previous period (the funnel evidence
  includes `previous_rate` so the UI can show whether the decline is new).

A new dataset (e.g. all stages are present but zero transitions) does not
yield a verdict — it becomes `unobserved_funnel_stages`.

## Data-quality and integrations

The diagnostics engine is informed by the data-quality service: provider
freshness, missing reporting windows and recent sync failures all surface
as `data_quality` findings with `review_status=review_required`. The UI
shows them in a separate panel so a customer can act before assuming the
analytics itself is broken.

## Scaling readiness

For each campaign the engine emits a `CampaignStateRead` with:

- `performance_state` — `learning` | `healthy` | `attention` | `inefficient`
  | `profitable` | `unprofitable` | `stale_data` | `insufficient_data`
- `scaling_readiness` — `learning` | `stable` | `insufficient_data`
  | `performance_positive` | `performance_negative`, with the gate facts
  (spend, impressions, days, conversions) so the UI can show *why* a
  campaign is not ready to scale.

The scaling rule is gated on the same sample minima as performance verdicts.

## Endpoints

All endpoints live under `/api/v1` and require `business:read`.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/businesses/{id}/diagnostics` | bearer, business:read | Findings + summary + campaign states + bottleneck highlight |
| GET | `/businesses/{id}/diagnostics/summary` | bearer, business:read | Counts only, for dashboard cards |
| GET | `/businesses/{id}/campaigns/{cid}/diagnostics` | bearer, business:read | Findings scoped to one campaign |

Filters:

- `range_kind` — `today`, `yesterday`, `last_7_days`, `last_14_days`,
  `last_30_days`, `month_to_date` (mirrors metrics).
- `entity_type` — `business`, `campaign`, `ad_set`, `ad`.
- `severity` — `info`, `low`, `medium`, `high`, `critical`.
- `category` — traffic, creative, conversion, offer, funnel, economics,
  tracking, data_quality, performance, scaling_readiness.
- `status` — `detected`, `resolved`, `insufficient_data`.

422 `invalid_diagnostics_filter` is returned for unknown filter values or
combinations; 404 `not_found` for unknown business/campaign or
cross-tenant access (always validated server-side, never trusted from the
client).

## Frontend

- `apps/web/messages/{en,ar}/diagnostics.json` provide 147 keys each
  (parity-verified): title/subtitle, overview labels, finding / filter /
  severity / status / category / state / scaling / entity / stage labels, and
  `diagnostics.<code>.title|description` for every rule.
- `apps/web/src/features/diagnostics/diagnostics-section.tsx` renders the
  DiagnosticsSection inside the analytics dashboard
  (`/business/{id}/metrics`): summary cards, bottleneck highlight, filter
  bar, finding cards (with severity badge, threshold, comparison, funnel
  context, facts), campaign states table, data-quality warnings panel,
  loading/error/empty states.
- The component is en/ar-native via next-intl; no string is hardcoded, no
  finding is ever translated inline. Filters narrow findings, the campaign
  table, and the warnings list in lock-step.
- The component never directly calls provider APIs or DB; it uses
  `fetchDiagnostics` from `features/diagnostics/api.ts`, which wraps the
  shared `api-client` (refresh-token rotation, retries, error shape).

## Testing strategy

- `tests/test_diagnostics_rules.py` — 90 deterministic unit tests covering
  every rule: boundaries (above/below threshold), sample protection, KPI
  formulas (cpc, cpa, roas, contribution), funnel drops, creative fatigue,
  scaling readiness gates, fingerprinting.
- `tests/test_diagnostics.py` — 15 integration tests against the API:
  filters and 422s, summary endpoint, per-campaign endpoint, cross-tenant
  404s, sync-failure → data-quality finding, insufficient-data filtering,
  review_required propagation, dedup + fingerprints.
- `apps/web/src/test/diagnostics-section.test.tsx` — 8 component tests:
  summary counts, finding cards + severity badges + threshold + facts,
  insufficient-data rendering, funnel bottleneck highlight, campaign
  states table, data-quality warnings panel, loading/error/empty states,
  Arabic parity.

The diagnostics tests never modify the Phase 3A KPI engine or aggregation
queries; they only exercise rules and the diagnostics endpoints.

## Related documents

- `docs/architecture/metrics.md` — KPI engine, canonical facts, status
  semantics the diagnostics layer depends on.
- `docs/architecture/tenancy.md` — tenant isolation; diagnostics endpoints
  enforce business access server-side.
- `docs/architecture/integrations.md` — adapter contracts and freshness
  signals consumed by the data-quality findings.
- `AGENTS.md` — financial-data guardrails (no floats, deterministic math)
  and AI boundaries (LLMs never produce numerical marketing metrics).
