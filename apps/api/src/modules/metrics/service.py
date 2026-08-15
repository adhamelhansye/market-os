"""Metrics service.

Read-only orchestration over the canonical metrics layer. It:

- resolves ranges in the BUSINESS timezone (never the server timezone);
- aggregates canonical facts (aggregation.py) and runs them through the
  pure KPI engine (kpi_engine.py);
- reuses the Phase 1 unit-economics profile for profitability KPIs
  (no second formula is ever written);
- keeps revenue sources labelled (commerce vs Meta-reported) and never
  mixes them.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.db.models import Business, IntegrationConnection, SyncRun
from src.modules.economics.service import summary_data
from src.modules.metrics import aggregation
from src.modules.metrics.aggregation import Range
from src.modules.metrics.definitions import (
    PRECISION_MONEY,
    PROVIDER_META,
    PROVIDER_SHOPIFY,
)
from src.modules.metrics.errors import (
    BusinessNotFoundError,
    InvalidRangeError,
)
from src.modules.metrics.kpi_engine import (
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_UNAVAILABLE,
    Comparison,
    Measure,
    aov,
    contribution_margin,
    cpa,
    cpc,
    cpm,
    ctr,
    cvr,
    dropoff_rate,
    funnel_transition,
    mer,
    roas,
)
from src.modules.metrics.provenance import (
    REVENUE_SOURCE_COMMERCE,
    REVENUE_SOURCE_META_REPORTED,
)

_RANGE_KINDS = (
    "today",
    "yesterday",
    "last_7_days",
    "last_14_days",
    "last_30_days",
    "month_to_date",
    "custom",
)

# Metrics no current provider observes; rendered as unavailable (never zero).
_OBSERVED_METRICS = ("impressions", "clicks", "landing_page_views")
_UNOBSERVED_METRICS = ("product_views", "add_to_cart", "checkout_started")


class _RangeResolver:
    def __init__(self, timezone: str) -> None:
        try:
            self.tz = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            self.tz = ZoneInfo("UTC")
        self.today = datetime.now(self.tz).date()

    def resolve(self, kind: str, *, start: date | None = None, end: date | None = None) -> Range:
        if kind not in _RANGE_KINDS:
            raise InvalidRangeError(f"Unknown range kind: {kind}")
        today = self.today
        if kind == "custom":
            if start is None or end is None:
                raise InvalidRangeError("Custom range requires start and end dates")
            if start > end:
                raise InvalidRangeError("Custom range start must not be after end")
            current = (start, end)
        elif kind == "today":
            current = (today, today)
        elif kind == "yesterday":
            current = (today - timedelta(days=1), today - timedelta(days=1))
        elif kind == "last_7_days":
            current = (today - timedelta(days=7), today - timedelta(days=1))
        elif kind == "last_14_days":
            current = (today - timedelta(days=14), today - timedelta(days=1))
        elif kind == "last_30_days":
            current = (today - timedelta(days=30), today - timedelta(days=1))
        else:  # month_to_date
            current = (today.replace(day=1), today)

        start, end = current
        length = (end - start).days + 1
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=length - 1)
        return Range(
            kind=kind,
            start=start,
            end=end,
            previous_start=previous_start,
            previous_end=previous_end,
        )


def resolve_range(
    timezone: str,
    kind: str,
    *,
    start: date | None = None,
    end: date | None = None,
) -> Range:
    """Public range resolution in the business timezone (router entry point)."""
    return _RangeResolver(timezone).resolve(kind, start=start, end=end)


def _measure(value, *, insufficient_reason: str | None = None) -> dict:
    """Row-level measure: SUM over no rows is unavailable; real zero stays zero."""
    if value is None:
        return {
            "value": None,
            "status": STATUS_UNAVAILABLE,
            "reason": insufficient_reason or "no facts in period",
        }
    return {"value": value, "status": STATUS_AVAILABLE, "reason": None}


def _kpi(measure: Measure) -> dict:
    if measure.status == STATUS_AVAILABLE:
        return {"value": measure.value, "status": STATUS_AVAILABLE, "reason": None}
    return {"value": None, "status": measure.status, "reason": measure.reason}


def _money_measure(
    value, currency: str, source: str, *, insufficient_reason: str | None = None
) -> dict:
    return {
        **_measure(value, insufficient_reason=insufficient_reason),
        "currency": currency,
        "source": source,
    }


def _money_kpi(measure: Measure, currency: str, source: str) -> dict:
    """Money-typed KPI result (cpc/cpm/cpa/aov)."""
    return {
        **_kpi(measure),
        "currency": currency,
        "source": source,
    }


def _comparison(current: Decimal | None, previous: Decimal | None) -> dict:
    comparison = Comparison.of(current, previous)
    return {
        "current": comparison.current,
        "previous": comparison.previous,
        "absolute_change": comparison.absolute_change,
        "percentage_change": _kpi(comparison.percentage_change),
    }


async def _business_or_raise(session: AsyncSession, business_id) -> Business:
    business = await session.get(Business, business_id)
    if business is None:
        raise BusinessNotFoundError(f"Business not found: {business_id}")
    return business


async def build_summary(session: AsyncSession, business: Business, range: Range) -> dict:
    """Summary measure block for a range (shared by /summary and /comparison)."""
    ad = await aggregation.ad_totals(session, business.id, range, currency=business.currency)
    commerce = await aggregation.commerce_totals(
        session, business.id, range, currency=business.currency
    )

    ad_rows = ad.get("rows") or 0
    commerce_rows_count = commerce.get("rows") or 0
    no_ad = "no advertising data in period" if ad_rows == 0 else None
    no_commerce = "no commerce data in period" if commerce_rows_count == 0 else None

    impressions = ad.get("impressions")
    clicks = ad.get("clicks")
    landing_page_views = ad.get("landing_page_views")
    spend = ad.get("spend")
    conversions = ad.get("conversions")
    conversion_value = ad.get("conversion_value")
    reach = ad.get("reach")
    link_clicks = ad.get("link_clicks")

    purchases = commerce.get("purchases")
    revenue = commerce.get("revenue")
    refunds = commerce.get("refunds")

    # Profitability profile: the configured unit economics (Phase 1), never
    # recomputed here. Period figures scale the per-unit economics.
    profit_profile = await summary_data(session, business)
    avg_unit_profit = profit_profile.get("average_contribution_profit")
    profile_has_economics = avg_unit_profit is not None

    if revenue is not None and purchases is not None and profile_has_economics:
        profit_value = (avg_unit_profit * Decimal(purchases)).quantize(PRECISION_MONEY)
        profit = _money_measure(profit_value, business.currency, "economics")
    else:
        reason = (
            "no commerce data in period"
            if revenue is None or purchases is None
            else "no unit economics configured"
        )
        profit = _money_measure(None, business.currency, "economics", insufficient_reason=reason)

    margin = contribution_margin(
        profit.get("value") if profit.get("status") == STATUS_AVAILABLE else None,
        revenue,
    )

    if profile_has_economics:
        break_even_cpa = _money_measure(avg_unit_profit, business.currency, "economics")
        break_even_roas_value = profit_profile.get("break_even_roas")
        if break_even_roas_value is not None:
            break_even_roas = _kpi(Measure(break_even_roas_value, STATUS_AVAILABLE))
        else:
            break_even_roas = Measure.unavailable(
                "no positive contribution profit in economics profile"
            )
    else:
        break_even_cpa = _money_measure(
            None, business.currency, "economics", insufficient_reason="no unit economics configured"
        )
        break_even_roas = Measure.unavailable("no unit economics configured")

    return {
        "business_id": business.id,
        "currency": business.currency,
        "timezone": business.timezone,
        "range": _range_view(range),
        "revenue": _money_measure(
            revenue, business.currency, REVENUE_SOURCE_COMMERCE, insufficient_reason=no_commerce
        ),
        "spend": _money_measure(spend, business.currency, PROVIDER_META, insufficient_reason=no_ad),
        "purchases": _measure(purchases, insufficient_reason=no_commerce),
        "refunds": _money_measure(
            refunds, business.currency, REVENUE_SOURCE_COMMERCE, insufficient_reason=no_commerce
        ),
        "impressions": _measure(impressions, insufficient_reason=no_ad),
        "reach": _measure(reach, insufficient_reason=no_ad),
        "clicks": _measure(clicks, insufficient_reason=no_ad),
        "link_clicks": _measure(link_clicks, insufficient_reason=no_ad),
        "landing_page_views": _measure(landing_page_views, insufficient_reason=no_ad),
        "conversions": _measure(conversions, insufficient_reason=no_ad),
        "ctr": _kpi(ctr(clicks, impressions)),
        "cpc": _money_kpi(cpc(spend, clicks), business.currency, PROVIDER_META),
        "cpm": _money_kpi(cpm(spend, impressions), business.currency, PROVIDER_META),
        "cvr": _kpi(cvr(purchases, clicks)),
        "cpa": _money_kpi(cpa(spend, purchases), business.currency, PROVIDER_META),
        "aov": _money_kpi(aov(revenue, purchases), business.currency, REVENUE_SOURCE_COMMERCE),
        "roas": _kpi(roas(conversion_value, spend)),
        "mer": _kpi(mer(revenue, spend)),
        "contribution_profit": profit,
        "contribution_margin": _kpi(margin),
        "break_even_cpa": break_even_cpa,
        "break_even_roas": _kpi(break_even_roas),
    }


async def summary(session: AsyncSession, business: Business, range: Range) -> dict:
    return await build_summary(session, business, range)


async def timeseries(session: AsyncSession, business: Business, range: Range) -> dict:
    ad_series = await aggregation.ad_timeseries(
        session, business.id, range, currency=business.currency
    )
    commerce_series = await aggregation.commerce_timeseries(
        session, business.id, range, currency=business.currency
    )
    commerce_map = {str(row["date"]): row for row in commerce_series}
    profit_profile = await summary_data(session, business)
    avg_unit_profit = profit_profile.get("average_contribution_profit")

    points: list[dict] = []
    for row in ad_series:
        key = str(row["date"])
        commerce = commerce_map.pop(key, {})
        points.append(_timeseries_point(row, commerce, business, avg_unit_profit))
    for _key, row in commerce_map.items():
        points.append(_timeseries_point({}, row, business, avg_unit_profit))
    points.sort(key=lambda p: p["date"])

    return {
        "business_id": business.id,
        "currency": business.currency,
        "timezone": business.timezone,
        "range": _range_view(range),
        "points": points,
    }


def _timeseries_point(
    row: dict, commerce: dict, business: Business, avg_unit_profit: Decimal | None
) -> dict:
    impressions = row.get("impressions")
    clicks = row.get("clicks")
    spend = row.get("spend")
    conversions = row.get("conversions")
    conversion_value = row.get("conversion_value")
    purchases = commerce.get("purchases")
    revenue = commerce.get("revenue")

    return {
        "date": row["date"] if row.get("date") is not None else commerce["date"],
        "spend": spend,
        "revenue": revenue,
        "purchases": purchases,
        "clicks": clicks,
        "impressions": impressions,
        "conversions": conversions,
        "conversion_value": conversion_value,
        "ctr": ctr(clicks, impressions).value
        if ctr(clicks, impressions).status == STATUS_AVAILABLE
        else None,
        "cpa": cpa(spend, purchases).value
        if cpa(spend, purchases).status == STATUS_AVAILABLE
        else None,
        "roas": roas(conversion_value, spend).value
        if roas(conversion_value, spend).status == STATUS_AVAILABLE
        else None,
        "mer": mer(revenue, spend).value
        if mer(revenue, spend).status == STATUS_AVAILABLE
        else None,
        "contribution_profit": (
            (avg_unit_profit * Decimal(purchases)).quantize(PRECISION_MONEY)
            if purchases is not None and avg_unit_profit is not None
            else None
        ),
    }


async def funnel(session: AsyncSession, business: Business, range: Range) -> dict:
    ad = await aggregation.ad_totals(session, business.id, range, currency=business.currency)
    commerce = await aggregation.commerce_totals(
        session, business.id, range, currency=business.currency
    )

    values: dict[str, Decimal | None] = {
        "impressions": ad.get("impressions"),
        "clicks": ad.get("clicks"),
        "landing_page_views": ad.get("landing_page_views"),
        "purchases": commerce.get("purchases"),
    }
    for metric in _UNOBSERVED_METRICS:
        values[metric] = None

    stages: list[dict] = []
    stage_order = (*_OBSERVED_METRICS, *_UNOBSERVED_METRICS, "purchases")
    for metric in stage_order:
        value = values[metric]
        if metric in _UNOBSERVED_METRICS:
            stage = {
                "metric": metric,
                "value": None,
                "status": STATUS_UNAVAILABLE,
                "reason": "no provider reports this metric",
                "conversion_rate": None,
                "dropoff_rate": None,
            }
        else:
            stage = {
                "metric": metric,
                "value": value,
                "status": STATUS_AVAILABLE if value is not None else STATUS_UNAVAILABLE,
                "reason": None if value is not None else "no facts in period",
                "conversion_rate": None,
                "dropoff_rate": None,
            }
        if stages:
            previous_value = stages[-1]["value"]
            stage["conversion_rate"] = _kpi(funnel_transition(value, previous_value))
            stage["dropoff_rate"] = _kpi(dropoff_rate(value, previous_value))
        stages.append(stage)

    return {
        "business_id": business.id,
        "range": _range_view(range),
        "stages": stages,
    }


def _entity_view(
    row: dict,
    id_label: str,
    extra_labels: tuple[str, ...],
    no_data: dict | None,
    currency: str,
) -> dict:
    name_label = f"{row_names_label(id_label)}_name"
    status_label = f"{row_names_label(id_label)}_status"
    base = {
        "id": row.get(id_label),
        id_label: row.get(id_label),
        "name": row.get(name_label),
        "status": row.get(status_label),
    }
    for label in extra_labels:
        base[label] = row.get(label)

    if no_data is not None:
        base.update(
            {
                "impressions": None,
                "reach": None,
                "clicks": None,
                "link_clicks": None,
                "landing_page_views": None,
                "spend": None,
                "conversions": None,
                "conversion_value": None,
                "revenue_source": None,
                "ctr": no_data,
                "cpc": None,
                "cpm": None,
                "cvr": None,
                "cpa": None,
                "aov": None,
                "roas": no_data,
            }
        )
        return base

    spend = row.get("spend")
    impressions = row.get("impressions")
    clicks = row.get("clicks")
    conversion_value = row.get("conversion_value")
    ctr_m = ctr(clicks, impressions)
    cpc_m = cpc(spend, clicks)
    cpm_m = cpm(spend, impressions)
    roas_m = roas(conversion_value, spend)

    base.update(
        {
            "impressions": impressions,
            "reach": row.get("reach"),
            "clicks": clicks,
            "link_clicks": row.get("link_clicks"),
            "landing_page_views": row.get("landing_page_views"),
            "spend": spend,
            "conversions": row.get("conversions"),
            "conversion_value": conversion_value,
            "revenue_source": (
                REVENUE_SOURCE_META_REPORTED if conversion_value is not None else None
            ),
            "ctr": _kpi(ctr_m),
            "cpc": _money_kpi(cpc_m, currency, PROVIDER_META),
            "cpm": _money_kpi(cpm_m, currency, PROVIDER_META),
            "cvr": {
                "value": None,
                "status": STATUS_UNAVAILABLE,
                "reason": "no purchase attribution at this grain",
            },
            "cpa": {
                "value": None,
                "status": STATUS_UNAVAILABLE,
                "reason": "no purchase attribution at this grain",
            },
            "aov": {
                "value": None,
                "status": STATUS_UNAVAILABLE,
                "reason": "no purchase attribution at this grain",
            },
            "roas": _kpi(roas_m),
        }
    )
    return base


def _entity_metrics(
    row: dict,
    *,
    id_label: str,
    extra_labels: tuple[str, ...],
    currency: str,
) -> dict:
    has_rows = row.get("rows") or 0
    if has_rows == 0:
        no_data = {
            "value": None,
            "status": STATUS_INSUFFICIENT_DATA,
            "reason": "no data in period",
        }
        return _entity_view(row, id_label, extra_labels, no_data, currency)
    return _entity_view(row, id_label, extra_labels, None, currency)


def row_names_label(id_label: str) -> str:
    return {
        "campaign_id": "campaign",
        "ad_set_id": "ad_set",
        "ad_id": "ad",
    }[id_label]


async def campaigns(session: AsyncSession, business: Business, range: Range) -> dict:
    rows = await aggregation.campaign_rollups(
        session, business.id, range, currency=business.currency
    )
    return {
        "business_id": business.id,
        "currency": business.currency,
        "timezone": business.timezone,
        "range": _range_view(range),
        "campaigns": [
            _entity_metrics(
                row,
                id_label="campaign_id",
                extra_labels=("ad_account_id",),
                currency=business.currency,
            )
            for row in rows
        ],
    }


async def ad_sets(
    session: AsyncSession, business: Business, range: Range, *, campaign_id=None
) -> dict:
    if campaign_id is not None:
        await aggregation.resolve_entity(session, business.id, "campaign", campaign_id)
    rows = await aggregation.ad_set_rollups(
        session, business.id, range, currency=business.currency, campaign_id=campaign_id
    )
    return {
        "business_id": business.id,
        "currency": business.currency,
        "timezone": business.timezone,
        "range": _range_view(range),
        "campaign_id": campaign_id,
        "ad_sets": [
            _entity_metrics(
                row, id_label="ad_set_id", extra_labels=("campaign_id",), currency=business.currency
            )
            for row in rows
        ],
    }


async def ads(
    session: AsyncSession,
    business: Business,
    range: Range,
    *,
    campaign_id=None,
    ad_set_id=None,
) -> dict:
    if campaign_id is not None:
        await aggregation.resolve_entity(session, business.id, "campaign", campaign_id)
    if ad_set_id is not None:
        await aggregation.resolve_entity(session, business.id, "ad_set", ad_set_id)
    rows = await aggregation.ad_rollups(
        session,
        business.id,
        range,
        currency=business.currency,
        campaign_id=campaign_id,
        ad_set_id=ad_set_id,
    )
    return {
        "business_id": business.id,
        "currency": business.currency,
        "timezone": business.timezone,
        "range": _range_view(range),
        "campaign_id": campaign_id,
        "ad_set_id": ad_set_id,
        "ads": [
            _entity_metrics(
                row,
                id_label="ad_id",
                extra_labels=("campaign_id", "ad_set_id"),
                currency=business.currency,
            )
            for row in rows
        ],
    }


async def products(session: AsyncSession, business: Business, range: Range) -> dict:
    rows = await aggregation.product_totals(session, business.id, range, currency=business.currency)
    products_view: list[dict] = []
    for row in rows:
        units = row.get("units")
        revenue = row.get("revenue")
        aov_m = aov(revenue, units)
        products_view.append(
            {
                "product_id": row.get("product_id"),
                "name": row.get("product_name"),
                "sku": row.get("product_sku"),
                "units": units,
                "revenue": revenue,
                "refunds": None,
                "cogs": None,
                "contribution_profit": None,
                "contribution_margin": {
                    "value": None,
                    "status": STATUS_UNAVAILABLE,
                    "reason": "no per-order cost data",
                },
                "aov": _money_kpi(aov_m, business.currency, "commerce"),
            }
        )
    return {
        "business_id": business.id,
        "currency": business.currency,
        "timezone": business.timezone,
        "range": _range_view(range),
        "products": products_view,
    }


async def data_quality(
    session: AsyncSession, business: Business, range: Range, settings: Settings
) -> dict:
    resolver = _RangeResolver(business.timezone)
    yesterday = resolver.today - timedelta(days=1)
    now = datetime.now(UTC)
    window = timedelta(hours=settings.metrics_stale_after_hours)

    providers: list[dict] = []
    for provider in (PROVIDER_SHOPIFY, PROVIDER_META):
        last_synced_at = await session.scalar(
            select(IntegrationConnection.last_sync_at)
            .where(
                IntegrationConnection.business_id == business.id,
                IntegrationConnection.provider == provider,
                IntegrationConnection.status == "connected",
                IntegrationConnection.last_sync_at.is_not(None),
            )
            .order_by(IntegrationConnection.last_sync_at.desc())
            .limit(1)
        )
        last_success = await session.scalar(
            select(SyncRun.finished_at)
            .join(IntegrationConnection, IntegrationConnection.id == SyncRun.connection_id)
            .where(
                IntegrationConnection.business_id == business.id,
                IntegrationConnection.provider == provider,
                SyncRun.status.in_(("success", "partial")),
                SyncRun.finished_at.is_not(None),
            )
            .order_by(SyncRun.finished_at.desc())
            .limit(1)
        )
        coverage = await aggregation.provider_coverage(session, business.id, provider, range)
        if coverage is None:
            if last_synced_at is None:
                status, reason = "unavailable", "not connected"
            else:
                status, reason = "unavailable", "no synced facts in period"
            providers.append(
                {
                    "provider": provider,
                    "connected": last_synced_at is not None,
                    "last_synced_at": last_synced_at.isoformat() if last_synced_at else None,
                    "last_successful_sync_at": last_success.isoformat() if last_success else None,
                    "coverage_start": None,
                    "coverage_end": None,
                    "covered_days": None,
                    "missing_days": None,
                    "freshness_status": status,
                    "reason": reason,
                }
            )
            continue

        coverage_end = coverage["max_date"]
        covered_days = int(coverage["covered_days"])
        total_days = (range.end - range.start).days + 1
        missing_days = max(0, total_days - covered_days)
        if coverage_end >= yesterday:
            status, reason = "fresh", None
        elif (
            last_synced_at is not None
            and (now - last_synced_at).total_seconds() < window.total_seconds()
        ):
            status, reason = "delayed", "coverage is behind the reporting window"
        else:
            status, reason = "stale", "no recent syncs"
        providers.append(
            {
                "provider": provider,
                "connected": True,
                "last_synced_at": last_synced_at.isoformat() if last_synced_at else None,
                "last_successful_sync_at": last_success.isoformat() if last_success else None,
                "coverage_start": coverage["min_date"],
                "coverage_end": coverage_end,
                "covered_days": covered_days,
                "missing_days": missing_days,
                "freshness_status": status,
                "reason": reason,
            }
        )
    return {
        "business_id": business.id,
        "timezone": business.timezone,
        "range": _range_view(range),
        "providers": providers,
    }


async def comparison(session: AsyncSession, business: Business, range: Range) -> dict:
    current = await build_summary(session, business, range)
    previous_range = Range(
        kind=range.kind,
        start=range.previous_start,
        end=range.previous_end,
        previous_start=None,
        previous_end=None,
    )
    previous = await build_summary(session, business, previous_range)

    result = {
        "business_id": business.id,
        "currency": business.currency,
        "timezone": business.timezone,
        "range": _range_view(range),
    }
    for key in (
        "revenue",
        "spend",
        "purchases",
        "roas",
        "mer",
        "cpa",
        "aov",
        "ctr",
        "contribution_profit",
    ):
        result[key] = _comparison(current[key].get("value"), previous[key].get("value"))
    return result


def _range_view(range: Range) -> dict:
    return {
        "kind": range.kind,
        "start": range.start,
        "end": range.end,
        "previous_start": range.previous_start,
        "previous_end": range.previous_end,
    }
