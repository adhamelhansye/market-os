"""Creative test measurement report API (Phase 8I).

Single canonical read-only report endpoint. No write endpoints exist in
this phase; 8H remains the only lifecycle mutation surface.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.core.dependencies import CurrentBusinessId, DbSession, require_permission
from src.core.tenancy import TenantContext
from src.modules.businesses.service import get_business
from src.modules.creative.measurement.service import build_test_report

router = APIRouter(tags=["creative-test-report"])


@router.get(
    "/businesses/{business_id}/strategy/creative/tests/{test_external_ref}/report"
)
async def test_report(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    test_external_ref: str,
    range_kind: Annotated[str, Query()] = "last_30_days",
) -> dict:
    """Unified measurement report assembled from canonical 8H/8C/8D state.

    Read-only. Values from upstream layers are surfaced verbatim; missing
    data appears as explicit unavailable/insufficient states.
    """
    business = await get_business(session, business_id)
    report = await build_test_report(
        session,
        business,
        test_external_ref=test_external_ref,
        range_kind=range_kind,
    )
    if report.get("status") == "not_found":
        from src.core.exceptions import NotFoundError

        raise NotFoundError("Creative test not found")
    return report
