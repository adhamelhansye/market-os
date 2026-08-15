"""Canonical metric definitions.

The single registry of metric codes the analytics layer understands:

- what each code means,
- which funnel stage it belongs to,
- which kind of value it is (count / money / rate),
- which providers can supply it as an *observed* fact (everything else is
  derived or unavailable — never silently zero).

Money is always Decimal (API serializes as string); counts are integers;
rates are Decimal ratios (0.0382 = 3.82%), formatted per locale by the
frontend without any arithmetic there.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

KIND_COUNT = "count"
KIND_MONEY = "money"
KIND_RATE = "rate"

FUNNEL_AWARENESS = "awareness"
FUNNEL_TRAFFIC = "traffic"
FUNNEL_INTENT = "intent"
FUNNEL_PURCHASE = "purchase"

SOURCE_COMMERCE = "commerce"
SOURCE_META_REPORTED = "meta_reported"
SOURCE_ECONOMICS = "economics"

# Provider identifiers shared with the integration layer.
PROVIDER_SHOPIFY = "shopify"
PROVIDER_META = "meta"


@dataclass(frozen=True)
class MetricDefinition:
    code: str
    kind: str
    funnel: str | None
    # Providers that can supply the metric as an observed fact.
    observed_by: tuple[str, ...] = ()


METRICS: dict[str, MetricDefinition] = {
    "impressions": MetricDefinition("impressions", KIND_COUNT, FUNNEL_AWARENESS, (PROVIDER_META,)),
    "reach": MetricDefinition("reach", KIND_COUNT, FUNNEL_AWARENESS, (PROVIDER_META,)),
    "clicks": MetricDefinition("clicks", KIND_COUNT, FUNNEL_TRAFFIC, (PROVIDER_META,)),
    "link_clicks": MetricDefinition("link_clicks", KIND_COUNT, FUNNEL_TRAFFIC, (PROVIDER_META,)),
    "landing_page_views": MetricDefinition(
        "landing_page_views", KIND_COUNT, FUNNEL_TRAFFIC, (PROVIDER_META,)
    ),
    "sessions": MetricDefinition("sessions", KIND_COUNT, FUNNEL_TRAFFIC),
    "product_views": MetricDefinition("product_views", KIND_COUNT, FUNNEL_INTENT),
    "add_to_cart": MetricDefinition("add_to_cart", KIND_COUNT, FUNNEL_INTENT),
    "checkout_started": MetricDefinition("checkout_started", KIND_COUNT, FUNNEL_INTENT),
    "purchases": MetricDefinition("purchases", KIND_COUNT, FUNNEL_PURCHASE, (PROVIDER_SHOPIFY,)),
    "revenue": MetricDefinition("revenue", KIND_MONEY, FUNNEL_PURCHASE, (PROVIDER_SHOPIFY,)),
    "spend": MetricDefinition("spend", KIND_MONEY, None, (PROVIDER_META,)),
    "refunds": MetricDefinition("refunds", KIND_MONEY, None, (PROVIDER_SHOPIFY,)),
    "cogs": MetricDefinition("cogs", KIND_MONEY, None),
    "shipping_cost": MetricDefinition("shipping_cost", KIND_MONEY, None),
    "payment_fees": MetricDefinition("payment_fees", KIND_MONEY, None),
    "conversions": MetricDefinition("conversions", KIND_COUNT, None, (PROVIDER_META,)),
    "conversion_value": MetricDefinition("conversion_value", KIND_MONEY, None, (PROVIDER_META,)),
}

# Derived KPI codes (computed by the engine, never observed).
KPI_CODES = (
    "ctr",
    "cpc",
    "cpm",
    "cvr",
    "cpa",
    "aov",
    "roas",
    "mer",
    "contribution_margin",
    "break_even_roas",
)

# Funnel stages in order (only stages with an observed provider are ever
# rendered; nothing is inferred between stages).
FUNNEL_STAGES = (
    "impressions",
    "clicks",
    "landing_page_views",
    "sessions",
    "product_views",
    "add_to_cart",
    "checkout_started",
    "purchases",
)

# Rounding policy: everything computes at full Decimal precision and is
# quantized only at the output boundary.
PRECISION_MONEY = Decimal("0.01")
PRECISION_RATE = Decimal("0.0001")
PRECISION_PERCENT = Decimal("0.01")


def require_metric(code: str) -> MetricDefinition:
    try:
        return METRICS[code]
    except KeyError:
        from src.modules.metrics.errors import UnknownMetricError

        raise UnknownMetricError(f"Unknown metric code: {code}") from None


def observed_providers(code: str) -> tuple[str, ...]:
    return require_metric(code).observed_by
