# Deterministic Strategy Module (Phase 7)

The strategy module produces **structured strategy artifacts** — positioning,
offers, decisions and messaging — deterministically from stored research,
economics and business data. It never queries a provider, never invokes an
LLM, and never invents numerical metrics: every value either comes from a
stored record (evidence, positioning candidate, offer candidate, product,
research intelligence snapshot) or is labeled with an explicit classification
and strength. The LLM may later *consume* these artifacts (e.g. writing
copy), but it must never be their source of truth.

## Scope

- `positioning` — positioning candidates (who/problem/solution/differentiator/
  promise) derived from research evidence and knowledge gaps. Deterministic
  scoring and recommendation.
- `offers` — offer candidates (product, pricing, contribution economics,
  break-even CPA/ROAS) validated against canonical unit economics.
- `decisions` — deterministic evaluation of candidates against goals,
  performance, forecasts and simulations (`strategy_decision_v1`).
- `messaging` — message components, angles, objection responses, claim
  validation, prioritization and competitor-messaging analysis
  (`messaging_v1`), all anchored one-to-one in evidence rows.

### Messaging (Phase 7B)

`POST /api/v1/businesses/{business_id}/strategy/messaging/generate` builds a
message strategy version from the latest positioning/offer/decision and the
latest research intelligence snapshot:

- **Components** (`MessageComponent`): one row per evidence entry, mapped
  deterministically by `_EVIDENCE_COMPONENTS` (pain_point/complaint →
  problem/pain, desire → desire, benefit → benefit, feature → feature,
  objection → objection, review/trust_signal → proof), plus positioning
  derived components (differentiator, promise, proof_points) and a CTA
  component only when an available action exists (`cta_type = view_product`
  only if the offer references a real product). Classification comes from
  the evidence (`observed`/`inferred`/`hypothesis`) or from the positioning
  candidate; the vocabulary observed/inferred/hypothesis/claimed/validated/
  unsupported is never silently promoted.
- **Objection responses** are always the strongest stored proof statement
  (`details.response`, `response_available`, `response_provenance`); a
  generic "guarantee" is never invented.
- **Unsupported claims** are flagged per component against a fixed
  vocabulary (`_UNSUPPORTED_CLAIM_WORDS`), recorded in
  `details.unsupported_claims` and aggregated in `quality.unsupported_claims`
  — they are never removed or promoted silently.
- **Claim status** per component: `supported` / `partially_supported` /
  `unsupported` / `unknown`, derived from classification and evidence
  strength with named constants.
- **Prioritization** (`quality.prioritization`): deterministic weighted
  scoring per component using named constants
  (`PRIORITY_WEIGHTS`: customer_relevance .25, evidence_strength .20,
  positioning_alignment .15, offer_alignment .15, proof_strength .10,
  differentiation .10, stage_relevance .05), sorted descending with ranks;
  `prioritization_rules_version` is recorded in the snapshot.
- **Angles** (`MessageAngle`): generated per component type
  (`_ANGLE_RULES` → problem_led, pain_led, desire_led, benefit_led,
  differentiator_led, proof_led, objection_led, offer_led) with hook
  *directions* only — never ad copy. Status is always
  `no_performance_attribution`; funnel stages are attached per component
  type (awareness/interest/consideration/purchase) without implementing
  Funnel Strategy.
- **Competitor analysis** (`quality.competitor_messaging`): pattern
  frequency and saturation from stored competitor records (min sample 3,
  `common` ≥ 50%, `moderately_common` ≥ 25%, else `rare`/`unknown`),
  competitor ids, and whitespace detection from customer evidence themes
  not covered by competitor patterns — always emitted as `hypothesis` with
  `whitespace_claim: "no_performance_claim"`.
- **Core message** (`core_message`): who/problem/desired_outcome/solution/
  differentiator/promise/proof_available/cta; missing required fields
  (`who`/`problem`/`solution`/`promise`) yield status `insufficient_data`,
  otherwise `draft`.
- **Versioning & snapshots**: each generate creates a new version
  (`messaging_v1`) with an immutable `input_snapshot` (positioning/offer/
  decision ids, research intelligence snapshot id + version, evidence ids,
  rules versions). `GET .../messaging` returns the latest version,
  `.../messaging/versions` all versions, `.../messaging/{id}/provenance`
  the provenance chain.

## Safety rules

- No LLM output is ever persisted as a strategy value; no money/performance
  figures are invented (`quality.performance_attribution` is always
  `no_performance_attribution`; retention directions are classification
  `hypothesis` only).
- Every record carries `organization_id` + `business_id`; all reads and
  writes revalidate tenancy server-side, cross-tenant/unknown ids yield 404,
  and mutations require `business:write` (`business:read` for reads).
- Positioning/offer/messaging endpoints never mutate external systems.

## API surface

All endpoints live under `/api/v1/businesses/{business_id}/strategy/`:
positioning (GET/POST candidates/recommend), offers (GET/POST candidates/
validate/recommend), summary, snapshot, decisions (GET/evaluate),
messaging (GET/generate/versions/{id}/provenance). Request/response
contracts are explicit Pydantic schemas; internal ORM models are never
exposed (see `src/modules/strategy/schemas.py` and `router.py`).

## Testing

`apps/api/tests/test_strategy.py` covers candidate creation, deterministic
scoring, tenancy isolation, RBAC, decision evaluation and the messaging
rules: objection severity + proof responses, unsupported-claim flagging,
competitor saturation and whitespace, deterministic prioritization and
versioning, CTA availability, snapshot/provenance references, and
insufficient-data status. Frontend coverage lives in
`apps/web/src/features/strategy/strategy-section.test.tsx` (en/ar).
