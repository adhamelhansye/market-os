"""Bundle endpoints, scoped to a business."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from src.core.dependencies import (
    CurrentBusinessId,
    DbSession,
    require_permission,
)
from src.core.exceptions import NotFoundError
from src.core.tenancy import TenantContext
from src.db.models import Bundle
from src.modules.bundles import service as bundle_service
from src.modules.bundles.schemas import BundleCreate, BundleRead, BundleUpdate
from src.modules.economics import service as economics_service
from src.modules.economics.schemas import BundleEconomicsRead

router = APIRouter(tags=["bundles"])


async def get_bundle_from_path(
    request: Request, business_id: CurrentBusinessId, session: DbSession
) -> Bundle:
    raw = request.path_params.get("bundle_id", "")
    try:
        bundle_id = uuid.UUID(raw)
    except ValueError:
        raise NotFoundError("Bundle not found") from None
    bundle = await session.get(Bundle, bundle_id)
    if bundle is None or bundle.business_id != business_id:
        raise NotFoundError("Bundle not found")
    return bundle


CurrentBundle = Annotated[Bundle, Depends(get_bundle_from_path)]


@router.get("/businesses/{business_id}/bundles", response_model=list[BundleRead])
async def list_bundles(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[BundleRead]:
    bundles = list(
        await session.scalars(
            select(Bundle).where(Bundle.business_id == business_id).order_by(Bundle.name)
        )
    )
    return [BundleRead.model_validate(b) for b in bundles]


@router.post(
    "/businesses/{business_id}/bundles", response_model=BundleRead, status_code=201
)
async def create_bundle(
    payload: BundleCreate,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> BundleRead:
    bundle = await bundle_service.create_bundle(session, business_id, payload)
    return BundleRead.model_validate(bundle)


@router.get("/businesses/{business_id}/bundles/{bundle_id}", response_model=BundleRead)
async def get_bundle(
    bundle: CurrentBundle,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
) -> BundleRead:
    return BundleRead.model_validate(bundle)


@router.patch(
    "/businesses/{business_id}/bundles/{bundle_id}", response_model=BundleRead
)
async def update_bundle(
    payload: BundleUpdate,
    bundle: CurrentBundle,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> BundleRead:
    bundle = await bundle_service.update_bundle(session, bundle, payload)
    return BundleRead.model_validate(bundle)


@router.delete("/businesses/{business_id}/bundles/{bundle_id}", status_code=204)
async def delete_bundle(
    bundle: CurrentBundle,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> None:
    await bundle_service.delete_bundle(session, bundle)


@router.get(
    "/businesses/{business_id}/bundles/{bundle_id}/economics",
    response_model=BundleEconomicsRead,
)
async def get_bundle_economics(
    bundle: CurrentBundle,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> BundleEconomicsRead:
    economics = await economics_service.bundle_economics(session, bundle)
    return BundleEconomicsRead(
        bundle_id=bundle.id,
        name=bundle.name,
        currency=bundle.currency,
        bundle_price=economics.bundle_price,
        items_cost=economics.items_cost,
        contribution_profit=economics.contribution_profit,
        contribution_margin=economics.contribution_margin,
    )