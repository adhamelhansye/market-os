"""Economics endpoints: read-only, deterministic unit economics for a
business. Every route resolves business_id from the path and validates
access server-side (CurrentBusinessId + permission)."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from src.core.dependencies import (
    CurrentBusinessId,
    DbSession,
    require_permission,
)
from src.core.exceptions import NotFoundError
from src.core.tenancy import TenantContext
from src.db.models import Bundle, Product
from src.modules.businesses.service import get_business
from src.modules.economics import service as economics_service
from src.modules.economics.schemas import (
    BundleEconomicsRead,
    EconomicsSummaryRead,
    ProductEconomicsRead,
    RevenueSummaryRead,
)
from src.modules.goals.schemas import GoalRead

router = APIRouter(tags=["economics"])


@router.get(
    "/businesses/{business_id}/economics/summary",
    response_model=EconomicsSummaryRead,
)
async def economics_summary(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> EconomicsSummaryRead:
    business = await get_business(session, business_id)
    summary = await economics_service.summary_data(session, business)
    current_goal = summary.pop("current_goal", None)
    data = {
        **summary,
        "current_goal": GoalRead.model_validate(current_goal) if current_goal else None,
    }
    return EconomicsSummaryRead(**data)


@router.get(
    "/businesses/{business_id}/economics/revenue",
    response_model=RevenueSummaryRead,
)
async def revenue_summary(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> RevenueSummaryRead:
    business = await get_business(session, business_id)
    return RevenueSummaryRead(**await economics_service.revenue_summary(session, business))


def _to_product_read(product: Product, economics, inventory: int) -> ProductEconomicsRead:
    return ProductEconomicsRead(
        product_id=product.id,
        name=product.name,
        sku=product.sku,
        status=product.status,
        currency=product.currency,
        inventory_quantity=inventory,
        product_revenue=economics.product_revenue if economics else None,
        shipping_revenue=economics.shipping_revenue if economics else None,
        total_customer_revenue=economics.total_customer_revenue if economics else None,
        product_cost=economics.product_cost if economics else Decimal("0"),
        shipping_cost=economics.shipping_cost if economics else Decimal("0"),
        payment_fees=economics.payment_fees if economics else Decimal("0"),
        discount_amount=economics.discount_amount if economics else Decimal("0"),
        contribution_profit=economics.contribution_profit if economics else None,
        contribution_margin=economics.contribution_margin if economics else None,
        break_even_cpa=economics.break_even_cpa if economics else None,
        break_even_roas=economics.break_even_roas if economics else None,
        target_cpa=economics.target_cpa if economics else None,
        target_cpa_reason=economics.target_cpa_reason if economics else None,
    )


async def _product_economics_list(
    session: DbSession, business_id
) -> list[ProductEconomicsRead]:
    products = list(
        await session.scalars(
            select(Product).where(Product.business_id == business_id).order_by(Product.name)
        )
    )
    rows = []
    for product in products:
        economics = await economics_service.product_economics(session, product)
        inventory = await economics_service.current_inventory_quantity(session, product.id)
        rows.append(_to_product_read(product, economics, inventory))
    return rows


@router.get(
    "/businesses/{business_id}/economics/products",
    response_model=list[ProductEconomicsRead],
)
async def economics_products(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[ProductEconomicsRead]:
    return await _product_economics_list(session, business_id)


@router.get(
    "/businesses/{business_id}/economics/products/{product_id}",
    response_model=ProductEconomicsRead,
)
async def economics_product(
    business_id: CurrentBusinessId,
    product_id: str,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> ProductEconomicsRead:
    product = await _get_product(session, business_id, product_id)
    economics = await economics_service.product_economics(session, product)
    inventory = await economics_service.current_inventory_quantity(session, product.id)
    return _to_product_read(product, economics, inventory)


@router.get(
    "/businesses/{business_id}/economics/goals",
    response_model=list[GoalRead],
)
async def economics_goals(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[GoalRead]:
    from src.modules.goals.service import list_goals_for_business

    goals = await list_goals_for_business(session, business_id)
    return [GoalRead.model_validate(g) for g in goals]


@router.get(
    "/businesses/{business_id}/economics/bundles/{bundle_id}",
    response_model=BundleEconomicsRead,
)
async def economics_bundle(
    business_id: CurrentBusinessId,
    bundle_id: str,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> BundleEconomicsRead:
    bundle = await _get_bundle(session, business_id, bundle_id)
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


async def _get_product(session: DbSession, business_id, product_id: str) -> Product:
    try:
        parsed = uuid.UUID(product_id)
    except ValueError:
        raise NotFoundError("Product not found") from None
    product = await session.get(Product, parsed)
    if product is None or product.business_id != business_id:
        raise NotFoundError("Product not found")
    return product


async def _get_bundle(session: DbSession, business_id, bundle_id: str) -> Bundle:
    try:
        parsed = uuid.UUID(bundle_id)
    except ValueError:
        raise NotFoundError("Bundle not found") from None
    bundle = await session.get(Bundle, parsed)
    if bundle is None or bundle.business_id != business_id:
        raise NotFoundError("Bundle not found")
    return bundle