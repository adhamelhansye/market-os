"""Recommendations endpoints: read-only, deterministic review decisions.

Every route resolves business_id from the path via `get_business_from_path`
(server-side tenancy validation, 404 on unknown businesses) and requires the
`business:read` permission. Campaign ids are resolved inside the authorized
business — unknown or cross-tenant ids return 404, never a leak.

POST /generate only recomputes and persists the deterministic decisions for
a range; it never executes any action on providers, budgets or campaigns.

Range: `range_kind` selects a named window (today, yesterday, last_7_days,
last_14_days, last_30_days, month_to_date); `date_from`/`date_to` select an
arbitrary window. All date math happens in the business timezone.
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
from src.modules.recommendations import service as recommendations_service
from src.modules.recommendations.schemas import (
    DecisionRead,
    DecisionsRead,
    DecisionSummaryRead,
    GenerateRequest,
)

router = APIRouter(tags=["recommendations"])


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
    decision: str | None,
    severity: str | None,
):
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "decision": decision,
        "severity": severity,
    }


def _resolve_range(business, range_kind: str, date_from, date_to):
    if date_from is not None or date_to is not None:
        range_kind = "custom"
    return metrics_service.resolve_range(
        business.timezone, range_kind, start=date_from, end=date_to
    )


@router.get(
    "/businesses/{business_id}/recommendations",
    response_model=DecisionsRead,
    summary="Deterministic review decisions for a business",
)
async def recommendations_list(
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
        str | None, Query(description="Filter decisions by entity type (business, campaign).")
    ] = None,
    entity_id: Annotated[
        str | None,
        Query(description="Filter decisions to one entity (must belong to the business)."),
    ] = None,
    decision: Annotated[
        str | None,
        Query(
            description="Filter by decision type (scale_review, optimize, maintain, "
            "kill_review, learning, insufficient_data, tracking_issue, data_quality_issue)."
        ),
    ] = None,
    severity: Annotated[
        str | None, Query(description="Filter decisions by severity.")
    ] = None,
) -> DecisionsRead:
    business = await get_business(session, business_id)
    range_obj = _resolve_range(business, range_kind, date_from, date_to)
    filters = _parse_filters(
        entity_type, _parse_entity_id(entity_id), decision, severity
    )
    data = await recommendations_service.recommendations_for_business(
        session, business, range_obj, settings, **filters
    )
    return DecisionsRead(**data)


@router.get(
    "/businesses/{business_id}/recommendations/summary",
    response_model=DecisionSummaryRead,
    summary="Decision summary counters",
)
async def recommendations_summary(
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
        str | None, Query(description="Filter decisions by entity type.")
    ] = None,
    entity_id: Annotated[
        str | None,
        Query(description="Filter decisions to one entity (must belong to the business)."),
    ] = None,
    decision: Annotated[
        str | None, Query(description="Filter by decision type.")
    ] = None,
    severity: Annotated[
        str | None, Query(description="Filter decisions by severity.")
    ] = None,
) -> DecisionSummaryRead:
    business = await get_business(session, business_id)
    range_obj = _resolve_range(business, range_kind, date_from, date_to)
    filters = _parse_filters(
        entity_type, _parse_entity_id(entity_id), decision, severity
    )
    summary = await recommendations_service.recommendations_summary(
        session, business, range_obj, settings, **filters
    )
    return DecisionSummaryRead(**summary)


@router.get(
    "/businesses/{business_id}/campaigns/{campaign_id}/recommendation",
    response_model=DecisionRead,
    summary="Deterministic review decision for one campaign",
)
async def campaign_recommendation(
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
) -> DecisionRead:
    business = await get_business(session, business_id)
    campaign_id_uuid = _parse_entity_id(campaign_id)
    if campaign_id_uuid is None:
        raise UnknownEntityError(
            "campaign not found in this business", details={"id": campaign_id}
        )
    range_obj = _resolve_range(business, range_kind, date_from, date_to)
    data = await recommendations_service.campaign_recommendation(
        session, business, campaign_id_uuid, range_obj, settings
    )
    return DecisionRead(**data)


@router.post(
    "/businesses/{business_id}/recommendations/generate",
    response_model=DecisionsRead,
    summary="Recompute and persist deterministic decisions (idempotent)",
)
async def recommendations_generate(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    settings: SettingsDep,
    payload: GenerateRequest,
) -> DecisionsRead:
    business = await get_business(session, business_id)
    range_obj = _resolve_range(
        business, payload.range_kind, payload.date_from, payload.date_to
    )
    data = await recommendations_service.generate(
        session, business, range_obj, settings
    )
    return DecisionsRead(**data)