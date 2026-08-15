"""Diagnostics endpoints: read-only, deterministic analytics findings.

Every route resolves business_id from the path via `get_business_from_path`
(server-side tenancy validation, 404 on unknown businesses) and requires the
`business:read` permission. Campaign ids are resolved inside the authorized
business — unknown or cross-tenant ids return 404, never a leak.

Range: `range_kind` selects a named window (today, yesterday, last_7_days,
last_14_days, last_30_days, month_to_date); `date_from`/`date_to` (the
spec's names for custom ranges) select an arbitrary window. All date math
happens in the business timezone.
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
from src.modules.diagnostics import service as diagnostics_service
from src.modules.diagnostics.schemas import (
    CampaignDiagnosticsRead,
    DiagnosticsRead,
    DiagnosticsSummaryRead,
)
from src.modules.metrics import service as metrics_service
from src.modules.metrics.errors import UnknownEntityError

router = APIRouter(tags=["diagnostics"])


def _parse_entity_id(raw: str | None) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise UnknownEntityError(
            "entity not found in this business", details={"id": raw}
        ) from None


def _parse_filters(
    entity_type: str | None,
    entity_id: uuid.UUID | None,
    severity: str | None,
    category: str | None,
    status: str | None,
):
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "severity": severity,
        "category": category,
        "status": status,
    }


@router.get(
    "/businesses/{business_id}/diagnostics",
    response_model=DiagnosticsRead,
    summary="Deterministic diagnostic findings for a business",
)
async def diagnostics_list(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    settings: SettingsDep,
    range_kind: Annotated[
        str,
        Query(
            description="Named reporting window (today, yesterday, last_7_days, "
            "last_14_days, last_30_days, month_to_date)."
        ),
    ] = "last_30_days",
    date_from: Annotated[
        date | None, Query(description="Custom range start (alternative to range_kind).")
    ] = None,
    date_to: Annotated[
        date | None, Query(description="Custom range end (alternative to range_kind).")
    ] = None,
    entity_type: Annotated[
        str | None, Query(description="Filter findings by entity type.")
    ] = None,
    entity_id: Annotated[
        str | None,
        Query(description="Filter findings to one entity (must belong to the business)."),
    ] = None,
    severity: Annotated[
        str | None, Query(description="Filter findings by severity.")
    ] = None,
    category: Annotated[
        str | None, Query(description="Filter findings by category.")
    ] = None,
    status: Annotated[
        str | None, Query(description="Filter findings by lifecycle status.")
    ] = None,
) -> DiagnosticsRead:
    business = await get_business(session, business_id)
    if date_from is not None or date_to is not None:
        range_kind = "custom"
    range_obj = metrics_service.resolve_range(
        business.timezone, range_kind, start=date_from, end=date_to
    )
    filters = _parse_filters(
        entity_type, _parse_entity_id(entity_id), severity, category, status
    )
    data = await diagnostics_service.diagnostics_for_business(
        session, business, range_obj, settings, **filters
    )
    return DiagnosticsRead(**data)


@router.get(
    "/businesses/{business_id}/diagnostics/summary",
    response_model=DiagnosticsSummaryRead,
    summary="Diagnostics summary counters",
)
async def diagnostics_summary(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    settings: SettingsDep,
    range_kind: Annotated[
        str, Query(description="Named reporting window.")
    ] = "last_30_days",
    date_from: Annotated[
        date | None, Query(description="Custom range start (alternative to range_kind).")
    ] = None,
    date_to: Annotated[
        date | None, Query(description="Custom range end (alternative to range_kind).")
    ] = None,
    entity_type: Annotated[
        str | None, Query(description="Filter findings by entity type.")
    ] = None,
    entity_id: Annotated[
        str | None,
        Query(description="Filter findings to one entity (must belong to the business)."),
    ] = None,
    severity: Annotated[
        str | None, Query(description="Filter findings by severity.")
    ] = None,
    category: Annotated[
        str | None, Query(description="Filter findings by category.")
    ] = None,
    status: Annotated[
        str | None, Query(description="Filter findings by lifecycle status.")
    ] = None,
) -> DiagnosticsSummaryRead:
    business = await get_business(session, business_id)
    if date_from is not None or date_to is not None:
        range_kind = "custom"
    range_obj = metrics_service.resolve_range(
        business.timezone, range_kind, start=date_from, end=date_to
    )
    filters = _parse_filters(
        entity_type, _parse_entity_id(entity_id), severity, category, status
    )
    summary_data = await diagnostics_service.diagnostics_summary(
        session, business, range_obj, settings, **filters
    )
    return DiagnosticsSummaryRead(**summary_data)


@router.get(
    "/businesses/{business_id}/campaigns/{campaign_id}/diagnostics",
    response_model=CampaignDiagnosticsRead,
    summary="Per-campaign diagnostics with performance state",
)
async def campaign_diagnostics(
    business_id: CurrentBusinessId,
    campaign_id: str,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    settings: SettingsDep,
    range_kind: Annotated[
        str, Query(description="Named reporting window.")
    ] = "last_30_days",
    date_from: Annotated[
        date | None, Query(description="Custom range start (alternative to range_kind).")
    ] = None,
    date_to: Annotated[
        date | None, Query(description="Custom range end (alternative to range_kind).")
    ] = None,
) -> CampaignDiagnosticsRead:
    business = await get_business(session, business_id)
    campaign_id_uuid = _parse_entity_id(campaign_id)
    if campaign_id_uuid is None:
        raise UnknownEntityError("campaign not found in this business", details={"id": campaign_id})
    if date_from is not None or date_to is not None:
        range_kind = "custom"
    range_obj = metrics_service.resolve_range(
        business.timezone, range_kind, start=date_from, end=date_to
    )
    data = await diagnostics_service.campaign_diagnostics(
        session, business, campaign_id_uuid, range_obj, settings
    )
    return CampaignDiagnosticsRead(**data)