# Unit Economics

## Purpose

MarketingOS computes deterministic unit economics — contribution profit, break-even
CPA/ROAS, target CPA, inventory value — from product pricing, cost history, shipping
rules and discounts. This is the foundation for the economics dashboard, forecasts
and, later, campaign recommendations.

## Principles

- **Money is never floating point.** All money fields are `NUMERIC` in
  PostgreSQL and `Decimal` in Python; API bodies serialize them as strings.
- **The calculator is pure.** `src/modules/economics/calculator.py` has no
  database access and no LLM logic: services pass it the exact records to use.
- **No silent division by zero.** `_divide` returns `None` when the denominator
  is zero; `break_even_roas` is `None` when contribution profit is not positive.
- **Quantization is explicit.** Money output is quantized to 2 decimals,
  margins/ROAS to 4 decimals. JSON responses never leak `Decimal` internals.
- **The LLM never invents numbers.** Numerical metrics come only from this
  deterministic layer; AI handles reasoning and recommendations on top.

## Metric glossary

All formulas model a single order of a single product (quantity 1), with the
currently effective price and cost records.

| Metric | Formula | Notes |
| --- | --- | --- |
| product_revenue | product price charged to the customer | |
| shipping_revenue | shipping price charged to the customer | |
| total_customer_revenue | product_revenue + shipping_revenue | AOV basis |
| product_cost | cogs + packaging_cost | |
| payment_fees | payment_fee_fixed + product_revenue × payment_fee_percent / 100 | percent is basis points on price |
| discount_amount | percentage: min(price × value/100, maximum_discount); fixed: min(value, maximum_discount) | gated by minimum_order_value; capped at product_revenue |
| contribution_profit | product_revenue − product_cost − payment_fees − shipping_cost + shipping_revenue − discount_amount | quantized to 0.01 |
| contribution_margin | contribution_profit / total_customer_revenue | None when revenue is zero |
| break_even_cpa | contribution_profit | max ad spend per order before the order loses money |
| break_even_roas | total_customer_revenue / contribution_profit | None when profit ≤ 0 |
| target_cpa | break_even_cpa − desired_profit_per_order | None unless a desired profit assumption is provided |

## Which records are used

Record resolution lives in `src/modules/economics/service.py` ("effective
pricing"):

- **Price** and **cost**: the record with the latest `effective_from` that is
  `<=` the calculation date and not `effective_to`-terminated. Open-ended
  periods (no `effective_to`) are active until superseded; a newer open period
  may legally follow an older open period — the latest `effective_from` wins.
- **Shipping**: the business's default shipping rule (`is_default = true`).
- **Discount**: the single discount enabled for the business at calculation
  time (1 discount per period to keep results deterministic).
- **Goal**: the current goal is the one whose period contains "now".

## Summary aggregates

The business-level summary is built over **priced products** — products that
have an effective price AND an effective cost:

- `average_product_price`, `average_contribution_profit`,
  `average_contribution_margin` — simple averages (unweighted).
- `break_even_cpa_range` — [min, max] of per-product break-even CPAs.
- `break_even_roas` — total_customer_revenue / total contribution profit over
  all priced products; `None` when aggregate profit ≤ 0.
- `inventory_value` — sum of effective unit price × inventory quantity over
  products with inventory; always `"0.00"`-quantized, never a bare `"0"`.
- `current_goal` — the goal whose period contains now, if any.

## Rate limits and safety

- `SUM`/averages run in Python over loaded rows (pagination is per-business;
  product counts are small), keeping arithmetic fully deterministic.
- All queries are organization-scoped via `CurrentBusinessId`; the calculator
  receives only records already validated as belonging to the business.

## Tests

- `tests/test_calculator.py`, `tests/test_pricing_costs.py`,
  `tests/test_shipping.py`, `tests/test_discounts.py`, `tests/test_goals.py`,
  `tests/test_bundles.py`, `tests/test_inventory.py`,
  `tests/test_economics.py` — formula, resolution and endpoint level.
- Every meaningful rule above has a test; changing a formula requires updating
  the corresponding expectations (never delete tests to make them pass).