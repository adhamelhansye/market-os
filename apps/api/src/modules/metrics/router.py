"""Metrics endpoints: read-only, deterministic analytics for a business.

Every route resolves business_id from the path via `get_business_from_path`
(server-side tenancy validation, 404 on unknown businesses) and requires the
`business:read` permission. All KPIs are computed by the pure KPI engine over
canonical aggregates — never by the client and never by an LLM.

Range: `range_kind` selects a named window (today, yesterday, last_7_days,
last_14_days, last_30_days, month_to_date); `start`/`end` are required for
`custom`. All date math happens in the business timezone.
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.core.dependencies import (
    CurrentBusinessId,
    DbSession,
    SettingsDep,
    require_permission,
)
from src.core.tenancy import TenantContext
from src.modules.businesses.service import get_business
from src.modules.metrics import service as metrics_service
from src.modules.metrics.errors import UnknownEntityError
from src.modules.metrics.schemas import (
    AdSetsRead,
    AdsRead,
    CampaignsRead,
    ComparisonReadResponse,
    DataQualityRead,
    FunnelRead,
    ProductsRead,
    SummaryRead,
    TimeseriesRead,
)

router = APIRouter(tags=["metrics"])


async def get_range_params(
    range_kind: Annotated[
        str,
        Query(
            description="Named reporting window (today, yesterday, last_7_days, "
            "last_14_days, last_30_days, month_to_date, custom)."
        ),
    ] = "last_30_days",
    start: Annotated[
        date | None, Query(description="Custom range start (required for custom).")
    ] = None,
    end: Annotated[
        date | None, Query(description="Custom range end (required for custom).")
    ] = None,
) -> tuple[str, date | None, date | None]:
    return (range_kind, start, end)


RangeParams = Annotated[tuple[str, date | None, date | None], Depends(get_range_params)]


def _parse_entity_id(raw: str | None, kind: str) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise UnknownEntityError(
            f"{kind} not found in this business", details={"id": raw}
        ) from None


def _range_for(business, params: tuple[str, date | None, date | None]):
    range_kind, start, end = params
    return metrics_service.resolve_range(business.timezone, range_kind, start=start, end=end)


@router.get(
    "/businesses/{business_id}/metrics/summary",
    response_model=SummaryRead,
    summary="Period summary KPIs",
)
async def metrics_summary(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    params: RangeParams,
) -> SummaryRead:
    business = await get_business(session, business_id)
    data = await metrics_service.summary(session, business, _range_for(business, params))
    return SummaryRead(**data)


@router.get(
    "/businesses/{business_id}/metrics/timeseries",
    response_model=TimeseriesRead,
    summary="Daily timeseries",
)
async def metrics_timeseries(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    params: RangeParams,
) -> TimeseriesRead:
    business = await get_business(session, business_id)
    data = await metrics_service.timeseries(session, business, _range_for(business, params))
    return TimeseriesRead(**data)


@router.get(
    "/businesses/{business_id}/metrics/funnel",
    response_model=FunnelRead,
    summary="Acquisition funnel",
)
async def metrics_funnel(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    params: RangeParams,
) -> FunnelRead:
    business = await get_business(session, business_id)
    data = await metrics_service.funnel(session, business, _range_for(business, params))
    return FunnelRead(**data)


@router.get(
    "/businesses/{business_id}/metrics/campaigns",
    response_model=CampaignsRead,
    summary="Campaign-level performance",
)
async def metrics_campaigns(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    params: RangeParams,
) -> CampaignsRead:
    business = await get_business(session, business_id)
    data = await metrics_service.campaigns(session, business, _range_for(business, params))
    return CampaignsRead(**data)


@router.get(
    "/businesses/{business_id}/metrics/adsets",
    response_model=AdSetsRead,
    summary="Ad-set-level performance",
)
async def metrics_ad_sets(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    params: RangeParams,
    campaign_id: Annotated[
        str | None, Query(description="Filter ad sets to one campaign.")
    ] = None,
) -> AdSetsRead:
    business = await get_business(session, business_id)
    parsed = _parse_entity_id(campaign_id, "campaign")
    data = await metrics_service.ad_sets(
        session, business, _range_for(business, params), campaign_id=parsed
    )
    return AdSetsRead(**data)


@router.get(
    "/businesses/{business_id}/metrics/ads",
    response_model=AdsRead,
    summary="Ad-level performance",
)
async def metrics_ads(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    params: RangeParams,
    campaign_id: Annotated[
        str | None, Query(description="Filter ads to one campaign.")
    ] = None,
    ad_set_id: Annotated[
        str | None, Query(description="Filter ads to one ad set.")
    ] = None,
) -> AdsRead:
    business = await get_business(session, business_id)
    data = await metrics_service.ads(
        session,
        business,
        _range_for(business, params),
        campaign_id=_parse_entity_id(campaign_id, "campaign"),
        ad_set_id=_parse_entity_id(ad_set_id, "ad_set"),
    )
    return AdsRead(**data)


@router.get(
    "/businesses/{business_id}/metrics/products",
    response_model=ProductsRead,
    summary="Product-level performance",
)
async def metrics_products(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    params: RangeParams,
) -> ProductsRead:
    business = await get_business(session, business_id)
    data = await metrics_service.products(session, business, _range_for(business, params))
    return ProductsRead(**data)


@router.get(
    "/businesses/{business_id}/metrics/data-quality",
    response_model=DataQualityRead,
    summary="Provider data quality and freshness",
)
async def metrics_data_quality(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    settings: SettingsDep,
    params: RangeParams,
) -> DataQualityRead:
    business = await get_business(session, business_id)
    data = await metrics_service.data_quality(
        session, business, _range_for(business, params), settings
    )
    return DataQualityRead(**data)


@router.get(
    "/businesses/{business_id}/metrics/comparison",
    response_model=ComparisonReadResponse,
    summary="Current vs previous period comparison",
)
async def metrics_comparison(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    params: RangeParams,
) -> ComparisonReadResponse:
    business = await get_business(session, business_id)
    data = await metrics_service.comparison(session, business, _range_for(business, params))
    return ComparisonReadResponse(**data)
