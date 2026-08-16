# Deterministic Forecasting Engine — Architecture & API

## Overview

The Deterministic Forecasting Engine (Phase 4A) provides statistical forecasts for marketing KPIs using only canonical metrics data (Phase 3A) and unit economics (Phase 1). It never uses LLMs, simulators, or autonomous actions.

### Design Principles

- **Backend is the source of truth**: All forecast math runs server-side in Python. The frontend only formats and displays backend values.
- **Deterministic**: Same inputs → same outputs. No random seeds, no LLM variability.
- **Statistically sound**: Model selection via backtested sMAPE (zero-safe), with MAE tie-break. Confidence intervals from residual stddev × z-score table.
- **Explicit gaps**: Missing dates are materialized as `null`, never as zero.
- **Derived KPIs only when both sides exist**: CPA = spend/purchases, ROAS = revenue/spend, AOV = revenue/purchases, MER = biz_revenue/biz_spend. If either numerator or denominator is unavailable, the KPI is unavailable (never zero).
- **Campaign revenue only from Meta-attributed conversion_value**: Business commerce revenue is never distributed across campaigns.
- **Profit from Phase 1 economics**: `avg_contribution_profit × forecast_purchases`. Unavailable if economics missing.
- **Multi-tenant**: Every query scoped to business_id; cross-tenant access returns 404.
- **Idempotent persistence**: Unique constraint on `(org, business, entity_type, entity_id, metric_code, horizon, training_end, model_version)`.

---

## Backend Architecture

### Modules

```
apps/api/src/modules/forecasting/
├── constants.py          # Minimum history thresholds, horizons, model versions, statuses
├── errors.py             # ForecastingFilterError (422), ForecastingInputError (422), etc.
├── validation.py         # dense_series() → ValidatedSeries (gaps explicit)
├── models/
│   ├── baseline.py       # naive, moving_average, weighted_moving_average
│   ├── trend.py          # OLS linear trend (clamped ≥0, rejects degenerate residuals)
│   └── seasonality.py    # 7-day weekday buckets (min 28 days, fallback to MA)
├── backtesting.py        # Rolling holdout (30%, 7–30 days), sMAPE + MAE
├── confidence.py         # z-table (50–95%), interval() with non-negative clamp
├── scenarios.py          # flat / trend / seasonal scenario sets with totals
├── engine.py             # Orchestration: load → validate → backtest → select → scenarios → derive KPIs
├── service.py            # Persistence (upsert), summary(), generate(), campaign_forecast()
├── router.py             # 4 endpoints under /api/v1
├── schemas.py            # Pydantic request/response contracts
└── __init__.py
```

### Model Hierarchy (candidate order)

1. `naive` — last observed value
2. `moving_average` — 7-day SMA
3. `weighted_moving_average` — linear weights, 7-day window
4. `trend` — OLS per-day forecast (requires ≥14 obs, non-degenerate residuals)
5. `seasonal` — 7-day weekday buckets (requires ≥28 obs, fallback to MA)

Selection: backtest all candidates on same holdout (30% of training window, min 7, max 30 days). Pick lowest sMAPE; tie-break by MAE.

### Minimum History Thresholds

| Status | Observations |
|--------|--------------|
| `insufficient_data` | < 7 |
| `baseline` | ≥ 7 |
| `trend` | ≥ 14 |
| `seasonal` | ≥ 28 |

### Training Window

Auto-sized: `max(7*4, horizon*3, 60)`, capped at 180 days. Ends day before forecast start. Forecast start = business-local today.

### Derived KPIs (engine.py)

```python
derived_cpa(spend, purchases)      # only when both available & purchases > 0
derived_aov(revenue, purchases)    # business grain only
derived_roas(revenue, spend)       # only when both available & spend > 0
derived_mer(biz_revenue, biz_spend) # = derived_roas at business grain
derived_contribution_margin(profit, revenue)
```

Profit uses `avg_contribution_profit` from Phase 1 `summary_data()`:
```python
expected = avg_unit_profit * forecast_purchases
lower = avg_unit_profit * forecast_purchases_lower
upper = avg_unit_profit * forecast_purchases_upper
```

Unavailable if `avg_unit_profit` is None or revenue/purchases unavailable.

---

## API Endpoints

All under `/api/v1`, require `business:read` permission, scoped to `business_id` from path.

### `GET /businesses/{business_id}/forecast/summary`

**Query**: `horizon_days` (7, 14, 30, 60, 90; default 30)

**Response**: `ForecastSummaryRead`
- `business_id`, `currency`, `timezone`, `horizon_days`
- `forecast_start`, `forecast_end`, `training_start`, `training_end`
- `confidence_level` (Decimal, e.g., "0.80")
- `metrics[]`: `ForecastRead` for revenue, spend, purchases, profit
- `goals[]`: `GoalComparisonRead` (target, forecast, gap, gap_pct, status)
- `budget`: `BudgetComparisonRead` (budget, forecast_spend, utilization_pct, remaining, overrun)
- `scenario_totals`: `{metric_code: ScenarioTotalsRead{expected, lower, upper}}`

### `GET /businesses/{business_id}/forecast`

**Query**: `horizon_days`, `metric_code` (optional)

**Response**: `ForecastWithPointsRead[]` — latest persisted forecasts with daily points for charting.

### `POST /businesses/{business_id}/forecast/generate`

**Body**: `ForecastGenerateRequest`
- `horizon_days` (7, 14, 30, 60, 90)
- `entity_type` ("business" | "campaign")
- `entity_id` (UUID, required for campaign)
- `metric_code` (optional, restrict to one)
- `confidence_level` (Decimal, 0–1, default 0.80)
- `training_window_days` (optional, max 180)

**Response**: `ForecastWithPointsRead[]` — newly generated/updated forecasts.

Idempotent: same `(business, entity, metric, horizon, training_end, model_version)` upserts.

### `GET /businesses/{business_id}/campaigns/{campaign_id}/forecast`

**Query**: `horizon_days` (default 30)

**Response**: `CampaignForecastRead`
- `campaign_id`, `horizon_days`, `forecast_start/end`, `training_start/end`
- `confidence_level`
- `spend`, `purchases`, `revenue`: `ForecastRead` or `null`
- `cpa`: `ForecastValueMoneyRead` (currency, source) or `null`
- `roas`: `ForecastValueRead` or `null`
- `data_sufficiency`: "available" | "insufficient_data"
- `break_even_roas`: always `null` (placeholder)
- `scenarios`: `{metric_code: ScenarioTotalsRead}`

Auto-generates if no persisted snapshot exists.

Campaign revenue only when Meta `conversion_value` exists at campaign grain.
CPA/ROAS only when both numerator and denominator available.

---

## Response Shapes (Key Types)

```typescript
// ForecastRead
{
  id: UUID,
  organization_id: UUID,
  business_id: UUID,
  entity_type: "business" | "campaign",
  entity_id: UUID | null,
  metric_code: "revenue" | "spend" | "purchases" | "profit",
  horizon_days: 7 | 14 | 30 | 60 | 90,
  forecast_start: "YYYY-MM-DD",
  forecast_end: "YYYY-MM-DD",
  training_start: "YYYY-MM-DD",
  training_end: "YYYY-MM-DD",
  model: "naive" | "moving_average" | "weighted_moving_average" | "trend" | "seasonal" | "profit_derived",
  model_version: "1.0.0",
  confidence_level: "0.80",
  expected_value: "12345.67" | null,
  lower_value: "12345.67" | null,
  upper_value: "12345.67" | null,
  observations_used: 90,
  missing_observations: 0,
  backtest_mae: "123.45" | null,
  backtest_smape: "12.34" | null,
  status: "current" | "stale" | "insufficient_data" | "failed" | "unavailable",
  reason: "insufficient_history" | "no_model" | "missing_economics" | "missing_revenue_or_purchases" | null,
  currency: "USD",
  source: "advertising" | "commerce" | "economics",
  created_at: "ISO8601",
  updated_at: "ISO8601"
}

// ForecastPointRead (daily)
{ date: "YYYY-MM-DD", expected_value: "100.00", lower_value: "80.00", upper_value: "120.00" }

// GoalComparisonRead
{ metric_code, target_value, forecast_value, gap, gap_percent, status: "available" | "unavailable", reason }

// BudgetComparisonRead
{ budget, forecast_spend, utilization_percent, remaining, overrun: boolean, status, reason }

// ScenarioTotalsRead
{ metric_code, expected: "10000.00", lower: "8000.00", upper: "12000.00" }
```

Money values are Decimal strings (never floats).

---

## Frontend Consumption

### API Client

`apps/web/src/features/forecasting/api.ts`
```typescript
fetchForecastSummary(businessId, horizonDays): Promise<ForecastSummaryRead>
fetchBusinessForecasts(businessId, horizonDays, metricCode?): Promise<ForecastWithPointsRead[]>
generateBusinessForecast(businessId, payload): Promise<ForecastWithPointsRead[]>
fetchCampaignForecast(businessId, campaignId, horizonDays): Promise<CampaignForecastRead>
```

Uses TanStack Query with keys:
- `["forecast-summary", businessId, horizon]`
- `["business-forecasts", businessId, horizon, metricCode]`
- `["campaign-forecast", businessId, campaignId, horizon]`

Invalidate on generate.

### Components

`apps/web/src/features/forecasting/forecast-section.tsx` — mounted in metrics page.

**Sections:**
1. **Forecast Controls** — horizon Select (7/14/30/60/90), triggers refetch.
2. **Revenue/Spend/Profit Forecast** — KPI cards with expected value.
3. **Scenario Summary** — Worst / Expected / Best (from `scenario_totals`).
4. **Confidence** — level, model, observations used.
5. **Goal Comparison** — revenue/profit goal vs forecast, gap, gap%.
6. **Budget Comparison** — budget vs forecast spend, utilization%, overrun flag.
7. **Campaign Forecast Table** — columns: Campaign, Current Spend, Forecast Spend, Current CPA, Forecast CPA, Current ROAS, Forecast ROAS, State, Confidence.

### No Client-Side Math

The frontend **never** calculates:
- `forecastRevenue = revenue * ...`
- `best = expected * 1.2`
- `cpa = spend / purchases`
- `roas = revenue / spend`

All values come from backend response.

### Unavailable States

| State | Display |
|-------|---------|
| `insufficient_data` | "Not enough historical data to generate a reliable forecast." |
| `stale` | "This forecast was generated from older data." |
| `failed` | "Forecast generation failed." |
| `unavailable` (profit) | "Unavailable — missing unit economics data." |
| `unavailable` (campaign revenue/ROAS) | "Unavailable — no Meta-attributed revenue at campaign grain." |

### Internationalization

Messages in `messages/en/forecasting.json` and `messages/ar/forecasting.json`. Registered in `i18n/messages.ts`. All user-facing strings use `useTranslations("forecasting")`.

Arabic: RTL, professional marketing terminology (e.g., "توقعات الإيرادات", "العائد على الإنفاق الإعلاني").

### Responsive Design

- Desktop: full grid layout
- Tablet: responsive grid (2-col)
- Mobile: stacked cards, horizontal scroll on campaign table

### Accessibility

- Charts: accessible labels, tooltips
- Tables: proper `<th>` headers
- Buttons: labels, loading states
- Loading: spinner + text, no layout shift
- Errors: not color-only

---

## Forecast Status Semantics

| Status | Meaning | Frontend Action |
|--------|---------|-----------------|
| `current` | Training window fresh (≤1 day old) | Show normally |
| `stale` | Training window older than 1 day | Show with "stale" badge |
| `insufficient_data` | < 7 observations in training window | Show "Insufficient data" message |
| `failed` | Generation error | Show error message |
| `unavailable` | Derived KPI missing inputs | Show "Unavailable" with reason |

---

## Campaign Attribution Limitations

Per Phase 3A:
- Campaign revenue = Meta `conversion_value` summed per day per campaign.
- If no `conversion_value` → `revenue = null`, `roas = null`, `cpa` still available if spend + purchases exist.
- **Never** distribute business commerce revenue across campaigns.
- **Never** infer campaign ROAS from business ROAS.

---

## Testing

### Backend
- `tests/test_forecasting.py` — 31 unit tests (validation, baselines, trend, seasonal, backtesting, confidence, scenarios, derived KPIs, goal/budget, horizon validation)
- `tests/test_forecasting_api.py` — 12 integration tests (summary, generate idempotency, horizon 422, 404s, points, insufficient_data, goal/budget, budget overrun, cross-tenant 404, unknown campaign 404, currency isolation)

Run: `pytest tests/test_forecasting.py tests/test_forecasting_api.py -v`

### Frontend
- Component renders with loading/error/empty states
- Horizon switching refetches
- Scenario values from backend
- Confidence interval display
- Goal/budget comparison
- Campaign table with unavailable states
- Arabic/English RTL/LTR
- No client-side forecast math (verified by code review)

Run: `npm run typecheck && npm run lint && npm run build`

---

## Security

- No secrets in forecast data
- No tokens in responses
- No cross-tenant data leakage (validated by `resolve_entity` in service)
- No campaign ID leakage (scoped to business)
- No currency conversion (backend aggregates in business currency only)
- No LLM, no simulator, no autonomous actions
- Decimal arithmetic throughout (no floats)

---

## Migration

Alembic migration `0007_forecasting.py` creates:
- `forecasts` table (unique idx on org+business+entity_type+entity_id+metric+horizon+training_end+model_version)
- `forecast_points` table (forecast_id + date unique)

Run: `alembic upgrade head`

---

## Future Extensions (Not Implemented)

- Simulator / what-if scenarios
- LLM-generated explanations
- Autonomous campaign actions (pause, budget change)
- Multi-currency consolidation
- Probabilistic forecasting (beyond symmetric scenarios)
- Seasonal decomposition beyond 7-day weekday