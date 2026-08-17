"""Simulator endpoints: deterministic, read-only simulations.

Every route resolves `business_id` from the path via the central
`get_business_from_path` dependency (server-side tenancy validation, 404
on unknown businesses) and requires the `business:read` permission.

Simulations are analysis artifacts: they never mutate ad accounts,
campaigns or budgets. `/simulations` persists the deterministic snapshot
idempotently (identical resolved assumptions collapse to the same row);
`/simulations/{simulation_id}/rerun` recomputes the same inputs against
today's data.

Campaign-scoped ids are resolved inside the authorized business —
unknown or cross-tenant ids return 404, never a leak.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from src.core.dependencies import (
    CurrentBusinessId,
    CurrentUser,
    DbSession,
    require_permission,
)
from src.core.tenancy import TenantContext
from src.modules.metrics.errors import UnknownEntityError
from src.modules.simulator import service as simulator_service
from src.modules.simulator.errors import SimulatorFilterError
from src.modules.simulator.schemas import (
    SimulationCreateRequest,
    SimulationRead,
    SimulationSummaryRead,
)

router = APIRouter(tags=["simulator"])

_SIMULATION_ID = Path(description="Simulation id.")


# ---------------------------------------------------------------------------
# Business simulation endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/businesses/{business_id}/simulations",
    response_model=SimulationSummaryRead,
    summary="List persisted simulations for a business",
)
async def simulation_list(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    limit: Annotated[int, Query(description="Maximum number of rows.")] = 20,
) -> SimulationSummaryRead:
    business = await simulator_service.get_business(session, business_id)
    return await simulator_service.list_simulations(session, business.id, limit=limit)


@router.post(
    "/businesses/{business_id}/simulations",
    response_model=SimulationRead,
    summary="Run a deterministic simulation",
)
async def simulation_create(
    payload: SimulationCreateRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    user: CurrentUser,
) -> SimulationRead:
    business = await simulator_service.get_business(session, business_id)
    row = await simulator_service.create_simulation(
        session,
        business,
        request=payload,
        organization_id=business.organization_id,
        created_by=user.id,
    )
    return simulator_service.to_read(row)


@router.get(
    "/businesses/{business_id}/simulations/{simulation_id}",
    response_model=SimulationRead,
    summary="Get one persisted simulation",
)
async def simulation_get(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    simulation_id: uuid.UUID = _SIMULATION_ID,
) -> SimulationRead:
    business = await simulator_service.get_business(session, business_id)
    row = await simulator_service.get_simulation(session, business.id, simulation_id)
    if row is None:
        raise UnknownEntityError(
            "simulation not found in this business", details={"id": str(simulation_id)}
        )
    return simulator_service.to_read(row)


@router.post(
    "/businesses/{business_id}/simulations/{simulation_id}/rerun",
    response_model=SimulationRead,
    summary="Recompute one simulation against current data",
)
async def simulation_rerun(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    user: CurrentUser,
    simulation_id: uuid.UUID = _SIMULATION_ID,
) -> SimulationRead:
    business = await simulator_service.get_business(session, business_id)
    row = await simulator_service.get_simulation(session, business.id, simulation_id)
    if row is None:
        raise UnknownEntityError(
            "simulation not found in this business", details={"id": str(simulation_id)}
        )
    if row.organization_id != business.organization_id:
        raise UnknownEntityError(
            "simulation not found in this business", details={"id": str(simulation_id)}
        )
    if not user:
        raise SimulatorFilterError("user required to rerun a simulation", details={})
    refreshed = await simulator_service.rerun_simulation(
        session,
        business,
        row,
        organization_id=business.organization_id,
    )
    return simulator_service.to_read(refreshed)


# ---------------------------------------------------------------------------
# Campaign simulation endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/businesses/{business_id}/campaigns/{campaign_id}/simulate",
    response_model=SimulationRead,
    summary="Run a deterministic simulation for one campaign",
)
async def campaign_simulation(
    payload: SimulationCreateRequest,
    business_id: CurrentBusinessId,
    campaign_id: str,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    user: CurrentUser,
) -> SimulationRead:
    try:
        parsed = uuid.UUID(campaign_id)
    except ValueError:
        raise UnknownEntityError(
            "campaign not found in this business", details={"id": campaign_id}
        ) from None
    business = await simulator_service.get_business(session, business_id)
    payload.entity_type = "campaign"
    payload.entity_id = parsed
    row = await simulator_service.create_simulation(
        session,
        business,
        request=payload,
        organization_id=business.organization_id,
        created_by=user.id,
    )
    return simulator_service.to_read(row)


__all__ = ["router"]
