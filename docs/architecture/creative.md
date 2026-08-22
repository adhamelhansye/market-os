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
