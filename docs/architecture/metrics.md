# Unified Metrics & Deterministic KPI Engine (Phase 3A)

Analytics for MarketingOS: every KPI the product reports is computed by a
deterministic engine over canonical provider facts. The engine never invents
numbers and never averages daily or per-campaign ratios.

## Pipeline

```
Provider data ──► Canonical facts ──► Aggregation ──► KPI engine ──► Analytics API ──► Dashboard
(adapter)         (orders /          (SQL over      (pure Decimal   (read-only)      (Next.js,
                  ad_insights,       metric_facts)   math, typed     /api/v1/...      Recharts)
                  migration 0006)                    measures)
```

- Providers write canonical facts only (Shopify orders, Meta ad insights).
- `metric_facts` is a UNION VIEW (migration 0006) over those tables — one
  source of truth, no sync step, nothing to diverge.
- Aggregation is SQL over the view (business, grain, date range, currency).
- The KPI engine is a pure module: no DB, no API, no LLM.

## Canonical facts view

The view emits one row per fact with provenance (`source_type`, `source_id`):

| Grain | Source | Meaning |
| --- | --- | --- |
| `ad` | `ad_insights` | Finest advertising grain (ingested at `level=ad`) |
| `business` | `orders` | One row per order: 1 purchase, `total` revenue, refund flag |
| `product` | `order_items` | One row per line: quantity purchased, line revenue |

Higher advertising grains (ad set / campaign / ad account) are rollups of
`ad` rows — never stored, never mixed with other grains in one aggregation
(mixing grains double-counts; tested against).

### Ad vs commerce facts

Meta-reported facts (`conversions`, `conversion_value` — all action types)
are exposed as columns distinct from commerce facts (`purchases`, `revenue`,
`refunds`). The two are never claimed identical and never mixed:

- **ROAS at ad/campaign/ad-set grain** = `conversion_value / spend`
  (Meta-attributed revenue, source label `meta_reported`).
- **MER (business level)** = commerce revenue / total ad spend
  (canonical Shopify orders, source `commerce`).
- Reconciliation between the two is deliberately not attempted.

## Zero vs unavailable

The most important contract in the layer. A measure is one of:

- **available** — the KPI was computed (zero is a valid computed value:
  CTR 0% with 1000 impressions and 0 clicks).
- **unavailable** — the system lacks the facts (no denominator, no
  numerator, no provider). The reason explains why. Never a fabricated zero,
  never Infinity.
- **insufficient_data** — the period has no facts at all (entity rollups).
- **invalid** — defensive rejection of negative inputs.

Rows that don't exist are `unavailable`, never zero: a day without facts
has no timeseries point; a business without orders has no revenue measure.
The frontend renders unavailable measures with their reason instead of a
number.

## KPI definitions

Period KPIs are ALWAYS computed from aggregated totals (total spend / total
purchases for CPA, ...). Averaging daily or per-campaign ratios is a bug and
is tested against: campaigns spending 100→ROAS 3 and 900→ROAS 1 give a
blended ROAS of 1.2, never 2.

| KPI | Formula | Precision (output) |
| --- | --- | --- |
| CTR | clicks / impressions | 4dp ratio |
| CPC | spend / clicks | money 2dp |
| CPM | spend / impressions × 1000 | money 2dp |
| CVR | purchases / clicks | 4dp ratio |
| CPA | spend / purchases | money 2dp |
| AOV | revenue / purchases | money 2dp |
| ROAS (ad grain) | Meta conversion_value / spend | 4dp ratio |
| MER | commerce revenue / spend | 4dp ratio |
| contribution margin | contribution profit / revenue | 4dp ratio |

Rounding: full Decimal arithmetic, quantized (`decimal.Decimal.quantize`)
only at the output boundary. Money is never a float anywhere — API responses
serialize Decimal as strings.

## Profitability

Contribution profit is derived by scaling the Phase 1 unit-economics profile
(`economics.service.summary_data`): `average_contribution_profit × purchases`.
No second formula exists. Break-even CPA and break-even ROAS come from the
same profile. Without configured unit economics these measures are
unavailable with "no unit economics configured".

## Purchase attribution

Commerce purchases are business-level facts (orders). Purchase-level KPIs
(CVR, CPA, AOV) at ad/campaign/ad-set grain are **unavailable** with reason
"no purchase attribution at this grain" — the layer does not invent
attribution. Product analytics (units, revenue, AOV per product) come from
order items; refunds, COGS, shipping and payment fees are not attributed to
products (unavailable, never zero).

## Funnel

Stages rendered, in order: impressions → clicks → landing page views →
purchases, with explicit unavailable stages for product views, add to cart
and checkout started (no provider reports them today). Conversion and
drop-off rates relate each stage to the one before it; the chain never
fabricates a path through unobserved stages. The funnel includes neither
`sessions` (not part of the purchase funnel) nor unknown metric codes.

## Timezone & currency

- All range math happens in the business timezone (`ZoneInfo`, fallback
  UTC): today, yesterday, last 7/14/30 days, month-to-date, custom.
- Every aggregation filters on the business currency: a EUR order is never
  summed into a USD total and never converted. Multi-currency businesses
  are out of scope (remaining issue).

## Data quality & freshness

`/metrics/data-quality` reports per provider: connected, last sync,
last successful sync (SyncRun `success`/`partial`), coverage window and
freshness — `fresh` (covers yesterday), `delayed` (syncs recent but lagging),
`stale` (no recent syncs, window from `metrics_stale_after_hours`),
`unavailable` (not connected / no facts).

## API

All endpoints under `/api/v1/businesses/{business_id}/metrics/*`, read-only,
`business:read` required, business resolved from the path with server-side
tenancy checks. Query params: `range_kind` (+ `start`/`end` for `custom`),
entity filters `campaign_id`/`ad_set_id` validated inside the authorized
business (unknown ids → 404). Responses are typed Pydantic models; every
measure carries `{value, status, reason}` and money adds `{currency, source}`.

| Endpoint | Purpose |
| --- | --- |
| `/summary` | Period KPIs (the full measure block) |
| `/timeseries` | Daily points (only days with facts) |
| `/funnel` | Stage values, conversion and drop-off rates |
| `/campaigns`, `/adsets`, `/ads` | Entity rollups (ad grain) |
| `/products` | Per-product units, revenue, AOV |
| `/data-quality` | Provider freshness |
| `/comparison` | Current vs previous period with absolute/percent change |

Percent change is unavailable (never fabricated) when the previous period
was zero or missing.

## Caching

Analytics are computed live per request (SQL aggregation is cheap); no Redis
cache layer was introduced — caching would only add invalidation state with
no measurable benefit at this stage. Freshness is evaluated live with every
request and reflects the last sync.

## Remaining issues

- Multi-currency businesses (conversion rules) — out of scope, EUR orders
  escluded from USD totals.
- Purchase attribution at ad grain — requires Meta Conversions API or
  server-side tagging (Phase 2C+).
- GA4/TikTok/Google Ads providers would extend the view with new fact rows.
- `summary_data` also returns the current goal which metrics don't display.