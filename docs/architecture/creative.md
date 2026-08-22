# Creative intelligence (Phases 8A–8D)

Deterministic creative concept, testing, performance and learning layers.
Creative defines **what and why**; performance records **what happened**;
learning records **what was observed to be associated** — nothing here
generates assets, executes actions or claims causation.

## Phase stack

| Phase | Scope | Persistence |
|---|---|---|
| 8A | Creative concepts, briefs, matrix, risks, evidence, snapshots, provenance | `creative_*` tables (migration 0017) |
| 8B | Creative strategies, tests, variants, portfolios, coverage/diversity | `creative_*` tables (migration 0018) |
| 8C | Performance observations, signals, fatigue, classification, scaling readiness | `creative_performance_links`, `creative_performance_snapshots` (0019) |
| 8D | Learning hierarchy: patterns, learnings, recommendations | `creative_learning_snapshots` (0020) |
| 8E | Optimization plan: gated opportunities, blocked list, coverage/concentration analysis | `creative_optimization_snapshots` (0021) |
| 8F | Decision plan assembly + human review state (review-only) | `creative_decision_plans`, `creative_decision_item_reviews` (0022) |

## Data flow (Phase 8C → 8D)

```
metric_facts (ad-grain canonical facts)
  → creative_performance_links   (explicit user-authored attribution)
  → per-entity observations      (Phase 8C service)
  → signals / fatigue / classification / readiness   (pure 8C engine)
  → OBSERVATION → SIGNAL → PATTERN → LEARNING → RECOMMENDATION
                                                 (pure 8D engine)
  → creative_learning_snapshots  (immutable, fingerprint-keyed)
```

The 8D engine consumes 8C outputs verbatim. It never re-derives CTR/CPC/
CPM/CPA/ROAS, never reads providers, and never distributes business-level
commerce revenue to creatives. Conversion-based ratios keep their
`meta_reported` provenance label.

## Learning hierarchy

- **OBSERVATION** — a linked entity's Phase 8C result set.
- **SIGNAL** — directional association of a metric vs the in-scope Decimal
  baseline mean (deadband `trend_deadband_percent`; lower-is-better metrics
  inverted). States: positive / negative / neutral / insufficient.
- **PATTERN** — entities grouped by dimension value (`angle`,
  `hook_direction`, `creative_format`, `funnel_stage`). Status ladder,
  first match wins:
  `conflicting → stale → insufficient_data → stable → supported → emerging`.
  Gates: `learning_min_entities`, conflict ratio `learning_conflict_ratio`,
  staleness `learning_stale_days`.
- **LEARNING** — deterministic template statements over observed counts.
  Association language only ("is associated with stronger observed CTR …
  not causal"). Insufficient patterns produce no learning.
- **RECOMMENDATION** — bounded types (`expand_angle`, `explore_more`,
  `test_new_hook`, `test_new_format`, `refresh_creative`,
  `investigate_fatigue`, `reduce_concentration`,
  `investigate_conflicting_evidence`, `improve_coverage`,
  `gather_more_evidence`). Priority is a named-weight Decimal sum
  (`priority_weight_*`) bucketed high/medium/low. Every recommendation is
  `review_only: true` with no action payload.

### Conflicting evidence (never averaged)

When a dimension value has materially contradicting members (minority share
≥ conflict ratio) the pattern status is `conflicting` and the report carries
both supporting and contradicting entity ids plus the resolution path — more
sufficiently observed creatives of that value.

## Provenance

Every profile carries its Phase 8C provenance chain:

```
entity → provider object → campaign → test → strategy/funnel/messaging/
positioning/offer references
```

Snapshots embed a `provenance_index` mapping entity ids to chains. Missing
references are rendered as unavailable states, never fabricated.

## Snapshots & versioning

- One row per distinct input fingerprint (`business_id`, range, rules
  versions, entity set). Recompute returns the existing row (idempotent).
- Rules stamp: `clearning-v1` (`CREATIVE_LEARNING_RULES_VERSION`).
- Payload is JSON-safe (Decimals serialized as strings).
- Reads serve the latest snapshot; before any generation the API returns an
  explicit `no_snapshot` state.

## API

All under `/api/v1/businesses/{business_id}/strategy/creative/learning`:

| Method | Path | Permission |
|---|---|---|
| POST | `/generate` | `business:write` |
| GET | `/summary` | `business:read` |
| GET | `/patterns` · `/learnings` · `/recommendations` · `/profiles` | `business:read` |
| GET | `/snapshots` · `/snapshots/{id}` | `business:read` |

## Boundaries

No LLMs, no asset generation, no campaign/budget/bid/provider mutations, no
autonomous execution, no probability-of-success scores, no winner
predictions, no causal claims, no client-side financial calculations.
Recommendations are informational review inputs only.

## Phase 8E — Optimization Intelligence

Consumes the latest Phase 8D snapshot (or computes learning fresh when
none exists), Phase 8C fatigue/classification evidence and Phase 7
strategy-context availability to produce a review-only optimization plan.

### Gates O1–O8

Named gates with explicit precedence for POSITIVE expansion types:
`O1 insufficient_data > O2 stale_data > O3 conflicting_evidence` block;
`O7 supported_pattern` enables. `O4 fatigue_signal`, `O5 concentration_risk`,
`O6 coverage_gap`, `O8 strategic_alignment` classify the other opportunity
categories. Blocked candidates are reported in `blocked_opportunities`
with their blocking gate — never dropped, never silently positive.

### Opportunity taxonomy

expand_supported_angle · test_new_angle · test_new_hook · test_new_format ·
refresh_fatigued_creative · reduce_angle_concentration ·
reduce_format_concentration · improve_funnel_coverage ·
improve_proof_coverage · improve_objection_coverage ·
investigate_underperformance · investigate_conflicting_evidence ·
gather_more_evidence · validate_offer_alignment · validate_message_alignment

### Plan states

unavailable → insufficient_data → investigate → test_ready / review_ready.
No "optimized"/"guaranteed" states exist.

### Scoring

Priority is a named-Decimal-weight sum (`opt_weight_*`,
`opt_penalty_contradiction`) bucketed high/medium/low. It is a
deterministic review-ordering score — explicitly NOT a probability of
success; every opportunity carries that disclaimer in its payload.

### API

`/api/v1/businesses/{business_id}/strategy/creative/optimization/` —
POST `/generate` (business:write); GET `/summary`, `/opportunities`,
`/blocked`, `/tests`, `/refresh`, `/coverage`, `/portfolio`, `/conflicts`,
`/snapshots`, `/snapshots/{id}` (business:read). Rules stamp: `copt-v1`.

## Phase 8F — Decision Plan & Human Review

Consumes the LATEST persisted Phase 8E snapshot verbatim — opportunities
are never recomputed, re-scored or re-gated. The pure engine copies each
non-blocked opportunity into a decision-plan item (adding only
`execution_status="not_executed"`, default `review_state="proposed"` and a
deterministic `suggested_review_focus` mapped from the 8E category).
Blocked opportunities remain an informational appendix (`actionable:
false`) and can never become items.

### Human review state

`creative_decision_item_reviews` is the repository's ONLY mutable
human-review table. States are strictly non-executional:
`proposed | acknowledged | dismissed | deferred` (CHECK-constrained).
Acknowledging means "a human reviewed this item" — nothing executes,
nothing is modified on any provider. Reviews key on the stable 8E
`opportunity_id` so they survive regeneration; each row preserves the
`source_plan_fingerprint` it was last made under. Review progress is
derived at read time and never written into the immutable plan payload.

### API

`/api/v1/businesses/{business_id}/strategy/creative/decision-plan/` —
POST `/generate` and POST `/items/{opportunity_id}/review`
(business:write); GET `/summary`, `/items`, `/blocked`, `/snapshots`,
`/snapshots/{id}` (business:read). Cross-tenant access → 404; viewer
writes → 403. Rules stamp: `cdecision-v1`.

### Boundary

No LLM, no asset generation, no campaign/provider/budget mutations, no
execution layer of any kind. The chain stops here:

Optimization Intelligence → Decision Plan → Human Review.
