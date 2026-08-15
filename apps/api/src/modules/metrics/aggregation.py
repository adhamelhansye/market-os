"""Metric aggregation over `metric_facts`.

Rules (see metrics.md):

- Advertising totals ALWAYS read grain='ad' rows only — the finest stored
  advertising grain — and campaign/ad-set/ad/account totals are rollups of
  those rows. Mixing grains in one aggregation would double-count, which is
  tested against.
- Commerce totals read grain='business' rows (orders) and grain='product'
  rows (order items) only; the two are never summed together.
- Aggregates are restricted to the BUSINESS currency (matching the Phase 1
  revenue convention: a EUR order is never silently summed into a USD
  total). Rows in other currencies are excluded, never converted.
- No row = no fact: aggregates surface NULL (not zero) so the service layer
  can mark things unavailable instead of inventing zeros.
- All moneys come back as Decimal (SQLAlchemy Numeric); counts as int.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Ad, AdSet, Campaign, Product
from src.modules.metrics.definitions import PROVIDER_SHOPIFY
from src.modules.metrics.errors import UnknownEntityError
from src.modules.metrics.models import F, metric_facts

EntityKind = Literal["campaign", "ad_set", "ad"]

_AD_FACT_COLUMNS = (
    "impressions",
    "reach",
    "clicks",
    "link_clicks",
    "landing_page_views",
    "spend",
    "conversions",
    "conversion_value",
)

_COMMERCE_FACT_COLUMNS = ("purchases", "revenue", "refunds")


@dataclass(frozen=True)
class Range:
    kind: str
    start: date
    end: date
    previous_start: date | None = None
    previous_end: date | None = None


def _sums(columns: tuple[str, ...]) -> list:
    return [func.sum(F[column]).label(column) for column in columns]


def _row_total(row) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row._mapping)


def _scoped(*conditions) -> list:
    """Shared WHERE pieces: business + grain + date + currency filters."""
    return list(conditions)


async def ad_totals(
    session: AsyncSession,
    business_id,
    range: Range,
    *,
    currency: str,
    entity: EntityKind | None = None,
    entity_id=None,
) -> dict[str, Any]:
    """Summed advertising facts (grain='ad') for the range and currency.

    Empty result = no advertising facts in range (never zero-padded).
    """
    conditions = [
        F["business_id"] == business_id,
        F["grain"] == "ad",
        F["date"] >= range.start,
        F["date"] <= range.end,
        F["currency"] == currency,
    ]
    if entity is not None:
        conditions.append(F[f"{entity}_id"] == entity_id)
    stmt = (
        select(*_sums(_AD_FACT_COLUMNS), func.count().label("rows"))
        .select_from(metric_facts)
        .where(*conditions)
    )
    result = await session.execute(stmt)
    return _row_total(result.one_or_none())


async def commerce_totals(
    session: AsyncSession, business_id, range: Range, *, currency: str
) -> dict[str, Any]:
    """Summed commerce facts (grain='business') for the range and currency."""
    stmt = (
        select(*_sums(_COMMERCE_FACT_COLUMNS), func.count().label("rows"))
        .select_from(metric_facts)
        .where(
            F["business_id"] == business_id,
            F["grain"] == "business",
            F["date"] >= range.start,
            F["date"] <= range.end,
            F["currency"] == currency,
        )
    )
    result = await session.execute(stmt)
    return _row_total(result.one_or_none())


async def ad_timeseries(
    session: AsyncSession, business_id, range: Range, *, currency: str
) -> list[dict[str, Any]]:
    """Daily advertising totals — one row per date with facts."""
    stmt = (
        select(F["date"], *_sums(_AD_FACT_COLUMNS))
        .select_from(metric_facts)
        .where(
            F["business_id"] == business_id,
            F["grain"] == "ad",
            F["date"] >= range.start,
            F["date"] <= range.end,
            F["currency"] == currency,
        )
        .group_by(F["date"])
        .order_by(F["date"])
    )
    return [dict(row._mapping) for row in await session.execute(stmt)]


async def commerce_timeseries(
    session: AsyncSession, business_id, range: Range, *, currency: str
) -> list[dict[str, Any]]:
    """Daily commerce totals — one row per date with orders."""
    stmt = (
        select(F["date"], *_sums(_COMMERCE_FACT_COLUMNS))
        .select_from(metric_facts)
        .where(
            F["business_id"] == business_id,
            F["grain"] == "business",
            F["date"] >= range.start,
            F["date"] <= range.end,
            F["currency"] == currency,
        )
        .group_by(F["date"])
        .order_by(F["date"])
    )
    return [dict(row._mapping) for row in await session.execute(stmt)]


async def campaign_rollups(
    session: AsyncSession, business_id, range: Range, *, currency: str
) -> list[dict[str, Any]]:
    """Per-campaign advertising rollups (ad-grain rows)."""
    stmt = (
        select(
            F["campaign_id"].label("campaign_id"),
            Campaign.name.label("campaign_name"),
            Campaign.status.label("campaign_status"),
            Campaign.ad_account_id.label("ad_account_id"),
            *_sums(_AD_FACT_COLUMNS),
            func.count().label("rows"),
        )
        .select_from(metric_facts.join(Campaign, Campaign.id == F["campaign_id"], isouter=True))
        .where(
            F["business_id"] == business_id,
            F["grain"] == "ad",
            F["date"] >= range.start,
            F["date"] <= range.end,
            F["currency"] == currency,
        )
        .group_by(F["campaign_id"], Campaign.name, Campaign.status, Campaign.ad_account_id)
        .order_by(F["campaign_id"])
    )
    return [dict(row._mapping) for row in await session.execute(stmt)]


async def ad_set_rollups(
    session: AsyncSession,
    business_id,
    range: Range,
    *,
    currency: str,
    campaign_id=None,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            F["ad_set_id"].label("ad_set_id"),
            AdSet.name.label("ad_set_name"),
            AdSet.status.label("ad_set_status"),
            AdSet.campaign_id.label("campaign_id"),
            *_sums(_AD_FACT_COLUMNS),
            func.count().label("rows"),
        )
        .select_from(metric_facts.join(AdSet, AdSet.id == F["ad_set_id"], isouter=True))
        .where(
            F["business_id"] == business_id,
            F["grain"] == "ad",
            F["date"] >= range.start,
            F["date"] <= range.end,
            F["currency"] == currency,
            sa.true() if campaign_id is None else AdSet.campaign_id == campaign_id,
        )
        .group_by(F["ad_set_id"], AdSet.name, AdSet.status, AdSet.campaign_id)
        .order_by(F["ad_set_id"])
    )
    return [dict(row._mapping) for row in await session.execute(stmt)]


async def ad_rollups(
    session: AsyncSession,
    business_id,
    range: Range,
    *,
    currency: str,
    campaign_id=None,
    ad_set_id=None,
) -> list[dict[str, Any]]:
    conditions = [
        F["business_id"] == business_id,
        F["grain"] == "ad",
        F["date"] >= range.start,
        F["date"] <= range.end,
        F["currency"] == currency,
    ]
    if campaign_id is not None:
        conditions.append(Ad.campaign_id == campaign_id)
    if ad_set_id is not None:
        conditions.append(Ad.ad_set_id == ad_set_id)

    stmt = (
        select(
            F["ad_id"].label("ad_id"),
            Ad.name.label("ad_name"),
            Ad.status.label("ad_status"),
            Ad.campaign_id.label("campaign_id"),
            Ad.ad_set_id.label("ad_set_id"),
            *_sums(_AD_FACT_COLUMNS),
            func.count().label("rows"),
        )
        .select_from(metric_facts.join(Ad, Ad.id == F["ad_id"], isouter=True))
        .where(*conditions)
        .group_by(F["ad_id"], Ad.name, Ad.status, Ad.campaign_id, Ad.ad_set_id)
        .order_by(F["ad_id"])
    )
    return [dict(row._mapping) for row in await session.execute(stmt)]


async def product_totals(
    session: AsyncSession, business_id, range: Range, *, currency: str
) -> list[dict[str, Any]]:
    """Per-product commerce facts from order items (grain='product').

    purchases = units sold; revenue = line revenue. Refunds are not
    attributed to individual products (unavailable, never zero).
    """
    stmt = (
        select(
            F["product_id"].label("product_id"),
            Product.name.label("product_name"),
            Product.sku.label("product_sku"),
            func.sum(F["purchases"]).label("units"),
            func.sum(F["revenue"]).label("revenue"),
            func.count().label("lines"),
        )
        .select_from(metric_facts.join(Product, Product.id == F["product_id"], isouter=True))
        .where(
            F["business_id"] == business_id,
            F["grain"] == "product",
            F["date"] >= range.start,
            F["date"] <= range.end,
            F["currency"] == currency,
        )
        .group_by(F["product_id"], Product.name, Product.sku)
        .order_by(F["product_id"])
    )
    return [dict(row._mapping) for row in await session.execute(stmt)]


async def provider_coverage(
    session: AsyncSession, business_id, provider: str, range: Range
) -> dict[str, Any] | None:
    """Date coverage of facts for one provider within the range.

    Returns None when the provider has no facts at all in the range.
    """
    grain = "business" if provider == PROVIDER_SHOPIFY else "ad"
    stmt = (
        select(
            func.min(F["date"]).label("min_date"),
            func.max(F["date"]).label("max_date"),
            func.count(func.distinct(F["date"])).label("covered_days"),
        )
        .select_from(metric_facts)
        .where(
            F["business_id"] == business_id,
            F["provider"] == provider,
            F["grain"] == grain,
            F["date"] >= range.start,
            F["date"] <= range.end,
        )
    )
    row = (await session.execute(stmt)).one_or_none()
    mapping = dict(row._mapping) if row is not None else {}
    if mapping.get("max_date") is None:
        return None
    return mapping


async def resolve_entity(
    session: AsyncSession, business_id, kind: EntityKind, entity_id
) -> dict[str, Any]:
    """Entity ids must resolve inside the authorized business (tenancy)."""
    table = {"campaign": Campaign, "ad_set": AdSet, "ad": Ad}[kind]
    found = (
        await session.execute(
            select(table.id).where(table.id == entity_id, table.business_id == business_id)
        )
    ).first()
    if found is None:
        raise UnknownEntityError(
            f"{kind} not found in this business", details={"id": str(entity_id)}
        )
    return {"id": found[0]}


__all__ = [
    "Range",
    "ad_totals",
    "commerce_totals",
    "ad_timeseries",
    "commerce_timeseries",
    "campaign_rollups",
    "ad_set_rollups",
    "ad_rollups",
    "product_totals",
    "provider_coverage",
    "resolve_entity",
    "EntityKind",
]
