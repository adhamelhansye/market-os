"""Typed API contracts for the metrics endpoints.

Every KPI is a `MeasureRead` {value, status, reason}; money measures add
{currency, source}. Money is Decimal (serialized as strings by the app
encoder) — never float. `value` is NULL for anything that is not
`available`; zero and unavailable are never conflated.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class RangeRead(BaseModel):
    kind: str
    start: date
    end: date
    previous_start: date | None = None
    previous_end: date | None = None


class MeasureRead(BaseModel):
    value: Decimal | None = None
    status: str = "unavailable"
    reason: str | None = None


class CountMeasureRead(BaseModel):
    """Count-typed measure: value is an integer, never a Decimal string."""
    value: int | None = None
    status: str = "unavailable"
    reason: str | None = None


class MoneyMeasureRead(MeasureRead):
    currency: str | None = None
    source: str | None = None


class ComparisonRead(BaseModel):
    current: Decimal | None = None
    previous: Decimal | None = None
    absolute_change: Decimal | None = None
    percentage_change: MeasureRead | None = None


class SummaryRead(BaseModel):
    business_id: uuid.UUID
    currency: str
    timezone: str
    range: RangeRead
    revenue: MoneyMeasureRead
    spend: MoneyMeasureRead
    purchases: CountMeasureRead
    refunds: MoneyMeasureRead
    impressions: CountMeasureRead
    reach: CountMeasureRead
    clicks: CountMeasureRead
    link_clicks: CountMeasureRead
    landing_page_views: CountMeasureRead
    conversions: CountMeasureRead
    ctr: MeasureRead
    cpc: MoneyMeasureRead
    cpm: MoneyMeasureRead
    cvr: MeasureRead
    cpa: MoneyMeasureRead
    aov: MoneyMeasureRead
    roas: MeasureRead
    mer: MeasureRead
    contribution_profit: MoneyMeasureRead
    contribution_margin: MeasureRead
    break_even_cpa: MoneyMeasureRead
    break_even_roas: MeasureRead


class TimeseriesPoint(BaseModel):
    date: date
    spend: Decimal | None = None
    revenue: Decimal | None = None
    purchases: int | None = None
    clicks: int | None = None
    impressions: int | None = None
    conversions: int | None = None
    conversion_value: Decimal | None = None
    ctr: Decimal | None = None
    cpa: Decimal | None = None
    roas: Decimal | None = None
    mer: Decimal | None = None
    contribution_profit: Decimal | None = None


class TimeseriesRead(BaseModel):
    business_id: uuid.UUID
    currency: str
    timezone: str
    range: RangeRead
    points: list[TimeseriesPoint]


class FunnelStage(BaseModel):
    metric: str
    value: int | None = None
    status: str = "unavailable"
    reason: str | None = None
    conversion_rate: MeasureRead | None = None
    dropoff_rate: MeasureRead | None = None


class FunnelRead(BaseModel):
    business_id: uuid.UUID
    range: RangeRead
    stages: list[FunnelStage]


class EntityMetrics(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str | None = None
    status: str | None = None
    impressions: int | None = None
    reach: int | None = None
    clicks: int | None = None
    link_clicks: int | None = None
    landing_page_views: int | None = None
    spend: Decimal | None = None
    conversions: int | None = None
    conversion_value: Decimal | None = None
    # Revenue available to this grain: Meta-reported, never commerce.
    revenue_source: str | None = None
    ctr: MeasureRead | None = None
    cpc: MoneyMeasureRead | None = None
    cpm: MoneyMeasureRead | None = None
    cvr: MeasureRead | None = None
    cpa: MoneyMeasureRead | None = None
    aov: MoneyMeasureRead | None = None
    roas: MeasureRead | None = None


class CampaignMetrics(EntityMetrics):
    campaign_id: uuid.UUID | None = None
    ad_account_id: uuid.UUID | None = None


class CampaignsRead(BaseModel):
    business_id: uuid.UUID
    currency: str
    timezone: str
    range: RangeRead
    campaigns: list[CampaignMetrics]


class AdSetMetrics(EntityMetrics):
    ad_set_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None


class AdSetsRead(BaseModel):
    business_id: uuid.UUID
    currency: str
    timezone: str
    range: RangeRead
    campaign_id: uuid.UUID | None = None
    ad_sets: list[AdSetMetrics]


class AdMetrics(EntityMetrics):
    ad_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    ad_set_id: uuid.UUID | None = None


class AdsRead(BaseModel):
    business_id: uuid.UUID
    currency: str
    timezone: str
    range: RangeRead
    campaign_id: uuid.UUID | None = None
    ad_set_id: uuid.UUID | None = None
    ads: list[AdMetrics]


class ProductMetrics(BaseModel):
    product_id: uuid.UUID | None = None
    name: str | None = None
    sku: str | None = None
    units: int | None = None
    revenue: Decimal | None = None
    refunds: Decimal | None = None
    cogs: Decimal | None = None
    contribution_profit: Decimal | None = None
    contribution_margin: MeasureRead | None = None
    aov: MoneyMeasureRead | None = None


class ProductsRead(BaseModel):
    business_id: uuid.UUID
    currency: str
    timezone: str
    range: RangeRead
    products: list[ProductMetrics]


class ProviderQuality(BaseModel):
    provider: str
    connected: bool
    last_synced_at: str | None = None
    last_successful_sync_at: str | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None
    covered_days: int | None = None
    missing_days: int | None = None
    freshness_status: str = "unavailable"
    reason: str | None = None


class DataQualityRead(BaseModel):
    business_id: uuid.UUID
    timezone: str
    range: RangeRead
    providers: list[ProviderQuality]


class ComparisonReadResponse(BaseModel):
    business_id: uuid.UUID
    currency: str
    timezone: str
    range: RangeRead
    revenue: ComparisonRead
    spend: ComparisonRead
    purchases: ComparisonRead
    roas: ComparisonRead
    mer: ComparisonRead
    cpa: ComparisonRead
    aov: ComparisonRead
    ctr: ComparisonRead
    contribution_profit: ComparisonRead
