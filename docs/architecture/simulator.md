# Simulator (deterministic campaign simulation)

## 1. Overview and goal

The simulator answers "what would this spend produce?" before any money is
spent. Given a budget, a duration, a historical window and optional targets,
it produces deterministic scenario estimates (downside / expected / upside),
sensitivity tables, break-even analysis, target comparisons, and an evidence
strength assessment — all computed from *stored* historical metrics and unit
economics. It ships in Phase 5A next to Forecast (Phase 4A) and
Recommendations (Phase 4B) and follows the same architectural rules.

A simulation is a persisted, idempotent model run: it snapshots its inputs
(`assumptions_snapshot`, `results_snapshot`, `assumptions_hash`) so a row in
history can be opened or re-run later as the equivalent of the original run.

## 2. Deterministic engine principle

The engine is pure, deterministic Python. The same inputs (assumption values,
duration, scenario multipliers) always produce identical outputs:

- Every calculation runs through immutable `Decimal` arithmetic; money
  fields never touch floats.
- Scenario multipliers are fixed constants applied to purchases and revenue
  per scenario label.
- Sensitivity deltas are fixed constants: `SENSITIVITY_STEPS`
  (−0.20, −0.10, −0.05, 0, +0.05, +0.10, +0.20), applied as
  `value * (1 + delta)`.
- The engine is a standalone module with no IO: inputs arrive as a prepared
  parameter object and outputs are pure result dataclasses. See
  `apps/api/src/modules/simulator/engine.py`.

## 3. Boundaries — what the simulator is NOT

- **Not a source of truth for money.** Revenue, spend, CPA, ROAS, profit and
  orders always come from stored data through the KPI engine; the simulator
  only combines them with an assumed budget. It never reports actuals.
- **No probability or success ranking.** The engine returns deterministic
  estimates, never "likelihood of success"; the UI renders estimates and
  evidence strength, never a success score.
- **No execution.** The simulator never writes to ad accounts, never creates
  campaigns, never changes budgets, and exposes no webhook triggers, job
  queues, or scheduling.
- **No LLM involvement.** LLMs are not part of the calculation path; they
  never produce KPI values (see AGENTS.md "AI" section).

## 4. Data flow (read-only inputs)

```
HTTP /api/v1/businesses/{business_id}/simulations
  → router (auth: business:read, tenancy: business access)
  → service.simulate (loads data only, besides persisting the run)
    → inputs assembly
      · datetime/window provider  (kpi_engine time windows)
      · campaigns repository     (only from the same business_id)
      · ads / adsets / products  (ad-account history, business history)
      · unit economics           (business row economics)
    → engine → scenario/sensitivity/break-even/targets
  → persistence (simulations + assumptions snapshots)
  → Pydantic response schemas
```

Every data source is filtered by `organization_id`/`business_id` before any
use; a simulation can never be built from cross-tenant data because the
lookup layer never sees it.

## 5. Historical window semantics

- `historical_window_days` is required and must be one of the allowed
  windows: 7, 14, 30, 60, 90. Anything else returns 422.
- The window defines the *look-back* for assumptions derived from history
  (CTR, CPC, CVR, AOV, refund rate, ...) and the observation counting
  interval used for data quality.
- `duration_days` (1–90, default 30) defines how many future days the spend
  is simulated over; it does not change which historical data is read.
- Only observations with stored `occurred_on` inside the window count;
  observation counts and data-quality/evidence assessment derive directly
  from those observations.

## 6. Assumption resolution order (provenance)

Each assumption is resolved from the first non-null candidate in this
priority order, which is stored on the returned assumption row as `source`:

1. `user_input` — overrides supplied in the request
2. `campaign_history` — campaign metric observations (when the entity is a
   campaign, or campaign grain is the strongest available)
3. `ad_account_history` — ad account rollups
4. `business_history` — business-level metric observations
5. `economics` — unit economics from the business record
6. `goal` — target values (used only where no empirical fallback exists)
7. `system_default` — documented constants when no data exists

`historical_value` is always the value that would have been used had the
winner not overridden it; `override` is true exactly when the request
supplied a value for that assumption. `assumptions_hash` covers the
serialized assumption set plus the model version so identical input sets are
recognizable later.

## 7. Unit economics

The engine multiplies funnel quantities by fixed cost and margin components,
all read from the business's economics record (never invented):

- `shipping_cost`, `payment_fees` — subtracted per order
- `contribution_margin` — applied to revenue to derive contribution profit
- `refund_rate` — reduces expected revenue to net revenue
- AOV, break-even and margin values derive from these stored numbers, never
  from free parameters.

## 8. Funnel math (mapping spend → results)

The engine computes, in order: impressions (spend / CPM), clicks
(impressions × CTR), purchases (clicks × CVR), revenue (purchases × AOV),
net revenue (after refunds), contribution profit
(revenue × margin − shipping − fees), then the derived KPIs ROAS
(revenue / spend), CPA (spend / purchases), MER (revenue / spend) and the
per-unit rates CTR, CVR, CPC, CPM — all in Decimal. When a denominator is
zero or a component is missing, the affected metric is emitted as `null`
and rendered as unavailable, never as zero.

## 9. Scenarios

The engine produces three scenarios per run: `downside`, `expected` and
`upside`. Each contains `available`, `reason` (when unavailable) and the full
metric set from section 8. `expected` is the base run; `downside`/`upside`
apply the fixed multipliers. A scenario may be `available: false` when the
evidence base is too thin — the UI then shows the reason, and never shows
zeros for the unavailable scenario.

## 10. Sensitivity analysis

For each variable in `SENSITIVITY_STEPS` (−20%, −10%, −5%, 0, +5%, +10%,
+20%) the engine re-runs the funnel with `value * (1 + delta)` and records
`new_value`, revenue, profit, CPA and ROAS per row. Rows are pure backend
outputs; the frontend renders them without any calculation.

## 11. Break-even analysis

From unit economics, the engine derives thresholds that keep the run at
zero contribution profit: `break_even_cpa`, `break_even_roas`, `minimum_cvr`,
`maximum_cpc`, `minimum_aov`, `maximum_cpa`, `minimum_roas`, and compares
them against the simulated values (`simulated_cpa`, `simulated_roas`).

## 12. Targets and status

Optional request targets (`target_cpa`, `target_roas`, `target_revenue`,
`target_profit`) are compared against the simulated values. Each target row
carries `metric_code`, `target_value`, `simulated_value`, and a `status` of
`met` / `not_met` (or unavailable when the simulated metric is unavailable).

## 13. Data quality and evidence

- `data_quality` is one of `strong` / `moderate` / `weak` / `insufficient`,
  computed from observation counts inside the chosen window.
- `evidence_strength` reflects both the data quality and the resolution of
  each assumption (how many non-default sources produced values).
- The UI renders both as badges; a run with insufficient evidence still
  returns full JSON but must not be presented as confident.

## 14. Overrides and re-runs

- `overrides` (SimulationOverrideInput) accepts: budget, ctr, cpc, cpm,
  cvr, aov, refund_rate, contribution_margin, shipping_cost, payment_fees.
- `POST /simulations/{id}/rerun` re-executes the engine with the stored
  request payload (so changed business data can be re-evaluated) and
  persists a new run.
- The client sends override values with the request; it never computes
  results locally (see the frontend contract in section 17).

## 15. API endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/v1/businesses/{bid}/simulations` | history summary (latest snapshots) |
| POST | `/api/v1/businesses/{bid}/simulations` | create + run (business scope) |
| GET | `/api/v1/businesses/{bid}/simulations/{sid}` | one persisted run |
| POST | `/api/v1/businesses/{bid}/simulations/{sid}/rerun` | re-run with stored inputs |
| POST | `/api/v1/businesses/{bid}/campaigns/{cid}/simulate` | create + run at campaign scope |

All endpoints require the `business:read` permission and validate business
access from the authenticated tenant; unknown business, campaign or
simulation IDs return 404 (never 403 for cross-tenant resource ids).

## 16. Serialization rules

- Money (budget, revenue, profit, spend, CPA, AOV, break-even fields) is
  serialized as Decimal strings; counts (impressions, clicks, purchases)
  as numbers; rates (CTR, CVR, refund rate) as Decimal fraction strings;
  ROAS/MER as Decimal multiplier strings.
- Request amounts (budget, targets, overrides) accept number or decimal
  string forms and are normalized to Decimal server-side.
- The API contract is generated into `packages/shared-types` via
  `infra/scripts/generate-types.sh` — never hand-edited.

## 17. Frontend contract

The web feature (`apps/web/src/features/simulator/`) is a read/write view
over these endpoints:

- Fetch-only display of all computed values; no client-side simulation
  arithmetic, no success scores, no probability rendering.
- Unavailable scenarios are shown as unavailable with their reason — never
  as zeros — and sensitivity/break-even/target tables only display backend
  values.
- Overrides are sent with the request; the client never computes results.
- History rows open a stored snapshot or trigger a re-run; neither touches
  ad accounts or budgets.
- All strings are i18n keys in `messages/{en,ar}/simulator.json`
  (105 keys, exact parity); technical metric acronyms (CTR, CPC, CPM, CPA,
  CVR, AOV, ROAS, MER) are not translated.

## 18. Testing

- Backend: `apps/api/tests/test_simulator_engine.py` and
  `test_simulator_api.py` (30 tests) cover determinism, money precision,
  scenario math, sensitivity deltas, break-even math, target statuses,
  data quality, overrides, rerun semantics, tenancy isolation and 404s.
- Frontend: `src/features/simulator/*.test.tsx` (35 tests) cover loading /
  empty / error states, scenario rendering (unavailable ≠ zero), assumption
  editor (sources, confidence, overrides), sensitivity display, history
  open/rerun, campaign-scope runs, and both locales.
- All tests run in CI; financial assertions use Decimal math only.

## 19. Known limitations and future work

- Scenario and sensitivity deltas are fixed constants; adaptive ranges are
  future work and must remain deterministic.
- Evidence strength is rule-based; statistical confidence intervals for
  scenarios are future work (Phase 5/6) and stay out of the LLM path.
- Campaign-scope runs depend on campaign metrics being present in the
  window; campaigns without data surface a clear empty state.
- No A/B trade-off analysis between two budgets yet — out of scope for 5A.

## Related documents

- `docs/architecture/overview.md` — system overview and API surface
- `docs/architecture/metrics.md` — KPI engine that produces the inputs
- `docs/architecture/forecasting.md` — deterministic forecast engine
- `docs/architecture/recommendations.md` — review-only decision engine
- `AGENTS.md` — engineering rules (determinism, Decimal, no LLM metrics)